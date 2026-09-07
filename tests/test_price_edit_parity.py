"""Journal-aware workbook parity: deliberate edits pass, corruption still fails."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sqlite3
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/verify_workbook_parity.py"

scripts_path = str(ROOT / "scripts")
root_path = str(ROOT)
sys.path[:0] = [scripts_path, root_path]
try:
    spec = importlib.util.spec_from_file_location("verify_workbook_parity_under_test", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {MODULE_PATH}")
    parity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parity)
finally:
    sys.path.remove(scripts_path)
    sys.path.remove(root_path)


def database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE price_edits (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          product_row_id INTEGER NOT NULL,
          field TEXT NOT NULL,
          old_value REAL NOT NULL,
          new_value REAL NOT NULL,
          workbook_value REAL,
          edited_at TEXT NOT NULL
        );
        """
    )
    return connection


def add_edit(
    connection: sqlite3.Connection,
    field: str,
    old: float,
    new: float,
    workbook: float,
    at: str = "2026-09-07T10:00:00Z",
) -> None:
    connection.execute(
        "INSERT INTO price_edits "
        "(product_row_id, field, old_value, new_value, workbook_value, edited_at) "
        "VALUES (2, ?, ?, ?, ?, ?)",
        (field, old, new, workbook, at),
    )


class ActivePriceEditTests(unittest.TestCase):
    def test_a_non_reverted_edit_is_active(self):
        connection = database()
        self.addCleanup(connection.close)
        add_edit(connection, "source_cost", 1237.5, 1300.0, 1237.5)

        edits = parity.active_price_edits(connection)
        self.assertIn((2, "source_cost"), edits)
        self.assertEqual(edits[(2, "source_cost")]["new_value"], 1300.0)

    def test_only_the_latest_edit_per_field_counts(self):
        connection = database()
        self.addCleanup(connection.close)
        add_edit(connection, "source_cost", 1237.5, 1300.0, 1237.5, "2026-09-07T10:00:00Z")
        add_edit(connection, "source_cost", 1300.0, 1400.0, 1237.5, "2026-09-07T11:00:00Z")

        edits = parity.active_price_edits(connection)
        self.assertEqual(edits[(2, "source_cost")]["new_value"], 1400.0)

    def test_a_latest_revert_is_not_an_active_edit(self):
        connection = database()
        self.addCleanup(connection.close)
        add_edit(connection, "mrp", 1650.0, 1700.0, 1650.0)
        add_edit(connection, "mrp", 1700.0, 1650.0, 1650.0, "2026-09-07T12:00:00Z")

        self.assertNotIn((2, "mrp"), parity.active_price_edits(connection))

    def test_an_edit_explains_only_the_exact_current_and_workbook_values(self):
        connection = database()
        self.addCleanup(connection.close)
        add_edit(connection, "source_cost", 1237.5, 1300.0, 1237.5)
        edit = parity.active_price_edits(connection)[(2, "source_cost")]

        self.assertTrue(
            parity.edit_explains(edit, Decimal("1300"), Decimal("1237.5"))
        )
        self.assertFalse(
            parity.edit_explains(edit, Decimal("1400"), Decimal("1237.5")),
            "a journal row must not excuse a different D1 value",
        )
        self.assertFalse(
            parity.edit_explains(edit, Decimal("1300"), Decimal("1200")),
            "a journal row must also match the real workbook baseline",
        )

    def test_no_journal_never_excuses_drift(self):
        self.assertFalse(
            parity.edit_explains(None, Decimal("1300"), Decimal("1237.5"))
        )


class FullParityCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "catalog.sqlite"
        connection = sqlite3.connect(self.path)
        connection.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO products (row_id, product_name, brand_name, size, "
            "manufactured_price, market_average_price, canonical_name, "
            "mrp_source_type, sourcing_origin, source_sheet, source_row) "
            "VALUES (2, 'Bio-Screen Powder Sunblock SPF 50+', 'Bio-Screen', "
            "'12gm', 1300, 1650, 'Bio-Screen Powder Sunblock SPF 50+', "
            "'workbook', 'local', 'Local product ', 2)"
        )
        connection.execute(
            "INSERT INTO price_edits (product_row_id, field, old_value, new_value, "
            "workbook_value, edited_at, folded) VALUES "
            "(2, 'source_cost', 1237.5, 1300, 1237.5, '2026-09-07T10:00:00Z', 1)"
        )
        connection.commit()
        connection.close()

    def run_parity(self) -> tuple[int, str]:
        original_replica = getattr(parity, "replica")
        original_argv = sys.argv
        setattr(parity, "replica", lambda: self.path)
        sys.argv = ["verify_workbook_parity.py"]
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output):
                result = parity.main()
        finally:
            setattr(parity, "replica", original_replica)
            sys.argv = original_argv
        return result, output.getvalue()

    def test_a_matching_journalled_edit_passes_the_full_gate(self):
        result, output = self.run_parity()
        self.assertEqual(result, 0, output)
        self.assertIn("Deliberate price edits (1)", output)
        self.assertIn("workbook 1237.5 -> D1 1300", output)
        self.assertIn("PASS — 0 problem(s)", output)

    def test_unjournalled_drift_still_fails_the_full_gate(self):
        connection = sqlite3.connect(self.path)
        connection.execute(
            "UPDATE products SET manufactured_price = 1400 WHERE row_id = 2"
        )
        connection.commit()
        connection.close()

        result, output = self.run_parity()
        self.assertEqual(result, 1)
        self.assertIn("no matching active edit", output)
        self.assertIn("FAIL — 1 problem(s)", output)


if __name__ == "__main__":
    unittest.main()
