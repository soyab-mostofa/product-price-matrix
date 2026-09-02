from __future__ import annotations

from pathlib import Path
import sqlite3
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/0002_secure_pricing_and_product_ids.sql"

OLD_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE global_pricing_params (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  packaging REAL NOT NULL DEFAULT 20,
  transport REAL NOT NULL DEFAULT 40,
  delivery REAL NOT NULL DEFAULT 60,
  cac REAL NOT NULL DEFAULT 80,
  target_margin_pct REAL NOT NULL DEFAULT 25,
  discount_type TEXT NOT NULL DEFAULT 'pct',
  discount_val REAL NOT NULL DEFAULT 10,
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
  confidence REAL DEFAULT 100,
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


class MigrationTests(unittest.TestCase):
    def test_secure_pricing_migration_is_expand_only_and_preserves_state(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.executescript(OLD_SCHEMA)
        connection.execute(
            "INSERT INTO global_pricing_params "
            "(id, packaging, transport, delivery, cac, target_margin_pct, discount_type, discount_val) "
            "VALUES (1, 99, 88, 77, 66, 25, 'amt', 55)"
        )
        connection.execute(
            "INSERT INTO products "
            "(row_id, product_name, brand_name, manufactured_price, market_average_price) "
            "VALUES (7, 'Unique Serum', 'Example', 100, 200)"
        )
        connection.execute(
            "INSERT INTO marketplace_listings (row_id, channel_name, price, url, available) "
            "VALUES (7, 'Official Store', 200, 'https://example.com/item', 1)"
        )
        connection.execute(
            "INSERT INTO product_pricing_overrides "
            "(product_name, packaging, transport, delivery, cac, target_margin_pct, discount_type, discount_val) "
            "VALUES ('Unique Serum', 1, 2, 3, 4, 5, 'pct', 6)"
        )

        connection.executescript(MIGRATION.read_text(encoding="utf-8"))

        global_params = connection.execute(
            "SELECT packaging, transport, delivery, cac, target_margin_pct, discount_type, discount_val "
            "FROM global_pricing_params WHERE id = 1"
        ).fetchone()
        override_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(product_pricing_overrides)")
        }
        override = connection.execute(
            "SELECT product_name, product_row_id FROM product_pricing_overrides"
        ).fetchone()
        source_type = connection.execute(
            "SELECT mrp_source_type FROM products WHERE row_id = 7"
        ).fetchone()[0]

        self.assertEqual((99.0, 88.0, 77.0, 66.0, 25.0, "amt", 55.0), global_params)
        self.assertEqual({"product_name", "product_row_id"}, override_columns & {"product_name", "product_row_id"})
        self.assertEqual(("Unique Serum", 7), override)
        self.assertEqual("official", source_type)

        connection.execute(
            "INSERT INTO product_pricing_overrides "
            "(product_row_id, packaging, transport, delivery, cac, target_margin_pct, discount_type, discount_val) "
            "VALUES (8, 1, 2, 3, 4, 5, 'pct', 6) "
            "ON CONFLICT(product_row_id) DO UPDATE SET packaging = excluded.packaging"
        )
        connection.close()


if __name__ == "__main__":
    unittest.main()
