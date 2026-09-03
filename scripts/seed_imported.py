"""Write the workbook's Imported SKUs into every local D1 replica.

Idempotent: SKUs are keyed by (product_name, sourcing_origin), so re-running
updates in place rather than duplicating. Workbook prices land as *unverified*
listings — real research with no product page attached yet — which discovery
later upgrades once it finds and confirms the live page.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from imported_seed import find_overlaps, read_workbook  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
D1_DIR = ROOT / ".wrangler/state/v3/d1/miniflare-D1DatabaseObject"
REPORT_PATH = ROOT / "imported_seed_report.json"

# A brand is required by the schema; one SKU genuinely cannot be resolved and
# is parked here rather than guessed at. See tests/test_imported_seed.py.
UNKNOWN_BRAND = "Unknown"


def seed(path: Path) -> dict[str, int]:
    report = read_workbook()
    connection = sqlite3.connect(path, timeout=30)
    connection.execute("PRAGMA busy_timeout = 30000")
    try:
        # Overlaps mean "this imported SKU already exists as a local one", so the
        # comparison is against the local book only — otherwise a re-run reports
        # every imported SKU as colliding with the copy it wrote last time.
        existing = list(connection.execute(
            "SELECT product_name, size FROM products WHERE sourcing_origin = 'local'"
        ))
        find_overlaps(report, existing)

        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")

        # Start each SKU's row_id above the local catalog so the two books never
        # fight over an id when the local catalog is later re-seeded.
        next_id = (connection.execute("SELECT COALESCE(MAX(row_id), 0) FROM products").fetchone()[0]) + 1
        products = written = listings = 0

        for sku in report.skus:
            found = connection.execute(
                "SELECT row_id FROM products WHERE product_name = ? AND sourcing_origin = 'imported'",
                (sku.product_name,),
            ).fetchone()
            brand = sku.brand_name or UNKNOWN_BRAND
            # The workbook has no market benchmark for imported SKUs; the mean of
            # its channel prices is the best available reference until discovery
            # confirms an official or third-party price.
            prices = list(sku.channel_prices.values())
            benchmark = sum(prices) / len(prices) if prices else sku.source_cost
            mrp_source = "third_party_avg" if prices else "reference"

            if found:
                row_id = found[0]
                connection.execute(
                    "UPDATE products SET brand_name = ?, size = ?, manufactured_price = ?, "
                    "market_average_price = ?, canonical_name = ?, mrp_source_type = ?, category = ? "
                    "WHERE row_id = ?",
                    (brand, sku.size, sku.source_cost, benchmark, sku.product_name,
                     mrp_source, sku.category, row_id),
                )
            else:
                row_id = next_id
                next_id += 1
                connection.execute(
                    "INSERT INTO products (row_id, product_name, brand_name, size, "
                    "manufactured_price, market_average_price, canonical_name, "
                    "mrp_source_type, sourcing_origin, category) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'imported', ?)",
                    (row_id, sku.product_name, brand, sku.size, sku.source_cost,
                     benchmark, sku.product_name, mrp_source, sku.category),
                )
                products += 1
            written += 1

            for channel, price in sku.channel_prices.items():
                # Never downgrade a verified listing back to workbook data.
                connection.execute(
                    "INSERT INTO marketplace_listings "
                    "  (row_id, channel_name, price, url, matched_title, seller, confidence, available, verified) "
                    "VALUES (?, ?, ?, NULL, NULL, NULL, 100.0, 1, 0) "
                    "ON CONFLICT(row_id, channel_name) DO UPDATE SET price = excluded.price "
                    "  WHERE marketplace_listings.verified = 0",
                    (row_id, channel, price),
                )
                listings += 1

        # Recompute authoritative MRP from active listings
        connection.execute(
            """
            UPDATE products
               SET market_average_price = COALESCE(
                     (SELECT price FROM marketplace_listings
                       WHERE row_id = products.row_id AND channel_name = 'Official Store' AND available = 1),
                     (SELECT AVG(price) FROM marketplace_listings
                       WHERE row_id = products.row_id AND available = 1),
                     products.manufactured_price
                   ),
                   mrp_source_type = CASE
                     WHEN EXISTS (SELECT 1 FROM marketplace_listings
                                   WHERE row_id = products.row_id AND channel_name = 'Official Store' AND available = 1) THEN 'official'
                     WHEN EXISTS (SELECT 1 FROM marketplace_listings
                                   WHERE row_id = products.row_id AND available = 1) THEN 'third_party_avg'
                     ELSE 'reference'
                   END
             WHERE sourcing_origin = 'imported'
            """
        )

        connection.commit()

        report_data = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "products_total": len(report.skus),
            "listings_total": report.listing_count,
            "unresolved_brands": report.unresolved_brands,
            "missing_sizes": report.missing_sizes,
            "overlaps": [list(o) for o in report.overlaps],
            "rejected_prices": [list(r) for r in report.rejected_prices],
        }
        REPORT_PATH.write_text(json.dumps(report_data, indent=2), encoding="utf-8")

        return {
            "products_inserted": products,
            "products_written": written,
            "listings_written": listings,
            "unresolved_brands": len(report.unresolved_brands),
            "overlaps": len(report.overlaps),
            "rejected_cells": len(report.rejected_prices),
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main() -> None:
    replicas = [
        path for path in sorted(D1_DIR.glob("*.sqlite"))
        if path.name != "metadata.sqlite"
    ]
    if not replicas:
        print("No local D1 replica found; run `bun run db:local:migrate` first.")
        return

    for path in replicas:
        has_products = path.stat().st_size > 0 and sqlite3.connect(path).execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='products'"
        ).fetchone()[0]
        if not has_products:
            continue
        stats = seed(path)
        print(f"Seeded {path.name}: " + ", ".join(f"{k}={v}" for k, v in stats.items()))


if __name__ == "__main__":
    main()
