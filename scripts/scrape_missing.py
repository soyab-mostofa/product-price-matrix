"""Comprehensive multi-channel discovery for missing product listings.

Targets:
  1. All products (Local & Imported) with 0 active listings.
  2. Products with < 2 active listings to increase benchmark density.

Channels queried:
  - Shajgoj (Next.js / Algolia data route)
  - Arogga (REST Search API)
  - OhSoGo (Storefront Suggest API)
  - Daraz (AJAX Catalog API)

Enforces strict `sku_matcher.validate_match` standards. Upgrades unverified
listings or adds verified ones, recomputing `market_average_price` and
`mrp_source_type` across all local D1 replicas.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sku_matcher import validate_match  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
D1_DIR = ROOT / ".wrangler/state/v3/d1/miniflare-D1DatabaseObject"
PROGRESS_PATH = ROOT / "scrape_missing_progress.json"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"


def _http_get_json(url: str, timeout: int = 15) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


class ShajgojChannel:
    name = "Shajgoj"
    host = "https://shop.shajgoj.com"
    _build_id_re = re.compile(r'"buildId":"([^"]+)"')

    def __init__(self) -> None:
        self.build_id = self._read_build_id()

    def _read_build_id(self) -> str:
        req = urllib.request.Request(f"{self.host}/shop", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        found = self._build_id_re.search(html)
        if not found:
            raise RuntimeError("Shajgoj build ID not found")
        return found.group(1)

    def search(self, query: str) -> list[dict]:
        url = f"{self.host}/_next/data/{self.build_id}/shop.json?query={urllib.parse.quote_plus(query[:70])}"
        try:
            payload = _http_get_json(url, timeout=12)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                self.build_id = self._read_build_id()
                url = f"{self.host}/_next/data/{self.build_id}/shop.json?query={urllib.parse.quote_plus(query[:70])}"
                payload = _http_get_json(url, timeout=12)
            else:
                raise
        results = payload.get("pageProps", {}).get("serverState", {}).get("initialResults", {})
        if not results:
            return []
        first = next(iter(results.values()))
        return (first.get("results") or [{}])[0].get("hits", [])[:12]

    def extract(self, hit: dict) -> tuple[str, float, str, str | None] | None:
        name = str(hit.get("name") or "").strip()
        slug = str(hit.get("slug") or "").strip()
        if not name or not slug:
            return None
        price = hit.get("sale_price") if hit.get("has_sale") else hit.get("price")
        if price in (None, ""):
            price = hit.get("price")
        try:
            val = float(price)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        if val <= 0:
            return None
        return name, val, f"{self.host}/product/{slug}", str(hit.get("size") or "") or None


class AroggaChannel:
    name = "Arogga"

    def search(self, query: str) -> list[dict]:
        url = f"https://api.arogga.com/general/v3/search?_search={urllib.parse.quote_plus(query[:60])}&_page=1&_perPage=10"
        payload = _http_get_json(url, timeout=12)
        return payload.get("data", [])[:10]

    def extract(self, hit: dict) -> tuple[str, float, str, str | None] | None:
        name = str(hit.get("p_name") or "").strip()
        pv_list = hit.get("pv") or []
        if not name or not pv_list:
            return None
        pv = pv_list[0]
        price = pv.get("pv_b2c_discounted_price") or pv.get("pv_b2c_price") or pv.get("pv_mrp")
        pv_id = pv.get("pv_id") or hit.get("id")
        if not price or not pv_id:
            return None
        try:
            val = float(price)
        except (TypeError, ValueError):
            return None
        if val <= 0:
            return None
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        url = f"https://www.arogga.com/product/{pv_id}/{slug}"
        size = str(pv.get("pu_b2c_sales_unit_label") or pv.get("pu_base_unit_label") or "") or None
        return name, val, url, size


class OhSoGoChannel:
    name = "OhSoGo"
    host = "https://www.ohsogo.com"

    def search(self, query: str) -> list[dict]:
        url = f"{self.host}/search/suggest.json?q={urllib.parse.quote_plus(query[:60])}&resources[type]=product"
        payload = _http_get_json(url, timeout=12)
        return payload.get("resources", {}).get("results", {}).get("products", [])[:10]

    def extract(self, hit: dict) -> tuple[str, float, str, str | None] | None:
        title = str(hit.get("title") or "").strip()
        raw_url = str(hit.get("url") or "").strip()
        raw_price = hit.get("price")
        if not title or not raw_url or raw_price is None:
            return None
        try:
            val = float(raw_price)
        except (TypeError, ValueError):
            return None
        if val <= 0:
            return None
        clean_url = raw_url.split("?")[0]
        full_url = f"{self.host}{clean_url}" if clean_url.startswith("/") else clean_url
        return title, val, full_url, None


class DarazChannel:
    name = "Daraz"

    def search(self, query: str) -> list[dict]:
        url = f"https://www.daraz.com.bd/catalog/?q={urllib.parse.quote_plus(query[:60])}&ajax=true"
        payload = _http_get_json(url, timeout=15)
        return payload.get("mods", {}).get("listItems", [])[:12]

    def extract(self, hit: dict) -> tuple[str, float, str, str | None] | None:
        name = str(hit.get("name") or "").strip()
        raw_item_url = str(hit.get("itemUrl") or "").strip()
        raw_price = hit.get("price")
        if not name or not raw_item_url or raw_price is None:
            return None
        try:
            val = float(raw_price)
        except (TypeError, ValueError):
            return None
        if val <= 0:
            return None
        url = f"https:{raw_item_url}" if raw_item_url.startswith("//") else raw_item_url
        return name, val, url, None


CHANNELS = {
    "Arogga": AroggaChannel,
    "Daraz": DarazChannel,
    "OhSoGo": OhSoGoChannel,
    "Shajgoj": ShajgojChannel,
}


def clean_search_query(name: str, brand: str) -> str:
    """Normalize noisy titles and known typos so marketplace APIs match."""
    q = name
    # Typos & normalizations
    q = re.sub(r"\bJiseon\b", "Joseon", q, flags=re.I)
    q = re.sub(r"\bHeir\b", "Hair", q, flags=re.I)
    q = re.sub(r"Head To Tea", "Head To Toe", q, flags=re.I)
    q = re.sub(r"\bCOND\b", "Conditioner", q, flags=re.I)
    q = re.sub(r"\bLON\b", "Long", q, flags=re.I)
    q = re.sub(r"\b1LTR\b", "1000ml", q, flags=re.I)
    q = re.sub(r"200mI\b", "200ml", q)
    q = re.sub(r"100mI\b", "100ml", q)
    q = re.sub(r"250mI\b", "250ml", q)
    # Remove Bengali text suffixes or parentheses that confuse English search engines
    q = re.sub(r"/[^a-zA-Z0-9\s]+.*", "", q)
    q = re.sub(r"\[.*?\]|\(.*?\)", "", q)
    q = " ".join(q.split())
    if brand.lower() not in q.lower():
        q = f"{brand} {q}"
    return q


def replica_paths() -> list[Path]:
    found = []
    for path in sorted(D1_DIR.glob("*.sqlite")):
        if path.name == "metadata.sqlite":
            continue
        try:
            con = sqlite3.connect(path, timeout=5)
            count = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='products'").fetchone()[0]
            con.close()
            if count:
                found.append(path)
        except Exception:
            pass
    return found


def record_match(connections: list[sqlite3.Connection], row_id: int, channel: str,
                 title: str, price: float, url: str, confidence: float) -> None:
    for con in connections:
        con.execute(
            """
            INSERT INTO marketplace_listings
              (row_id, channel_name, price, url, matched_title, seller, confidence, available, verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1)
            ON CONFLICT(row_id, channel_name) DO UPDATE SET
              price = excluded.price,
              url = excluded.url,
              matched_title = excluded.matched_title,
              confidence = excluded.confidence,
              verified = 1
            """,
            (row_id, channel, price, url, title, channel, confidence),
        )
        con.execute(
            """
            UPDATE products
               SET market_average_price = COALESCE(
                     (SELECT price FROM marketplace_listings
                       WHERE row_id = ?1 AND channel_name = 'Official Store' AND available = 1 AND verified = 1),
                     (SELECT AVG(price) FROM marketplace_listings
                       WHERE row_id = ?1 AND available = 1 AND verified = 1),
                     market_average_price,
                     manufactured_price
                   ),
                   mrp_source_type = CASE
                     WHEN EXISTS (SELECT 1 FROM marketplace_listings
                                   WHERE row_id = ?1 AND channel_name = 'Official Store' AND available = 1 AND verified = 1) THEN 'official'
                     WHEN EXISTS (SELECT 1 FROM marketplace_listings
                                   WHERE row_id = ?1 AND available = 1 AND verified = 1) THEN 'third_party_avg'
                     ELSE 'reference'
                   END
             WHERE row_id = ?1
            """,
            (row_id,),
        )
        con.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unlisted-only", action="store_true", help="Only target products with 0 listings")
    parser.add_argument("--origin", choices=["all", "local", "imported"], default="all", help="Target origin")
    parser.add_argument("--delay", type=float, default=0.25, help="Seconds between requests")
    parser.add_argument("--reset", action="store_true", help="Reset progress")
    args = parser.parse_args()

    databases = replica_paths()
    if not databases:
        print("No local D1 replicas found.")
        return

    connections = [sqlite3.connect(p, timeout=30) for p in databases]
    for c in connections:
        c.execute("PRAGMA busy_timeout = 30000")

    primary = connections[0]

    origin_clause = ""
    if args.origin != "all":
        origin_clause = f"AND p.sourcing_origin = '{args.origin}'"

    if args.unlisted_only:
        filter_clause = "AND (SELECT COUNT(*) FROM marketplace_listings l WHERE l.row_id = p.row_id AND l.verified = 1) = 0"
    else:
        # Target products with 0 or only 1 verified listing
        filter_clause = "AND (SELECT COUNT(*) FROM marketplace_listings l WHERE l.row_id = p.row_id AND l.verified = 1) < 2"

    query = f"""
        SELECT p.row_id, p.product_name, p.brand_name, p.size, p.sourcing_origin,
               (SELECT COUNT(*) FROM marketplace_listings l WHERE l.row_id = p.row_id AND l.verified = 1) as verified_cnt
          FROM products p
         WHERE 1=1 {origin_clause} {filter_clause}
         ORDER BY verified_cnt ASC, p.row_id ASC
    """
    targets = primary.execute(query).fetchall()

    progress: dict[str, Any] = {} if args.reset or not PROGRESS_PATH.exists() else json.loads(PROGRESS_PATH.read_text())
    done: set[str] = set(progress.get("done", []))

    channel_instances = {}
    for name, cls in CHANNELS.items():
        try:
            channel_instances[name] = cls()
        except Exception as exc:
            print(f"Channel {name} init failed: {exc}")

    print(f"Targeting {len(targets)} products with low/missing listings across {len(channel_instances)} channels:")
    print(f"  Origin filter: {args.origin}")
    print(f"  Channels: {', '.join(channel_instances.keys())}")
    print(f"  Replicas: {len(connections)}\n")

    new_matches = 0

    for idx, (row_id, name, brand, size, origin, verified_count) in enumerate(targets, start=1):
        clean_q = clean_search_query(name, brand)

        # Skip channels the product already has verified listings for
        existing_channels = set(
            r[0] for r in primary.execute(
                "SELECT channel_name FROM marketplace_listings WHERE row_id = ? AND verified = 1", (row_id,)
            ).fetchall()
        )

        for ch_name, ch in channel_instances.items():
            if ch_name in existing_channels:
                continue

            key = f"{row_id}:{ch_name}"
            if key in done and not args.reset:
                continue

            try:
                hits = ch.search(clean_q)
            except Exception:
                done.add(key)
                continue

            matched = None
            for hit in hits:
                parsed = ch.extract(hit)
                if not parsed:
                    continue
                cand_title, cand_price, cand_url, cand_size = parsed
                verdict = validate_match(
                    brand=brand,
                    product_name=name,
                    target_size_text=size,
                    candidate_name=cand_title,
                    candidate_context=ch_name,
                    candidate_size_text=cand_size,
                )
                if verdict.accepted:
                    matched = (cand_title, cand_price, cand_url, max(0.0, min(100.0, float(verdict.score))))
                    break

            if matched:
                matched_title, matched_price, matched_url, confidence = matched
                record_match(connections, row_id, ch_name, matched_title, matched_price, matched_url, confidence)
                new_matches += 1
                print(f"  [{idx}/{len(targets)}] [{origin}] {ch_name:8} ৳{matched_price:>7.0f} ({confidence:.0f}%) -> {name[:40]}")

            done.add(key)
            PROGRESS_PATH.write_text(json.dumps({"done": sorted(done)}))
            time.sleep(args.delay)

        if idx % 15 == 0:
            print(f"  … evaluated {idx}/{len(targets)} targets (+{new_matches} new listings added)")

    print(f"\nDiscovery completed: +{new_matches} new verified listings added.")
    for c in connections:
        c.close()


if __name__ == "__main__":
    main()
