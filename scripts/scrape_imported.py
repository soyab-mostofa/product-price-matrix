"""Multi-channel marketplace discovery engine for Imported SKUs.

Queries live e-commerce search APIs across Bangladesh's major beauty channels:
  1. Shajgoj  (Next.js / Algolia SSR index endpoint)
  2. Arogga   (Direct REST catalog search API: api.arogga.com)
  3. OhSoGo   (Storefront catalog search API: ohsogo.com)
  4. Daraz    (Direct marketplace AJAX catalog endpoint: daraz.com.bd)

Every discovered candidate is evaluated through `sku_matcher.validate_match` to enforce
strict brand, volume, category, bundle, and variant integrity. Accepted matches upgrade
seeded workbook prices in place or insert verified listings with actual composite
confidence scores.

Recomputes authoritative `market_average_price` and `mrp_source_type` across all
replicas after every match, and writes an audit log to `imported_scrape_audit.json`
and `imported_scrape_summary.json`.

Usage:
  uv run --with primp --with rapidfuzz python3 scripts/scrape_imported.py
  uv run --with primp --with rapidfuzz python3 scripts/scrape_imported.py --channel Arogga
  uv run --with primp --with rapidfuzz python3 scripts/scrape_imported.py --channel OhSoGo
  uv run --with primp --with rapidfuzz python3 scripts/scrape_imported.py --channel Daraz
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
PROGRESS_PATH = ROOT / "imported_scrape_progress.json"
AUDIT_PATH = ROOT / "imported_scrape_audit.json"
SUMMARY_PATH = ROOT / "imported_scrape_summary.json"

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
            raise RuntimeError("Shajgoj build ID not found on /shop")
        return found.group(1)

    def search(self, query: str) -> list[dict]:
        url = f"{self.host}/_next/data/{self.build_id}/shop.json?query={urllib.parse.quote_plus(query[:80])}"
        try:
            payload = _http_get_json(url, timeout=12)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                self.build_id = self._read_build_id()
                url = f"{self.host}/_next/data/{self.build_id}/shop.json?query={urllib.parse.quote_plus(query[:80])}"
                payload = _http_get_json(url, timeout=12)
            else:
                raise
        results = payload.get("pageProps", {}).get("serverState", {}).get("initialResults", {})
        if not results:
            return []
        first = next(iter(results.values()))
        return (first.get("results") or [{}])[0].get("hits", [])[:15]

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
        return payload.get("mods", {}).get("listItems", [])[:15]

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
    "Shajgoj": ShajgojChannel,
    "Arogga": AroggaChannel,
    "OhSoGo": OhSoGoChannel,
    "Daraz": DarazChannel,
}


def replica_paths(explicit: Path | None) -> list[Path]:
    if explicit:
        return [explicit]
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
    parser.add_argument("--channel", choices=list(CHANNELS.keys()) + ["all"], default="all",
                        help="Specific marketplace channel to scrape (default: all)")
    parser.add_argument("--limit", type=int, default=None, help="Limit to N products")
    parser.add_argument("--delay", type=float, default=0.3, help="Delay between requests in seconds")
    parser.add_argument("--retries", type=int, default=2, help="Network retry attempts")
    parser.add_argument("--reset", action="store_true", help="Clear progress checkpoint")
    args = parser.parse_args()

    databases = replica_paths(None)
    if not databases:
        print("Error: No local D1 replicas found.")
        return

    connections = [sqlite3.connect(p, timeout=30) for p in databases]
    for c in connections:
        c.execute("PRAGMA busy_timeout = 30000")

    primary = connections[0]
    skus = primary.execute(
        """SELECT row_id, product_name, brand_name, size, category, manufactured_price
             FROM products WHERE sourcing_origin = 'imported' ORDER BY row_id"""
    ).fetchall()
    if args.limit:
        skus = skus[:args.limit]

    # Baseline coverage check
    before_coverage = primary.execute(
        """SELECT count(DISTINCT row_id) FROM marketplace_listings l
            WHERE EXISTS (SELECT 1 FROM products p WHERE p.row_id=l.row_id AND p.sourcing_origin='imported')
              AND l.verified = 1"""
    ).fetchone()[0]

    progress: dict[str, Any] = {} if args.reset or not PROGRESS_PATH.exists() else json.loads(PROGRESS_PATH.read_text())
    done: set[str] = set(progress.get("done", []))
    audit_log: list[dict[str, Any]] = []

    active_channel_names = list(CHANNELS.keys()) if args.channel == "all" else [args.channel]
    channel_instances = {}
    for name in active_channel_names:
        try:
            channel_instances[name] = CHANNELS[name]()
        except Exception as exc:
            print(f"Failed to initialize channel {name}: {exc}")

    print(f"Starting imported catalog discovery:")
    print(f"  Products: {len(skus)}")
    print(f"  Channels: {', '.join(channel_instances.keys())}")
    print(f"  Replicas: {len(connections)} databases synced")
    print(f"  Pre-scrape verified coverage: {before_coverage}/{len(skus)} SKUs\n")

    verified_new = 0

    for idx, (row_id, name, brand, size, cat, mfg_price) in enumerate(skus, start=1):
        for ch_name, ch in channel_instances.items():
            key = f"{row_id}:{ch_name}"
            if key in done and not args.reset:
                continue

            query = f"{brand} {name}"
            hits, error_str = [], None
            for attempt in range(args.retries + 1):
                try:
                    hits = ch.search(query)
                    break
                except Exception as exc:
                    error_str = type(exc).__name__
                    time.sleep(args.delay * (2 ** attempt))

            if error_str:
                audit_log.append({
                    "row_id": row_id, "brand": brand, "product": name, "channel": ch_name,
                    "accepted": False, "reason": f"API error: {error_str}"
                })
                done.add(key)
                continue

            matched_candidate = None
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
                audit_log.append({
                    "row_id": row_id, "brand": brand, "product": name, "channel": ch_name,
                    "candidate_title": cand_title, "candidate_price": cand_price,
                    "accepted": verdict.accepted, "reasons": verdict.reasons,
                    "score": round(verdict.score, 2),
                })
                if verdict.accepted:
                    matched_candidate = (cand_title, cand_price, cand_url, max(0.0, min(100.0, float(verdict.score))))
                    break

            if matched_candidate:
                c_title, c_price, c_url, c_conf = matched_candidate
                record_match(connections, row_id, ch_name, c_title, c_price, c_url, c_conf)
                verified_new += 1
                print(f"  [{idx}/{len(skus)}] {ch_name:10} ৳{c_price:>7.0f} ({c_conf:.0f}%) -> {c_title[:50]}")

            done.add(key)
            PROGRESS_PATH.write_text(json.dumps({"done": sorted(done)}))
            time.sleep(args.delay)

        if idx % 10 == 0:
            print(f"  … processed {idx}/{len(skus)} SKUs ({verified_new} new verified listings added)")

    # Post-scrape audit & summary
    after_coverage = primary.execute(
        """SELECT count(DISTINCT row_id) FROM marketplace_listings l
            WHERE EXISTS (SELECT 1 FROM products p WHERE p.row_id=l.row_id AND p.sourcing_origin='imported')
              AND l.verified = 1"""
    ).fetchone()[0]

    unlisted_skus = primary.execute(
        """SELECT row_id, product_name, brand_name, size, category FROM products p
            WHERE sourcing_origin = 'imported'
              AND NOT EXISTS (SELECT 1 FROM marketplace_listings l WHERE l.row_id = p.row_id AND l.available = 1)"""
    ).fetchall()

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_imported_skus": len(skus),
        "pre_scrape_verified_skus": before_coverage,
        "post_scrape_verified_skus": after_coverage,
        "new_verified_listings": verified_new,
        "unlisted_skus_count": len(unlisted_skus),
        "unlisted_skus": [
            {"row_id": r[0], "product_name": r[1], "brand": r[2], "size": r[3], "category": r[4]}
            for r in unlisted_skus
        ],
    }

    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    AUDIT_PATH.write_text(json.dumps(audit_log, indent=2), encoding="utf-8")

    for c in connections:
        c.close()

    print(f"\n========================================================")
    print(f"Multi-Channel Discovery Run Completed:")
    print(f"  Verified SKU Coverage: {before_coverage} -> {after_coverage} / {len(skus)}")
    print(f"  New Verified Listings: +{verified_new}")
    print(f"  Remaining Unlisted SKUs: {len(unlisted_skus)}")
    print(f"  Audit Log: {AUDIT_PATH.name}")
    print(f"  Run Summary: {SUMMARY_PATH.name}")
    print(f"========================================================")


if __name__ == "__main__":
    main()
