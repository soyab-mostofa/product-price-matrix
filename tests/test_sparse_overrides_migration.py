from __future__ import annotations

from pathlib import Path
import sqlite3
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/0003_sparse_pricing_overrides.sql"
SCHEMA = ROOT / "schema.sql"

DENSE_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE global_pricing_params (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  packaging REAL NOT NULL, transport REAL NOT NULL, delivery REAL NOT NULL,
  cac REAL NOT NULL, target_margin_pct REAL NOT NULL,
  discount_type TEXT NOT NULL, discount_val REAL NOT NULL,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE products (
  row_id INTEGER PRIMARY KEY, product_name TEXT NOT NULL, brand_name TEXT NOT NULL,
  size TEXT, manufactured_price REAL NOT NULL, market_average_price REAL NOT NULL,
  canonical_name TEXT, mrp_source_type TEXT NOT NULL DEFAULT 'reference'
);
CREATE TABLE product_pricing_overrides (
  product_row_id INTEGER PRIMARY KEY,
  packaging REAL NOT NULL, transport REAL NOT NULL, delivery REAL NOT NULL,
  cac REAL NOT NULL, target_margin_pct REAL NOT NULL,
  discount_type TEXT NOT NULL, discount_val REAL NOT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (product_row_id) REFERENCES products(row_id) ON DELETE CASCADE
);
"""

# Global engine: packaging 20, transport 0, delivery 60, cac 0, margin 0, 0% discount.
GLOBAL_ROW = "INSERT INTO global_pricing_params VALUES (1,20,0,60,0,0,'pct',0,CURRENT_TIMESTAMP)"


def _dense_database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(DENSE_SCHEMA)
    connection.execute(GLOBAL_ROW)
    for row_id, name in [(1, "Margin Only"), (2, "Echoes Global"), (3, "Cost And Discount")]:
        connection.execute(
            "INSERT INTO products "
            "(row_id, product_name, brand_name, manufactured_price, market_average_price) "
            "VALUES (?, ?, 'Example', 100, 200)",
            (row_id, name),
        )
    return connection


class SparseOverrideMigrationTests(unittest.TestCase):
    def test_migration_keeps_only_deliberate_pins(self) -> None:
        connection = _dense_database()
        # Only the margin differs from global.
        connection.execute(
            "INSERT INTO product_pricing_overrides "
            "VALUES (1,20,0,60,0,30,'pct',0,'2026-01-01 10:00:00')"
        )
        # Every field echoes global: this was never a real tune.
        connection.execute(
            "INSERT INTO product_pricing_overrides "
            "VALUES (2,20,0,60,0,0,'pct',0,'2026-01-02 10:00:00')"
        )
        # A cost knob plus a genuinely different discount pair.
        connection.execute(
            "INSERT INTO product_pricing_overrides "
            "VALUES (3,20,0,60,40,0,'amt',50,'2026-01-03 10:00:00')"
        )
        connection.commit()

        connection.executescript(MIGRATION.read_text(encoding="utf-8"))

        rows = {
            row[0]: row[1:]
            for row in connection.execute(
                "SELECT product_row_id, packaging, transport, delivery, cac, "
                "target_margin_pct, discount_type, discount_val, updated_at "
                "FROM product_pricing_overrides"
            )
        }

        # Row 2 pinned nothing beyond global, so it should be gone entirely.
        self.assertEqual({1, 3}, set(rows))
        # Row 1 keeps its margin; every echoed cost field now inherits global.
        self.assertEqual((None, None, None, None, 30.0, None, None, "2026-01-01 10:00:00"), rows[1])
        # Row 3 keeps its CAC and its discount pair, and nothing else.
        self.assertEqual((None, None, None, 40.0, None, "amt", 50.0, "2026-01-03 10:00:00"), rows[3])
        connection.close()

    def test_migration_drops_overrides_for_deleted_products(self) -> None:
        connection = _dense_database()
        connection.execute(
            "INSERT INTO product_pricing_overrides "
            "VALUES (1,20,0,60,0,30,'pct',0,'2026-01-01 10:00:00')"
        )
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DELETE FROM products WHERE row_id = 1")
        connection.commit()

        connection.executescript(MIGRATION.read_text(encoding="utf-8"))

        remaining = connection.execute(
            "SELECT COUNT(*) FROM product_pricing_overrides"
        ).fetchone()[0]
        self.assertEqual(0, remaining)
        connection.close()

    def test_sparse_table_enforces_override_invariants(self) -> None:
        connection = _dense_database()
        connection.commit()
        connection.executescript(MIGRATION.read_text(encoding="utf-8"))

        # A discount pins as a pair or not at all.
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO product_pricing_overrides (product_row_id, discount_type) "
                "VALUES (1, 'pct')"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO product_pricing_overrides (product_row_id, discount_val) "
                "VALUES (1, 25)"
            )
        # An override that pins nothing must not exist.
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO product_pricing_overrides (product_row_id) VALUES (1)"
            )
        # Ranges still hold.
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO product_pricing_overrides (product_row_id, target_margin_pct) "
                "VALUES (1, 100)"
            )
        # A single-field tune is the whole point.
        connection.execute(
            "INSERT INTO product_pricing_overrides (product_row_id, target_margin_pct) "
            "VALUES (1, 30)"
        )
        self.assertEqual(
            1, connection.execute("SELECT COUNT(*) FROM product_pricing_overrides").fetchone()[0]
        )
        connection.close()

    def test_schema_and_migration_agree_on_override_shape(self) -> None:
        """A fresh schema.sql database must match a migrated one."""
        migrated = _dense_database()
        migrated.commit()
        migrated.executescript(MIGRATION.read_text(encoding="utf-8"))
        migrated_columns = [
            (row[1], row[2], row[3])
            for row in migrated.execute("PRAGMA table_info(product_pricing_overrides)")
        ]

        fresh = sqlite3.connect(":memory:")
        fresh.executescript(SCHEMA.read_text(encoding="utf-8"))
        fresh_columns = [
            (row[1], row[2], row[3])
            for row in fresh.execute("PRAGMA table_info(product_pricing_overrides)")
        ]

        self.assertEqual(fresh_columns, migrated_columns)
        migrated.close()
        fresh.close()


if __name__ == "__main__":
    unittest.main()
