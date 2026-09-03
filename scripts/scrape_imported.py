"""Discover marketplace listings for Imported SKUs.

Storefronts here are JavaScript apps, not server-rendered HTML, so scraping the
search page yields nothing. Shajgoj is a Next.js site backed by an Algolia
index; its shop route exposes that index's results as structured JSON through
Next's own data endpoint, which is both cheaper and more reliable than parsing
markup. Every candidate still passes the project's strict matcher — brand,
category, volume, bundle and shade — before it is recorded.

A confirmed live page upgrades the SKU's seeded workbook price in place rather
than adding a second listing for the same channel.

Run:  uv run --with primp --with rapidfuzz python3 scripts/scrape_imported.py
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sku_matcher import validate_match  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
D1_DIR = ROOT / ".wrangler/state/v3/d1/miniflare-D1DatabaseObject"
PROGRESS = ROOT / "imported_scrape_progress.json"

SHAJGOJ_HOST = "https://shop.shajgoj.com"
_BUILD_ID = re.compile(r'"buildId":"([^"]+)"')


class Shajgoj:
    """Reads the storefront's Algolia index through Next.js's data route."""

    name = "Shajgoj"

    def __init__(self, client) -> None:
        self.client = client
        self.build_id = self._read_build_id()

    def _read_build_id(self) -> str:
        page = self.client.get(f"{SHAJGOJ_HOST}/shop", timeout=30).text
        found = _BUILD_ID.search(page)
        if not found:
            raise RuntimeError("Shajgoj build id not found; the storefront changed shape")
        return found.group(1)

    def search(self, query: str) -> list[dict]:
        """Hits for a query, or [] when the build id has rotated mid-crawl."""
        url = f"{SHAJGOJ_HOST}/_next/data/{self.build_id}/shop.json?query={quote_plus(query[:90])}"
        response = self.client.get(url, timeout=30)
        if response.status_code == 404:
            self.build_id = self._read_build_id()
            response = self.client.get(
                f"{SHAJGOJ_HOST}/_next/data/{self.build_id}/shop.json?query={quote_plus(query[:90])}",
                timeout=30,
            )
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}")

        payload = json.loads(response.text)
        results = payload["pageProps"]["serverState"]["initialResults"]
        first = next(iter(results.values()))["results"][0]
        return first.get("hits", [])[:15]

    @staticmethod
    def listing(hit: dict) -> tuple[str, float, str, str] | None:
        """(title, active price, url, size) — the discounted price when on sale."""
        name = str(hit.get("name") or "").strip()
        slug = str(hit.get("slug") or "").strip()
        if not name or not slug:
            return None
        price = hit.get("sale_price") if hit.get("has_sale") else hit.get("price")
        if price in (None, ""):
            price = hit.get("price")
        try:
            value = float(price)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        if value <= 0:
            return None
        return name, value, f"{SHAJGOJ_HOST}/product/{slug}", str(hit.get("size") or "")


def imported_skus(connection: sqlite3.Connection, limit: int | None) -> list[dict]:
    rows = connection.execute(
        "SELECT row_id, product_name, brand_name, size FROM products "
        "WHERE sourcing_origin = 'imported' ORDER BY row_id"
    ).fetchall()
    skus = [dict(zip(("row_id", "product_name", "brand_name", "size"), row)) for row in rows]
    return skus[:limit] if limit else skus


def record(connection: sqlite3.Connection, row_id: int, channel: str,
           title: str, price: float, url: str, confidence: float) -> None:
    """Upgrade a seeded price in place; never duplicate a channel for one SKU.

    The matcher's own score is stored rather than a flat 100, so a listing that
    only just cleared the bar is distinguishable from an exact hit.
    """
    connection.execute(
        "INSERT INTO marketplace_listings "
        "  (row_id, channel_name, price, url, matched_title, seller, confidence, available, verified) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1) "
        "ON CONFLICT(row_id, channel_name) DO UPDATE SET "
        "  price = excluded.price, url = excluded.url, "
        "  matched_title = excluded.matched_title, "
        "  confidence = excluded.confidence, verified = 1",
        (row_id, channel, price, url, title, channel, confidence),
    )


def replica_paths(explicit: Path | None) -> list[Path]:
    """Every initialised local replica.

    Vite and `wrangler d1 execute --local` resolve the same binding to
    different hashed files, so writing to just one leaves the other stale.
    Picking by file size is worse than arbitrary — it changes as they grow.
    """
    if explicit:
        return [explicit]
    found = []
    for path in sorted(D1_DIR.glob("*.sqlite")):
        if path.name == "metadata.sqlite":
            continue
        connection = sqlite3.connect(path)
        try:
            has_products = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='products'"
            ).fetchone()[0]
        finally:
            connection.close()
        if has_products:
            found.append(path)
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="only the first N SKUs")
    parser.add_argument("--delay", type=float, default=0.8, help="seconds between requests")
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--reset", action="store_true", help="ignore saved progress")
    parser.add_argument("--retries", type=int, default=2, help="attempts per SKU on network errors")
    args = parser.parse_args()

    import primp

    databases = replica_paths(args.db)
    if not databases:
        print("No local D1 replica found; run `bun run db:local:migrate` first.")
        return
    connections = [sqlite3.connect(path, timeout=30) for path in databases]
    for connection in connections:
        connection.execute("PRAGMA busy_timeout = 30000")

    client = primp.Client(impersonate="chrome_130", timeout=30, verify=False)
    channel = Shajgoj(client)
    skus = imported_skus(connections[0], args.limit)

    progress = {} if args.reset or not PROGRESS.exists() else json.loads(PROGRESS.read_text())
    done: set[str] = set(progress.get("done", []))
    stats: dict[str, int] = {}
    verified = 0

    print(f"Scraping {len(skus)} imported SKUs on {channel.name} (build {channel.build_id})")
    print(f"Writing to {len(connections)} local replica(s)\n")
    for index, sku in enumerate(skus, start=1):
        key = f"{sku['row_id']}:{channel.name}"
        if key in done:
            continue
        query = f"{sku['brand_name']} {sku['product_name']}"

        # DNS and timeouts here are transient; a single blip should not cost a
        # SKU its listing for the whole run.
        hits, failure = [], None
        for attempt in range(args.retries + 1):
            try:
                hits, failure = channel.search(query), None
                break
            except Exception as error:
                failure = type(error).__name__
                time.sleep(args.delay * (2 ** attempt))
        if failure:
            stats[f"error:{failure}"] = stats.get(f"error:{failure}", 0) + 1
            continue

        accepted = None
        for hit in hits:
            parsed = channel.listing(hit)
            if not parsed:
                continue
            title, price, url, size = parsed
            verdict = validate_match(
                brand=sku["brand_name"],
                product_name=sku["product_name"],
                target_size_text=sku["size"],
                candidate_name=title,
                candidate_context=channel.name,
                candidate_size_text=size or None,
            )
            if verdict.accepted:
                accepted = (title, price, url, max(0.0, min(100.0, float(verdict.score))))
                break

        if accepted:
            for connection in connections:
                record(connection, sku["row_id"], channel.name, *accepted)
                connection.commit()
            verified += 1
            stats["matched"] = stats.get("matched", 0) + 1
            print(f"  [{index}/{len(skus)}] {accepted[1]:>7.0f}  {accepted[0][:56]}  ({accepted[3]:.0f}%)")
        else:
            stats["no-valid-match" if hits else "no-results"] = \
                stats.get("no-valid-match" if hits else "no-results", 0) + 1

        done.add(key)
        if index % 20 == 0:
            PROGRESS.write_text(json.dumps({"done": sorted(done)}))
            print(f"  … {index}/{len(skus)} scanned, {verified} verified")
        time.sleep(args.delay)

    PROGRESS.write_text(json.dumps({"done": sorted(done)}))
    for connection in connections:
        connection.close()
    print(f"\nVerified listings written: {verified}")
    print("Outcomes: " + ", ".join(f"{k}={v}" for k, v in sorted(stats.items())))


if __name__ == "__main__":
    main()
