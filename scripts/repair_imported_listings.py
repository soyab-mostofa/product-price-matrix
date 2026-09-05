"""Repair and re-synchronize marketplace listings for imported SKUs.

Enforces:
1. Canonical Arogga product URLs using `product_id` instead of `pv_id`
   (/product/{product_id}/{slug}).
2. Strict SKU matching (rejecting wrong variants, product types, actives, and scents).
3. Reversion of invalid/unmatched third-party listings back to workbook baseline
   (verified = 0, url = NULL, matched_title = NULL).
4. Recomputation of authoritative market_average_price and mrp_source_type.
5. Synchronization across all local D1 replicas.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from imported_seed import read_workbook  # noqa: E402
from sku_matcher import validate_match  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
D1_DIR = ROOT / ".wrangler/state/v3/d1/miniflare-D1DatabaseObject"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}


def get_replica_paths() -> list[Path]:
    dbs = []
    for p in sorted(D1_DIR.glob("*.sqlite")):
        if p.name == "metadata.sqlite":
            continue
        try:
            con = sqlite3.connect(p, timeout=5)
            count = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='products'").fetchone()[0]
            con.close()
            if count:
                dbs.append(p)
        except Exception:
            pass
    return dbs


def scrape_arogga_for_sku(brand: str, name: str, size: str | None) -> tuple[str, float, str, str | None, float] | None:
    query = name if name.lower().startswith(brand.lower()) else f"{brand} {name}"
    url = f"https://api.arogga.com/general/v3/search?_search={urllib.parse.quote_plus(query[:60])}&_page=1&_perPage=10"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        print(f"    [Arogga] API error for {name}: {exc}")
        return None

    for item in data.get("data", []):
        p_name = str(item.get("p_name") or "").strip()
        p_id = item.get("id") or item.get("p_id")
        if not p_name or not p_id:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", p_name.lower()).strip("-")
        prod_url = f"https://www.arogga.com/product/{p_id}/{slug}"

        for pv in item.get("pv", []):
            raw_price = pv.get("pv_b2c_discounted_price") or pv.get("pv_b2c_price") or pv.get("pv_mrp")
            if not raw_price:
                continue
            try:
                price = float(raw_price)
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            cand_size = str(pv.get("pu_b2c_sales_unit_label") or pv.get("pu_base_unit_label") or "") or None

            verdict = validate_match(
                brand=brand,
                product_name=name,
                target_size_text=size,
                candidate_name=p_name,
                candidate_context="Arogga",
                candidate_size_text=cand_size,
            )
            if verdict.accepted:
                return p_name, price, prod_url, cand_size, verdict.score

    return None


def main() -> None:
    replicas = get_replica_paths()
    if not replicas:
        print("No local D1 replicas found!")
        sys.exit(1)

    print(f"Found {len(replicas)} local D1 database replicas:")
    for r in replicas:
        print(f"  - {r.name}")

    workbook_report = read_workbook()
    workbook_skus = {sku.product_name: sku for sku in workbook_report.skus}
    print(f"Loaded {len(workbook_skus)} imported SKUs from commercial workbook.")

    primary = sqlite3.connect(replicas[0], timeout=30)
    primary_skus = primary.execute(
        "SELECT row_id, product_name, brand_name, size, category, manufactured_price FROM products WHERE sourcing_origin = 'imported' ORDER BY row_id"
    ).fetchall()
    primary.close()

    print(f"\n--- STEP 1: Re-scraping and verifying Arogga for {len(primary_skus)} imported SKUs ---")
    arogga_results = {}
    for idx, (row_id, name, brand, size, cat, cost) in enumerate(primary_skus, start=1):
        res = scrape_arogga_for_sku(brand, name, size)
        if res:
            p_name, price, prod_url, cand_size, score = res
            arogga_results[row_id] = res
            print(f"  [{idx}/{len(primary_skus)}] MATCH Arogga ৳{price:.0f} ({score:.0f}%): {name[:35]} -> {p_name[:35]}")
        else:
            print(f"  [{idx}/{len(primary_skus)}] NO MATCH Arogga: {name[:45]}")
        time.sleep(0.04)

    print(f"\nArogga matching complete: {len(arogga_results)} accepted matches.")

    print("\n--- STEP 2: Auditing all channels for imported SKUs ---")
    connections = [sqlite3.connect(p, timeout=30) for p in replicas]
    for c in connections:
        c.execute("PRAGMA busy_timeout = 30000")

    # Clean other channels
    for con in connections:
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("BEGIN IMMEDIATE")

        # 1. Update Arogga listings
        for row_id, name, brand, size, cat, cost in primary_skus:
            wb_sku = workbook_skus.get(name)
            wb_arogga_price = wb_sku.channel_prices.get("Arogga") if wb_sku else None

            if row_id in arogga_results:
                p_name, price, prod_url, cand_size, score = arogga_results[row_id]
                con.execute(
                    """
                    INSERT INTO marketplace_listings
                      (row_id, channel_name, price, url, matched_title, size, seller, confidence, available, verified)
                    VALUES (?, 'Arogga', ?, ?, ?, ?, 'Arogga', ?, 1, 1)
                    ON CONFLICT(row_id, channel_name) DO UPDATE SET
                      price = excluded.price,
                      url = excluded.url,
                      matched_title = excluded.matched_title,
                      size = excluded.size,
                      confidence = excluded.confidence,
                      verified = 1,
                      available = 1
                    """,
                    (row_id, price, prod_url, p_name, cand_size, score),
                )
            else:
                # No valid Arogga match
                if wb_arogga_price is not None:
                    con.execute(
                        """
                        INSERT INTO marketplace_listings
                          (row_id, channel_name, price, url, matched_title, size, seller, confidence, available, verified)
                        VALUES (?, 'Arogga', ?, NULL, NULL, NULL, 'Arogga', 100.0, 1, 0)
                        ON CONFLICT(row_id, channel_name) DO UPDATE SET
                          price = excluded.price,
                          url = NULL,
                          matched_title = NULL,
                          size = NULL,
                          confidence = 100.0,
                          verified = 0,
                          available = 1
                        """,
                        (row_id, wb_arogga_price),
                    )
                else:
                    con.execute("DELETE FROM marketplace_listings WHERE row_id = ? AND channel_name = 'Arogga'", (row_id,))

        # 2. Audit and sanitize Daraz, OhSoGo, Shajgoj
        listings = con.execute(
            """
            SELECT ml.row_id, ml.channel_name, ml.price, ml.url, ml.matched_title, ml.size, p.product_name, p.brand_name, p.size
            FROM marketplace_listings ml
            JOIN products p ON p.row_id = ml.row_id
            WHERE p.sourcing_origin = 'imported' AND ml.channel_name IN ('Daraz', 'OhSoGo', 'Shajgoj') AND ml.verified = 1
            """
        ).fetchall()

        purged = 0
        for l_row_id, ch, l_price, l_url, m_title, l_size, p_name, brand, p_size in listings:
            verdict = validate_match(
                brand=brand,
                product_name=p_name,
                target_size_text=p_size,
                candidate_name=m_title or "",
                candidate_context=ch,
                candidate_size_text=l_size,
            )
            if not verdict.accepted:
                purged += 1
                wb_sku = workbook_skus.get(p_name)
                wb_price = wb_sku.channel_prices.get(ch) if wb_sku else None
                if wb_price is not None:
                    con.execute(
                        """
                        UPDATE marketplace_listings
                        SET price = ?, url = NULL, matched_title = NULL, verified = 0, confidence = 100.0
                        WHERE row_id = ? AND channel_name = ?
                        """,
                        (wb_price, l_row_id, ch),
                    )
                else:
                    con.execute("DELETE FROM marketplace_listings WHERE row_id = ? AND channel_name = ?", (l_row_id, ch))

        print(f"Purged / downgraded {purged} invalid non-Arogga listings in {con}")

        # 3. Recompute market_average_price and mrp_source_type for imported products
        con.execute(
            """
            UPDATE products
               SET market_average_price = COALESCE(
                     (SELECT price FROM marketplace_listings
                       WHERE row_id = products.row_id AND channel_name = 'Official Store' AND available = 1 AND verified = 1),
                     (SELECT AVG(price) FROM marketplace_listings
                       WHERE row_id = products.row_id AND available = 1 AND verified = 1),
                     (SELECT AVG(price) FROM marketplace_listings
                       WHERE row_id = products.row_id AND available = 1),
                     products.market_average_price,
                     products.manufactured_price
                   ),
                   mrp_source_type = CASE
                     WHEN EXISTS (SELECT 1 FROM marketplace_listings
                                   WHERE row_id = products.row_id AND channel_name = 'Official Store' AND available = 1 AND verified = 1) THEN 'official'
                     WHEN EXISTS (SELECT 1 FROM marketplace_listings
                                   WHERE row_id = products.row_id AND available = 1 AND verified = 1) THEN 'third_party_avg'
                     ELSE 'reference'
                   END
             WHERE sourcing_origin = 'imported'
            """
        )
        con.commit()
        con.close()

    print("\n--- STEP 3: Verification complete across all local D1 replicas ---")


if __name__ == "__main__":
    main()
