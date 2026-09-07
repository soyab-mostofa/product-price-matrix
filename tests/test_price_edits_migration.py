"""The price_edits journal: shape, constraints, and the durability guarantee.

The grep test at the bottom is the important one. seed.sql re-inserts every
local row with `ON CONFLICT(row_id) DO UPDATE SET manufactured_price=...`, so
if a future seed change ever started writing price_edits too, an edit would be
silently reverted by the next rebuild — the same failure that destroyed 80
verified listings once. Pinning the absence in a test makes that regression
loud instead of silent.
"""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/0009_price_edits.sql"
SCHEMA_PATH = ROOT / "schema.sql"
SEED_PATH = ROOT / "seed.sql"


def _price_edits_migration() -> str:
    """The migration body, minus any transaction/pragma wrapper.

    Mirrors migrate_local_d1._unwrapped: the caller owns the transaction and
    sqlite3 refuses a nested BEGIN.
    """
    skipped = ("PRAGMA foreign_keys", "BEGIN TRANSACTION;", "COMMIT;")
    return "\n".join(
        line for line in MIGRATION.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith(skipped)
    )


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def _products_stub(connection: sqlite3.Connection) -> None:
    """A products table matching the post-0007 shape.

    0009 rebuilds `products` to widen mrp_source_type, so its SELECT names every
    column the real table has. A minimal stub would fail on the first missing
    one — which is the point: this stub has to track the real schema.
    """
    connection.executescript(
        """
        CREATE TABLE products (
          row_id INTEGER PRIMARY KEY,
          product_name TEXT NOT NULL,
          brand_name TEXT NOT NULL,
          size TEXT,
          manufactured_price REAL NOT NULL CHECK (manufactured_price >= 0),
          market_average_price REAL NOT NULL CHECK (market_average_price >= 0),
          canonical_name TEXT,
          mrp_source_type TEXT NOT NULL DEFAULT 'reference'
            CHECK (mrp_source_type IN ('official', 'third_party_avg', 'reference', 'workbook')),
          sourcing_origin TEXT NOT NULL DEFAULT 'local'
            CHECK (sourcing_origin IN ('local', 'imported')),
          category TEXT,
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          source_sheet TEXT,
          source_row INTEGER CHECK (source_row IS NULL OR source_row > 1)
        );
        INSERT INTO products
          (row_id, product_name, brand_name, size, manufactured_price,
           market_average_price, canonical_name, mrp_source_type,
           sourcing_origin, source_sheet, source_row)
        VALUES
          (2, 'Bio-Screen Powder Sunblock SPF 50+', 'Bio-Screen', '12gm',
           1237.5, 1650.0, 'Bio-Screen Powder Sunblock SPF 50+', 'workbook',
           'local', 'Local product ', 2);
        """
    )


def _migrated() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    _products_stub(connection)
    connection.executescript(_price_edits_migration())
    return connection


def columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


class PriceEditsMigrationTests(unittest.TestCase):
    def test_migration_creates_the_journal(self):
        connection = _migrated()
        self.addCleanup(connection.close)
        self.assertTrue(table_exists(connection, "price_edits"))
        self.assertEqual(
            columns(connection, "price_edits"),
            {
                "id", "product_row_id", "field", "old_value", "new_value",
                "workbook_value", "edited_at", "folded",
            },
        )

    def test_migration_is_idempotent(self):
        """A second run must not fail — the migrator may re-apply on any replica."""
        connection = _migrated()
        self.addCleanup(connection.close)
        connection.executescript(_price_edits_migration())
        self.assertTrue(table_exists(connection, "price_edits"))

    def test_schema_and_migration_agree_on_journal_shape(self):
        """A fresh schema.sql database must match a migrated one."""
        fresh = sqlite3.connect(":memory:")
        self.addCleanup(fresh.close)
        fresh.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

        migrated = _migrated()
        self.addCleanup(migrated.close)

        self.assertEqual(columns(fresh, "price_edits"), columns(migrated, "price_edits"))

    def test_field_is_constrained_to_the_two_editable_prices(self):
        connection = _migrated()
        self.addCleanup(connection.close)
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO price_edits (product_row_id, field, old_value, new_value) "
                "VALUES (2, 'discount_rate', 1237.5, 1300.0)"
            )

    def test_a_no_op_edit_is_rejected(self):
        """An edit that changes nothing is noise in an audit log."""
        connection = _migrated()
        self.addCleanup(connection.close)
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO price_edits (product_row_id, field, old_value, new_value) "
                "VALUES (2, 'source_cost', 1237.5, 1237.5)"
            )

    def test_negative_prices_are_rejected(self):
        connection = _migrated()
        self.addCleanup(connection.close)
        for old, new in ((-1.0, 1300.0), (1237.5, -1.0)):
            with self.subTest(old=old, new=new):
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        "INSERT INTO price_edits (product_row_id, field, old_value, new_value) "
                        "VALUES (2, 'source_cost', ?, ?)",
                        (old, new),
                    )

    def test_an_edit_records_its_workbook_baseline_and_starts_unfolded(self):
        connection = _migrated()
        self.addCleanup(connection.close)
        connection.execute(
            "INSERT INTO price_edits (product_row_id, field, old_value, new_value, workbook_value) "
            "VALUES (2, 'source_cost', 1237.5, 1300.0, 1237.5)"
        )
        row = connection.execute(
            "SELECT field, old_value, new_value, workbook_value, folded FROM price_edits"
        ).fetchone()
        self.assertEqual(row[0], "source_cost")
        self.assertAlmostEqual(row[3], 1237.5)
        self.assertEqual(row[4], 0, "a new edit is unfolded until the fold script runs")

    def test_successive_edits_keep_the_workbook_baseline(self):
        """revert-to-workbook must reach the workbook, not the previous edit."""
        connection = _migrated()
        self.addCleanup(connection.close)
        connection.execute(
            "INSERT INTO price_edits (product_row_id, field, old_value, new_value, workbook_value) "
            "VALUES (2, 'source_cost', 1237.5, 1300.0, 1237.5)"
        )
        connection.execute(
            "INSERT INTO price_edits (product_row_id, field, old_value, new_value, workbook_value) "
            "VALUES (2, 'source_cost', 1300.0, 1400.0, 1237.5)"
        )
        baselines = {
            row[0] for row in connection.execute("SELECT workbook_value FROM price_edits")
        }
        self.assertEqual(baselines, {1237.5})

    def test_edits_cascade_when_their_product_goes_away(self):
        connection = _migrated()
        self.addCleanup(connection.close)
        connection.execute(
            "INSERT INTO price_edits (product_row_id, field, old_value, new_value) "
            "VALUES (2, 'mrp', 1650.0, 1700.0)"
        )
        connection.execute("DELETE FROM products WHERE row_id = 2")
        self.assertEqual(
            connection.execute("SELECT COUNT(*) FROM price_edits").fetchone()[0], 0
        )

    def test_seed_never_writes_the_journal(self):
        """The durability guarantee, pinned.

        seed.sql rewrites `products` wholesale on every rebuild. The journal is
        what survives that and feeds the edits back in. If a seed ever started
        carrying price_edits rows, the rebuild would clobber the very record
        that repairs it.
        """
        if not SEED_PATH.exists():
            self.skipTest("seed.sql not generated in this checkout")
        seed_sql = SEED_PATH.read_text(encoding="utf-8")

        # assertNotIn would dump the whole 50KB seed into the failure message,
        # burying the finding. Report the offending line numbers instead.
        offenders = [
            number for number, line in enumerate(seed_sql.splitlines(), start=1)
            if "price_edits" in line
        ]
        self.assertEqual(
            offenders, [],
            f"seed.sql references price_edits on line(s) {offenders} — the journal "
            "is what survives a rebuild, so a seed that touches it defeats its "
            "purpose and edits will be silently reverted by db:local:sync",
        )


