"""Migration 0008: CAC gains a mode and the global engine moves to 5%."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/0008_percentage_cac.sql"
SCHEMA = ROOT / "schema.sql"

# The pre-0008 shape: a flat BDT `cac` on both tables, with no mode column.
FLAT_CAC_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE global_pricing_params (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  packaging REAL NOT NULL DEFAULT 45.0,
  transport REAL NOT NULL DEFAULT 0.0,
  delivery REAL NOT NULL DEFAULT 0.0,
  cac REAL NOT NULL DEFAULT 40.0,
  target_margin_pct REAL NOT NULL DEFAULT 0.0,
  discount_type TEXT NOT NULL DEFAULT 'pct',
  discount_val REAL NOT NULL DEFAULT 0.0,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE products (
  row_id INTEGER PRIMARY KEY, product_name TEXT NOT NULL, brand_name TEXT NOT NULL,
  manufactured_price REAL NOT NULL, market_average_price REAL NOT NULL
);
CREATE TABLE product_pricing_overrides (
  product_row_id INTEGER PRIMARY KEY,
  packaging REAL, transport REAL, delivery REAL, cac REAL,
  target_margin_pct REAL, discount_type TEXT, discount_val REAL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (product_row_id) REFERENCES products(row_id) ON DELETE CASCADE
);
"""


def _legacy_database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(FLAT_CAC_SCHEMA)
    connection.execute(
        "INSERT INTO global_pricing_params "
        "(id, packaging, transport, delivery, cac, target_margin_pct, discount_type, discount_val) "
        "VALUES (1, 45, 0, 0, 40, 0, 'pct', 0)"
    )
    for row_id, name, price in [(1, "Cheap Soap", 60.0), (2, "Costly Scent", 5000.0)]:
        connection.execute(
            "INSERT INTO products (row_id, product_name, brand_name, manufactured_price, market_average_price) "
            "VALUES (?, ?, 'Brand', ?, ?)",
            (row_id, name, price, price * 2),
        )
    # SKU 1 deliberately pins a flat 80 BDT CAC; SKU 2 pins only a margin.
    connection.execute("INSERT INTO product_pricing_overrides (product_row_id, cac) VALUES (1, 80)")
    connection.execute(
        "INSERT INTO product_pricing_overrides (product_row_id, target_margin_pct) VALUES (2, 30)"
    )
    connection.commit()
    return connection


def _migrated() -> sqlite3.Connection:
    connection = _legacy_database()
    connection.executescript(MIGRATION.read_text(encoding="utf-8"))
    return connection


class PercentageCacMigrationTest(unittest.TestCase):
    def test_global_engine_moves_to_five_percent(self) -> None:
        connection = _migrated()
        self.assertEqual(
            (5.0, "pct"),
            connection.execute("SELECT cac, cac_type FROM global_pricing_params").fetchone(),
        )
        connection.close()

    def test_flat_costs_survive_the_rebuild(self) -> None:
        connection = _migrated()
        self.assertEqual(
            (45.0, 0.0, 0.0, 0.0, "pct", 0.0),
            connection.execute(
                "SELECT packaging, transport, delivery, target_margin_pct, discount_type, discount_val "
                "FROM global_pricing_params"
            ).fetchone(),
        )
        connection.close()

    def test_a_pinned_cac_keeps_its_flat_bdt_meaning(self) -> None:
        """80 BDT must not silently become 80% of the sourcing price."""
        connection = _migrated()
        self.assertEqual(
            (80.0, "amt"),
            connection.execute(
                "SELECT cac, cac_type FROM product_pricing_overrides WHERE product_row_id = 1"
            ).fetchone(),
        )
        connection.close()

    def test_a_tune_that_pinned_no_cac_still_pins_none(self) -> None:
        connection = _migrated()
        self.assertEqual(
            (None, None, 30.0),
            connection.execute(
                "SELECT cac, cac_type, target_margin_pct FROM product_pricing_overrides "
                "WHERE product_row_id = 2"
            ).fetchone(),
        )
        connection.close()

    def test_rejects_half_a_cac_pair(self) -> None:
        connection = _migrated()
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO product_pricing_overrides (product_row_id, cac) VALUES (2, 25)"
            )
        connection.close()

    def test_rejects_a_percentage_above_one_hundred(self) -> None:
        connection = _migrated()
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("UPDATE global_pricing_params SET cac = 101 WHERE id = 1")
        connection.close()

    def test_schema_and_migration_agree_on_both_table_shapes(self) -> None:
        migrated = _migrated()
        fresh = sqlite3.connect(":memory:")
        fresh.executescript(SCHEMA.read_text(encoding="utf-8"))
        for table in ("global_pricing_params", "product_pricing_overrides"):
            with self.subTest(table=table):
                shape = lambda con: [  # noqa: E731
                    (row[1], row[2], row[3])
                    for row in con.execute(f"PRAGMA table_info({table})")
                ]
                self.assertEqual(shape(fresh), shape(migrated))
        migrated.close()
        fresh.close()


if __name__ == "__main__":
    unittest.main()
