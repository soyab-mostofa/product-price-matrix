"""Immutable workbook baselines: migration, constraints, and revert semantics."""
from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schema.sql"
MIGRATION_0009 = ROOT / "migrations/0009_price_edits.sql"
MIGRATION_0010 = ROOT / "migrations/0010_workbook_baselines.sql"


def old_database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE products (
          row_id INTEGER PRIMARY KEY,
          product_name TEXT NOT NULL,
          brand_name TEXT NOT NULL,
          size TEXT,
          manufactured_price REAL NOT NULL,
          market_average_price REAL NOT NULL,
          canonical_name TEXT,
          mrp_source_type TEXT NOT NULL DEFAULT 'reference'
            CHECK (mrp_source_type IN ('official','third_party_avg','reference','workbook')),
          sourcing_origin TEXT NOT NULL DEFAULT 'local',
          category TEXT,
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          source_sheet TEXT,
          source_row INTEGER
        );
        INSERT INTO products
          (row_id, product_name, brand_name, manufactured_price,
           market_average_price, mrp_source_type, sourcing_origin,
           source_sheet, source_row)
        VALUES (2, 'Local SKU', 'Brand', 1237.5, 1650, 'workbook', 'local',
                'Local product ', 2);
        """
    )
    connection.executescript(MIGRATION_0009.read_text(encoding="utf-8"))
    return connection


class WorkbookBaselineMigrationTests(unittest.TestCase):
    def test_backfills_immutable_baselines_from_a_parity_clean_database(self):
        connection = old_database()
        self.addCleanup(connection.close)
        connection.executescript(MIGRATION_0010.read_text(encoding="utf-8"))

        row = connection.execute(
            "SELECT manufactured_price, market_average_price, "
            "workbook_source_cost, workbook_mrp FROM products WHERE row_id = 2"
        ).fetchone()
        self.assertEqual(row, (1237.5, 1650.0, 1237.5, 1650.0))

    def test_backfill_uses_journal_baseline_when_current_value_is_an_override(self):
        connection = old_database()
        self.addCleanup(connection.close)
        connection.execute(
            "UPDATE products SET manufactured_price = 1400, "
            "market_average_price = 1700, mrp_source_type = 'manual' WHERE row_id = 2"
        )
        connection.execute(
            "INSERT INTO price_edits "
            "(product_row_id, field, old_value, new_value, workbook_value) "
            "VALUES (2, 'source_cost', 1237.5, 1400, 1237.5)"
        )
        connection.execute(
            "INSERT INTO price_edits "
            "(product_row_id, field, old_value, new_value, workbook_value) "
            "VALUES (2, 'mrp', 1650, 1700, 1650)"
        )
        connection.executescript(MIGRATION_0010.read_text(encoding="utf-8"))

        row = connection.execute(
            "SELECT manufactured_price, market_average_price, "
            "workbook_source_cost, workbook_mrp FROM products WHERE row_id = 2"
        ).fetchone()
        self.assertEqual(row, (1400.0, 1700.0, 1237.5, 1650.0))

    def test_current_price_can_change_without_changing_the_baseline(self):
        connection = old_database()
        self.addCleanup(connection.close)
        connection.executescript(MIGRATION_0010.read_text(encoding="utf-8"))
        connection.execute(
            "UPDATE products SET manufactured_price = 1400, "
            "market_average_price = 1700, mrp_source_type = 'manual' WHERE row_id = 2"
        )

        row = connection.execute(
            "SELECT manufactured_price, market_average_price, "
            "workbook_source_cost, workbook_mrp FROM products WHERE row_id = 2"
        ).fetchone()
        self.assertEqual(row, (1400.0, 1700.0, 1237.5, 1650.0))

    def test_a_revert_is_explicit_even_when_the_resolved_value_does_not_equal_the_baseline(self):
        connection = old_database()
        self.addCleanup(connection.close)
        connection.executescript(MIGRATION_0010.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO price_edits "
            "(product_row_id, field, old_value, new_value, workbook_value, reverted) "
            "VALUES (2, 'mrp', 900, 799, 749, 1)"
        )
        row = connection.execute(
            "SELECT new_value, workbook_value, reverted FROM price_edits"
        ).fetchone()
        self.assertEqual(row, (799.0, 749.0, 1))

    def test_a_provenance_only_revert_may_keep_the_same_number(self):
        connection = old_database()
        self.addCleanup(connection.close)
        connection.executescript(MIGRATION_0010.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO price_edits "
            "(product_row_id, field, old_value, new_value, workbook_value, reverted) "
            "VALUES (2, 'mrp', 799, 799, 749, 1)"
        )
        self.assertEqual(
            connection.execute("SELECT reverted FROM price_edits").fetchone()[0], 1
        )

    def test_a_normal_no_op_edit_is_still_rejected(self):
        connection = old_database()
        self.addCleanup(connection.close)
        connection.executescript(MIGRATION_0010.read_text(encoding="utf-8"))
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO price_edits "
                "(product_row_id, field, old_value, new_value, workbook_value) "
                "VALUES (2, 'source_cost', 1237.5, 1237.5, 1237.5)"
            )

    def test_fresh_schema_and_migration_have_the_same_final_columns(self):
        migrated = old_database()
        self.addCleanup(migrated.close)
        migrated.executescript(MIGRATION_0010.read_text(encoding="utf-8"))

        fresh = sqlite3.connect(":memory:")
        self.addCleanup(fresh.close)
        fresh.executescript(SCHEMA.read_text(encoding="utf-8"))

        for table in ("products", "price_edits"):
            migrated_columns = [row[1:4] for row in migrated.execute(f"PRAGMA table_info({table})")]
            fresh_columns = [row[1:4] for row in fresh.execute(f"PRAGMA table_info({table})")]
            self.assertEqual(migrated_columns, fresh_columns)


if __name__ == "__main__":
    unittest.main()