class ManualMrpProvenanceTests(unittest.TestCase):
    """0009's second half: products.mrp_source_type must accept 'manual'.

    An edited MRP is not the workbook benchmark. Leaving it labelled 'workbook'
    would let an edited figure claim an authority the workbook no longer backs —
    the exact confusion migration 0006 was written to remove.
    """

    def test_manual_is_a_legal_provenance_after_migration(self):
        connection = _migrated()
        self.addCleanup(connection.close)
        connection.execute(
            "UPDATE products SET mrp_source_type = 'manual' WHERE row_id = 2"
        )
        self.assertEqual(
            connection.execute(
                "SELECT mrp_source_type FROM products WHERE row_id = 2"
            ).fetchone()[0],
            "manual",
        )

    def test_junk_provenance_is_still_rejected(self):
        """Widening the CHECK must not turn it into a free-text column."""
        connection = _migrated()
        self.addCleanup(connection.close)
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE products SET mrp_source_type = 'guesswork' WHERE row_id = 2"
            )

    def test_the_rebuild_preserves_workbook_provenance(self):
        """The riskiest part of 0009: products is dropped and recreated.

        source_sheet/source_row come from 0007 and are what lets an on-screen
        figure be walked back to an Excel cell. Losing them in the rebuild would
        pass every other test and quietly break traceability.
        """
        connection = _migrated()
        self.addCleanup(connection.close)
        row = connection.execute(
            "SELECT product_name, brand_name, size, manufactured_price, "
            "market_average_price, mrp_source_type, sourcing_origin, "
            "source_sheet, source_row FROM products WHERE row_id = 2"
        ).fetchone()
        self.assertEqual(row[0], "Bio-Screen Powder Sunblock SPF 50+")
        self.assertEqual(row[1], "Bio-Screen")
        self.assertEqual(row[2], "12gm")
        self.assertAlmostEqual(row[3], 1237.5)
        self.assertAlmostEqual(row[4], 1650.0)
        self.assertEqual(row[5], "workbook", "the rebuild must not reclassify a row")
        self.assertEqual(row[6], "local")
        self.assertEqual(row[7], "Local product ")
        self.assertEqual(row[8], 2)

    def test_schema_and_migration_agree_on_product_shape(self):
        """A fresh schema.sql database must match a migrated one."""
        fresh = sqlite3.connect(":memory:")
        self.addCleanup(fresh.close)
        fresh.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

        migrated = _migrated()
        self.addCleanup(migrated.close)

        self.assertEqual(columns(fresh, "products"), columns(migrated, "products"))

    def test_the_brand_and_origin_indexes_survive_the_rebuild(self):
        """DROP TABLE takes its indexes with it; the migration must restore them."""
        connection = _migrated()
        self.addCleanup(connection.close)
        indexes = {
            str(row[0]) for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'products'"
            )
        }
        self.assertIn("idx_products_brand", indexes)
        self.assertIn("idx_products_origin", indexes)


if __name__ == "__main__":
    unittest.main()
