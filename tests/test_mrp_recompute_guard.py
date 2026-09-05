"""The scrapers must never overwrite a local SKU's workbook MRP.

A local SKU's MRP is the workbook benchmark (AGENTS.md §4.3): the cost basis
is a trade discount off exactly that number, so replacing it with a live
listing breaks the arithmetic and makes healthy margins read as losses.

Discovery passes recompute `market_average_price` from listings, which is
right for imported SKUs and wrong for local ones. That recompute was once
unguarded and silently corrupted 71 local benchmarks — every one lower than
the workbook, because it had been replaced by a promotional price. These
tests pin the guard in the SQL itself, so removing the origin filter fails
here rather than in production.
"""
from __future__ import annotations

import re
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SCHEMA = ROOT / "schema.sql"
SCRAPERS = (
    ROOT / "scripts/scrape_missing.py",
    ROOT / "scripts/scrape_imported.py",
)


class MrpRecomputeGuardTests(unittest.TestCase):
    def test_every_mrp_recompute_is_scoped_to_imported(self) -> None:
        """Each `UPDATE products ... mrp_source_type` must filter on origin."""
        for scraper in SCRAPERS:
            source = scraper.read_text(encoding="utf-8")
            statements = [
                match.group(0)
                for match in re.finditer(
                    r"UPDATE products.*?\"\"\"", source, re.DOTALL
                )
            ]
            recomputes = [s for s in statements if "mrp_source_type" in s]
            self.assertTrue(
                recomputes,
                f"{scraper.name}: expected an MRP recompute to guard",
            )
            for statement in recomputes:
                self.assertIn(
                    "sourcing_origin = 'imported'",
                    statement,
                    f"{scraper.name}: MRP recompute is not scoped to imported SKUs — "
                    "it would overwrite a local SKU's workbook benchmark",
                )

    def test_the_guard_actually_spares_local_rows(self) -> None:
        """Run the guarded statement and prove a local benchmark survives."""
        connection = sqlite3.connect(":memory:")
        connection.executescript(SCHEMA.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO products (row_id, product_name, brand_name, size, "
            "manufactured_price, market_average_price, mrp_source_type, sourcing_origin) "
            "VALUES (1, 'Local SKU', 'Brand', '100ml', 300.0, 500.0, 'workbook', 'local')"
        )
        connection.execute(
            "INSERT INTO products (row_id, product_name, brand_name, size, "
            "manufactured_price, market_average_price, mrp_source_type, sourcing_origin) "
            "VALUES (2, 'Imported SKU', 'Brand', '100ml', 300.0, 500.0, 'reference', 'imported')"
        )
        # A promotional listing well below the workbook benchmark.
        for row_id in (1, 2):
            connection.execute(
                "INSERT INTO marketplace_listings (row_id, channel_name, price, url, "
                "available, verified) VALUES (?, 'Arogga', 380.0, 'https://example.com/p', 1, 1)",
                (row_id,),
            )

        recompute = """
            UPDATE products
               SET market_average_price = COALESCE(
                     (SELECT AVG(price) FROM marketplace_listings
                       WHERE row_id = ?1 AND available = 1 AND verified = 1),
                     market_average_price
                   ),
                   mrp_source_type = 'third_party_avg'
             WHERE row_id = ?1 AND sourcing_origin = 'imported'
        """
        for row_id in (1, 2):
            connection.execute(recompute, (row_id,))
        connection.commit()

        local = connection.execute(
            "SELECT market_average_price, mrp_source_type FROM products WHERE row_id = 1"
        ).fetchone()
        self.assertEqual((500.0, "workbook"), local,
                         "the local benchmark was overwritten by a scraped price")

        imported = connection.execute(
            "SELECT market_average_price, mrp_source_type FROM products WHERE row_id = 2"
        ).fetchone()
        self.assertEqual((380.0, "third_party_avg"), imported,
                         "the imported MRP should still track live listings")
        connection.close()


if __name__ == "__main__":
    unittest.main()
