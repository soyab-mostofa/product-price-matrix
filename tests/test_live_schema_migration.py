"""Rehearse migrations/0002 against a byte-faithful replica of the LIVE remote D1 schema.

The live schema was captured from `wrangler d1 execute --remote` (sqlite_master.sql)
so this proves the migration applies to production as it actually exists today,
not to the local seeded replica which already has the new columns.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
import unittest

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/0002_secure_pricing_and_product_ids.sql"

# Verbatim from production sqlite_master on 2026-09-03 (pre-migration, legacy shape).
LIVE_SCHEMA = """
CREATE TABLE global_pricing_params (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  packaging REAL NOT NULL DEFAULT 20.0,
  transport REAL NOT NULL DEFAULT 40.0,
  delivery REAL NOT NULL DEFAULT 60.0,
  cac REAL NOT NULL DEFAULT 80.0,
  target_margin_pct REAL NOT NULL DEFAULT 25.0,
  discount_type TEXT NOT NULL DEFAULT 'pct',
  discount_val REAL NOT NULL DEFAULT 10.0,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE products (
  row_id INTEGER PRIMARY KEY,
  product_name TEXT NOT NULL,
  brand_name TEXT NOT NULL,
  size TEXT,
  manufactured_price REAL NOT NULL,
  market_average_price REAL NOT NULL,
  canonical_name TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE marketplace_listings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  row_id INTEGER NOT NULL,
  channel_name TEXT NOT NULL,
  price REAL NOT NULL,
  url TEXT NOT NULL,
  matched_title TEXT,
  size TEXT,
  seller TEXT,
  confidence REAL DEFAULT 100.0,
  available INTEGER DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (row_id) REFERENCES products(row_id) ON DELETE CASCADE,
  UNIQUE(row_id, channel_name)
);
CREATE TABLE product_pricing_overrides (
  product_name TEXT PRIMARY KEY,
  packaging REAL,
  transport REAL,
  delivery REAL,
  cac REAL,
  target_margin_pct REAL,
  discount_type TEXT,
  discount_val REAL,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


class LiveSchemaMigrationTests(unittest.TestCase):
    def build_live_replica(self) -> sqlite3.Connection:
        connection = sqlite3.connect(":memory:")
        connection.executescript(LIVE_SCHEMA)
        connection.executemany(
            "INSERT INTO products (row_id, product_name, brand_name, manufactured_price,"
            " market_average_price) VALUES (?, ?, ?, ?, ?)",
            [
                (222, "Amla Powder/ আমলকী গুঁড়া", "Panam", 100.0, 150.0),
                (230, "Almond Oil/ কাঠ বাদামের তেল", "Panam", 200.0, 260.0),
                (234, "Hibiscus Oil/ জবা ফুলের তেল (Big)", "Panam", 300.0, 380.0),
                (999, "Official Only SKU", "Brand", 50.0, 90.0),
                (1000, "Third Party Only SKU", "Brand", 60.0, 95.0),
                (1001, "No Listing SKU", "Brand", 70.0, 70.0),
            ],
        )
        connection.executemany(
            "INSERT INTO marketplace_listings (row_id, channel_name, price, url, available)"
            " VALUES (?, ?, ?, ?, ?)",
            [
                (999, "Official Store", 90.0, "https://example.test/a", 1),
                (1000, "Arogga", 95.0, "https://example.test/b", 1),
                (1001, "Daraz", 70.0, "https://example.test/c", 0),
            ],
        )
        # The three real production override rows.
        connection.executemany(
            "INSERT INTO product_pricing_overrides (product_name, packaging, transport,"
            " delivery, cac, target_margin_pct, discount_type, discount_val)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("Amla Powder/ আমলকী গুঁড়া", 20.0, 0.0, 0.0, 0.0, 0.0, "pct", 0.0),
                ("Almond Oil/ কাঠ বাদামের তেল", 20.0, 0.0, 0.0, 0.0, 0.0, "pct", 0.0),
                ("Hibiscus Oil/ জবা ফুলের তেল (Big)", 20.0, 0.0, 0.0, 40.0, 15.0, "pct", 0.0),
            ],
        )
        connection.commit()
        return connection

    def test_migration_applies_to_live_schema_and_preserves_overrides(self) -> None:
        connection = self.build_live_replica()
        try:
            connection.executescript(MIGRATION.read_text(encoding="utf-8"))

            rows = dict(
                connection.execute(
                    "SELECT product_row_id, cac FROM product_pricing_overrides"
                ).fetchall()
            )
            # All three real overrides are backfilled onto immutable row IDs.
            self.assertEqual({222, 230, 234}, set(rows))
            # Values survive untouched; the tuned Hibiscus row keeps its CAC of 40.
            self.assertEqual(40.0, rows[234])

            provenance = dict(
                connection.execute(
                    "SELECT row_id, mrp_source_type FROM products WHERE row_id >= 999"
                ).fetchall()
            )
            self.assertEqual("official", provenance[999])
            self.assertEqual("third_party_avg", provenance[1000])
            self.assertEqual("reference", provenance[1001])

            self.assertTrue(
                connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table'"
                    " AND name='admin_login_attempts'"
                ).fetchone()
            )
        finally:
            connection.close()

    def test_migration_is_idempotent_enough_to_be_safe_on_retry(self) -> None:
        """ALTER TABLE ADD COLUMN is not idempotent; a re-run must fail loudly,
        not silently corrupt data. Confirms the transaction rolls back cleanly."""
        connection = self.build_live_replica()
        try:
            connection.executescript(MIGRATION.read_text(encoding="utf-8"))
            before = connection.execute(
                "SELECT COUNT(*) FROM product_pricing_overrides WHERE product_row_id IS NOT NULL"
            ).fetchone()[0]

            with self.assertRaises(sqlite3.OperationalError):
                connection.executescript(MIGRATION.read_text(encoding="utf-8"))

            after = connection.execute(
                "SELECT COUNT(*) FROM product_pricing_overrides WHERE product_row_id IS NOT NULL"
            ).fetchone()[0]
            self.assertEqual(before, after)
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
