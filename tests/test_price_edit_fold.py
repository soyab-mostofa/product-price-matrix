"""The durability contract: an edit must survive rebuild + sync.

This is the test the whole journal exists for. seed.sql re-inserts every local
product with `ON CONFLICT(row_id) DO UPDATE SET manufactured_price=excluded...`,
so an unfolded edit is reverted by the next `db:local:sync` while every command
still prints success — the same silent-revert that destroyed 80 verified
listings once.

Rather than mock the pipeline, these tests run the real fold logic against a
real SQLite replica and a real research-file structure, then apply a seed built
the same way build_matrix.py builds it.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLD_SCRIPT = ROOT / "scripts/fold_price_edits_into_research.py"
SYNC_SCRIPT = ROOT / "scripts/sync_local_d1.py"
SCHEMA = ROOT / "schema.sql"

# One local SKU, matching the real catalog's row 2.
ROW_ID = 2
NAME = "Bio-Screen Powder Sunblock SPF 50+"
WORKBOOK_COST = 1237.5
WORKBOOK_MRP = 1650.0
EDITED_COST = 1300.0

IMPORTED_ROW_ID = 500
IMPORTED_NAME = "Simple Face Wash Refreshing Gel 150ml (uk)"
IMPORTED_SHEET = "imported Skincare"
IMPORTED_SOURCE_ROW = 2
IMPORTED_COST = 425.0
IMPORTED_MRP = 749.0


def make_replica(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO products (row_id, product_name, brand_name, size, "
            "manufactured_price, market_average_price, canonical_name, "
            "mrp_source_type, sourcing_origin, source_sheet, source_row, "
            "workbook_source_cost, workbook_mrp) "
            "VALUES (?, ?, 'Bio-Screen', '12gm', ?, ?, ?, 'workbook', 'local', "
            "'Local product ', 2, ?, ?)",
            (ROW_ID, NAME, WORKBOOK_COST, WORKBOOK_MRP, NAME, WORKBOOK_COST, WORKBOOK_MRP),
        )
        connection.execute(
            "INSERT INTO products (row_id, product_name, brand_name, size, "
            "manufactured_price, market_average_price, canonical_name, "
            "mrp_source_type, sourcing_origin, category, source_sheet, source_row, "
            "workbook_source_cost, workbook_mrp) "
            "VALUES (?, ?, 'Simple', '150ml', ?, ?, ?, 'official', 'imported', "
            "'Skincare', ?, ?, ?, ?)",
            (
                IMPORTED_ROW_ID, IMPORTED_NAME, IMPORTED_COST, IMPORTED_MRP,
                IMPORTED_NAME, IMPORTED_SHEET, IMPORTED_SOURCE_ROW,
                IMPORTED_COST, IMPORTED_MRP,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def journal_edit(
    path: Path,
    field: str,
    old: float,
    new: float,
    row_id: int = ROW_ID,
    workbook_value: float | None = None,
    reverted: bool = False,
) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE products SET manufactured_price = ? WHERE row_id = ?"
            if field == "source_cost"
            else "UPDATE products SET market_average_price = ?, mrp_source_type = 'manual' WHERE row_id = ?",
            (new, row_id),
        )
        connection.execute(
            "INSERT INTO price_edits (product_row_id, field, old_value, "
            "new_value, workbook_value, folded, reverted) VALUES (?, ?, ?, ?, ?, 0, ?)",
            (row_id, field, old, new, old if workbook_value is None else workbook_value,
             1 if reverted else 0),
        )
        connection.commit()
    finally:
        connection.close()


def research_payload(cost: float, mrp: float) -> dict:
    return {
        "currency": "BDT",
        "product_count": 1,
        "products": [{
            "row": ROW_ID,
            "product_name": NAME,
            "brand_name": "Bio-Screen",
            "size": "12gm",
            "canonical_name": NAME,
            "excel_prices": {"manufactured_price": cost, "market_average_price": mrp},
            "sources": {},
            "mrp_source_type": "workbook",
            "market_average_price": mrp,
            "source_sheet": "Local product ",
            "source_row": 2,
        }],
    }


def seed_from_research(research: dict, local_edits: dict | None = None) -> str:
    """A build seed: workbook baseline first, manual pins applied last."""
    product = research["products"][0]
    prices = product["excel_prices"]
    statements = (
        "DELETE FROM marketplace_listings WHERE row_id IN "
        "(SELECT row_id FROM products WHERE sourcing_origin = 'local');\n"
        "INSERT INTO products (row_id, product_name, brand_name, size, "
        "manufactured_price, market_average_price, canonical_name, "
        "mrp_source_type, sourcing_origin, source_sheet, source_row, "
        "workbook_source_cost, workbook_mrp) VALUES "
        f"({product['row']}, '{product['product_name']}', 'Bio-Screen', '12gm', "
        f"{prices['manufactured_price']}, {prices['market_average_price']}, "
        f"'{product['canonical_name']}', 'workbook', 'local', 'Local product ', 2, "
        f"{prices['manufactured_price']}, {prices['market_average_price']}) "
        "ON CONFLICT(row_id) DO UPDATE SET "
        "manufactured_price=excluded.manufactured_price, "
        "market_average_price=excluded.market_average_price, "
        "mrp_source_type=excluded.mrp_source_type, "
        "workbook_source_cost=excluded.workbook_source_cost, "
        "workbook_mrp=excluded.workbook_mrp;\n"
    )
    for edit in (local_edits or {"edits": []})["edits"]:
        if edit.get("source_cost") is not None:
            statements += (
                f"UPDATE products SET manufactured_price={float(edit['source_cost'])} "
                "WHERE source_sheet='Local product ' AND source_row=2;\n"
            )
        if edit.get("mrp") is not None:
            statements += (
                f"UPDATE products SET market_average_price={float(edit['mrp'])}, "
                "mrp_source_type='manual' "
                "WHERE source_sheet='Local product ' AND source_row=2;\n"
            )
    return statements


def price_in(path: Path, column: str) -> float:
    connection = sqlite3.connect(path)
    try:
        return float(
            connection.execute(
                f"SELECT {column} FROM products WHERE row_id = ?", (ROW_ID,)
            ).fetchone()[0]
        )
    finally:
        connection.close()


class PriceEditFoldTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.replica = self.dir / "replica.sqlite"
        self.research = self.dir / "research.json"
        self.local_edits = self.dir / "local_price_edits.json"
        self.imported_edits = self.dir / "imported_price_edits.json"
        make_replica(self.replica)
        self.research.write_text(
            json.dumps(research_payload(WORKBOOK_COST, WORKBOOK_MRP), indent=2),
            encoding="utf-8",
        )
        self.local_edits.write_text(
            json.dumps({"version": 1, "edits": []}, indent=2),
            encoding="utf-8",
        )
        self.imported_edits.write_text(
            json.dumps({"version": 1, "edits": []}, indent=2),
            encoding="utf-8",
        )

    def run_fold(self, *extra: str) -> subprocess.CompletedProcess[str]:
        """Run the real fold script against this fixture's paths."""
        source = FOLD_SCRIPT.read_text(encoding="utf-8")
        patched = source.replace(
            'RESEARCH = ROOT / "verified_marketplace_research.json"',
            f'RESEARCH = Path({str(self.research)!r})',
        ).replace(
            'LOCAL_EDITS = ROOT / "local_price_edits.json"',
            f'LOCAL_EDITS = Path({str(self.local_edits)!r})',
        ).replace(
            'IMPORTED_EDITS = ROOT / "imported_price_edits.json"',
            f'IMPORTED_EDITS = Path({str(self.imported_edits)!r})',
        ).replace(
            'D1_DIR = ROOT / ".wrangler/state/v3/d1/miniflare-D1DatabaseObject"',
            f'D1_DIR = Path({str(self.dir)!r})',
        )
        script = self.dir / "fold_under_test.py"
        script.write_text(patched, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(script), *extra],
            capture_output=True, text=True,
        )

    def test_an_unfolded_edit_is_reverted_by_the_seed(self):
        """The bug this whole mechanism exists to prevent."""
        journal_edit(self.replica, "source_cost", WORKBOOK_COST, EDITED_COST)
        self.assertEqual(price_in(self.replica, "manufactured_price"), EDITED_COST)

        # Rebuild from the UNFOLDED research file, then sync.
        research = json.loads(self.research.read_text(encoding="utf-8"))
        connection = sqlite3.connect(self.replica)
        connection.executescript(seed_from_research(research))
        connection.commit()
        connection.close()

        self.assertEqual(
            price_in(self.replica, "manufactured_price"), WORKBOOK_COST,
            "without folding, the seed silently reverts the edit — this is the bug",
        )

    def test_a_folded_edit_survives_the_seed(self):
        """The contract: fold, rebuild, sync, and the edit is still there."""
        journal_edit(self.replica, "source_cost", WORKBOOK_COST, EDITED_COST)

        result = self.run_fold()
        self.assertEqual(result.returncode, 0, result.stderr)

        research = json.loads(self.research.read_text(encoding="utf-8"))
        self.assertEqual(
            research["products"][0]["excel_prices"]["manufactured_price"],
            WORKBOOK_COST,
            "the fold must never rewrite the immutable workbook mirror",
        )
        local = json.loads(self.local_edits.read_text(encoding="utf-8"))
        self.assertEqual(local["edits"][0]["source_cost"], EDITED_COST)

        connection = sqlite3.connect(self.replica)
        connection.executescript(seed_from_research(research, local))
        connection.commit()
        connection.close()

        self.assertEqual(
            price_in(self.replica, "manufactured_price"), EDITED_COST,
            "a folded edit must survive the rebuild that regenerates the seed",
        )

    def test_folding_marks_the_journal_rows(self):
        journal_edit(self.replica, "source_cost", WORKBOOK_COST, EDITED_COST)
        self.run_fold()

        connection = sqlite3.connect(self.replica)
        try:
            unfolded = connection.execute(
                "SELECT COUNT(*) FROM price_edits WHERE folded = 0"
            ).fetchone()[0]
            total = connection.execute("SELECT COUNT(*) FROM price_edits").fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(unfolded, 0, "folded rows must not be folded twice")
        self.assertEqual(total, 1, "the audit trail must be kept, not deleted")

    def test_only_the_latest_value_per_field_is_folded(self):
        journal_edit(self.replica, "source_cost", WORKBOOK_COST, 1300.0)
        journal_edit(self.replica, "source_cost", 1300.0, 1400.0)

        self.run_fold()
        artifact = json.loads(self.local_edits.read_text(encoding="utf-8"))
        self.assertEqual(artifact["edits"][0]["source_cost"], 1400.0)

    def test_an_mrp_edit_uses_a_separate_override_and_preserves_the_mirror(self):
        journal_edit(self.replica, "mrp", WORKBOOK_MRP, 1700.0)
        self.run_fold()

        product = json.loads(self.research.read_text(encoding="utf-8"))["products"][0]
        self.assertEqual(product["excel_prices"]["market_average_price"], WORKBOOK_MRP)
        self.assertEqual(product["market_average_price"], WORKBOOK_MRP)
        self.assertEqual(product["mrp_source_type"], "workbook")
        edit = json.loads(self.local_edits.read_text(encoding="utf-8"))["edits"][0]
        self.assertEqual(edit["mrp"], 1700.0)

    def test_imported_edits_fold_into_the_stable_workbook_key(self):
        """Imported row_ids can move; sheet + Excel row is the durable identity."""
        journal_edit(
            self.replica, "source_cost", IMPORTED_COST, 450.0,
            row_id=IMPORTED_ROW_ID,
        )
        journal_edit(
            self.replica, "mrp", IMPORTED_MRP, 800.0,
            row_id=IMPORTED_ROW_ID,
        )

        result = self.run_fold()
        self.assertEqual(result.returncode, 0, result.stderr)

        artifact = json.loads(self.imported_edits.read_text(encoding="utf-8"))
        self.assertEqual(artifact["version"], 1)
        self.assertEqual(len(artifact["edits"]), 1)
        edit = artifact["edits"][0]
        self.assertEqual(edit["source_sheet"], IMPORTED_SHEET)
        self.assertEqual(edit["source_row"], IMPORTED_SOURCE_ROW)
        self.assertEqual(edit["source_cost"], 450.0)
        self.assertEqual(edit["mrp"], 800.0)

        connection = sqlite3.connect(self.replica)
        try:
            unfolded = connection.execute(
                "SELECT COUNT(*) FROM price_edits WHERE product_row_id = ? AND folded = 0",
                (IMPORTED_ROW_ID,),
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(unfolded, 0)

    def test_imported_revert_removes_the_canonical_pin(self):
        """After a revert, the seeder must resolve from workbook/listings again."""
        journal_edit(
            self.replica, "mrp", IMPORTED_MRP, 800.0,
            row_id=IMPORTED_ROW_ID,
        )
        self.assertEqual(self.run_fold().returncode, 0)
        self.assertEqual(
            json.loads(self.imported_edits.read_text(encoding="utf-8"))["edits"][0]["mrp"],
            800.0,
        )

        journal_edit(
            self.replica, "mrp", 800.0, IMPORTED_MRP,
            row_id=IMPORTED_ROW_ID, workbook_value=IMPORTED_MRP,
            reverted=True,
        )
        self.assertEqual(self.run_fold().returncode, 0)
        artifact = json.loads(self.imported_edits.read_text(encoding="utf-8"))
        self.assertEqual(
            artifact["edits"], [],
            "revert must remove the manual pin, not pin the baseline as 'manual'",
        )

    def test_local_mrp_revert_removes_the_override_without_touching_the_mirror(self):
        journal_edit(self.replica, "mrp", WORKBOOK_MRP, 1700.0)
        self.assertEqual(self.run_fold().returncode, 0)
        first = json.loads(self.local_edits.read_text(encoding="utf-8"))["edits"][0]
        self.assertEqual(first["mrp"], 1700.0)

        journal_edit(
            self.replica, "mrp", 1700.0, WORKBOOK_MRP,
            workbook_value=WORKBOOK_MRP, reverted=True,
        )
        self.assertEqual(self.run_fold().returncode, 0)
        self.assertEqual(
            json.loads(self.local_edits.read_text(encoding="utf-8"))["edits"], []
        )
        product = json.loads(self.research.read_text(encoding="utf-8"))["products"][0]
        self.assertEqual(product["market_average_price"], WORKBOOK_MRP)
        self.assertEqual(product["mrp_source_type"], "workbook")

    def test_seed_imported_applies_manual_values_after_its_recompute(self):
        """Full imported contract: edit -> fold -> workbook seed -> edit survives."""
        journal_edit(
            self.replica, "source_cost", IMPORTED_COST, 450.0,
            row_id=IMPORTED_ROW_ID,
        )
        journal_edit(
            self.replica, "mrp", IMPORTED_MRP, 800.0,
            row_id=IMPORTED_ROW_ID,
        )
        self.assertEqual(self.run_fold().returncode, 0)

        module_path = ROOT / "scripts/seed_imported.py"
        spec = importlib.util.spec_from_file_location("seed_imported_under_test", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not load {module_path}")
        module = importlib.util.module_from_spec(spec)
        scripts_path = str(ROOT / "scripts")
        root_path = str(ROOT)
        sys.path[:0] = [scripts_path, root_path]
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path.remove(scripts_path)
            sys.path.remove(root_path)

        setattr(module, "IMPORTED_PRICE_EDITS_PATH", self.imported_edits)
        setattr(module, "REPORT_PATH", self.dir / "imported_seed_report.json")
        stats = module.seed(self.replica)
        self.assertGreater(stats["products_written"], 0)
        self.assertEqual(stats["manual_price_edits_applied"], 1)

        connection = sqlite3.connect(self.replica)
        try:
            product = connection.execute(
                "SELECT manufactured_price, market_average_price, mrp_source_type "
                "FROM products WHERE source_sheet = ? AND source_row = ?",
                (IMPORTED_SHEET, IMPORTED_SOURCE_ROW),
            ).fetchone()
        finally:
            connection.close()

        self.assertEqual(product[0], 450.0)
        self.assertEqual(product[1], 800.0)
        self.assertEqual(product[2], "manual")

    def test_dry_run_writes_nothing(self):
        journal_edit(self.replica, "source_cost", WORKBOOK_COST, EDITED_COST)
        before = self.research.read_text(encoding="utf-8")

        result = self.run_fold("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.research.read_text(encoding="utf-8"), before)

        connection = sqlite3.connect(self.replica)
        try:
            unfolded = connection.execute(
                "SELECT COUNT(*) FROM price_edits WHERE folded = 0"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(unfolded, 1, "a dry run must not mark anything folded")


class SyncGuardTests(unittest.TestCase):
    """The guard that makes forgetting to fold impossible rather than documented."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.replica = Path(self.tmp.name) / "replica.sqlite"
        make_replica(self.replica)

        module_path = ROOT / "scripts/sync_local_d1.py"
        spec = importlib.util.spec_from_file_location("sync_local_d1_under_test", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not load {module_path}")
        module = importlib.util.module_from_spec(spec)
        # sync_local_d1 imports migrate_local_d1 from the same directory.
        scripts_path = str(ROOT / "scripts")
        sys.path.insert(0, scripts_path)
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path.remove(scripts_path)
        self.unfolded_price_edits = module.unfolded_price_edits

    def test_a_clean_replica_is_not_flagged(self):
        self.assertEqual(self.unfolded_price_edits(self.replica), [])

    def test_an_unfolded_edit_is_flagged(self):
        journal_edit(self.replica, "source_cost", WORKBOOK_COST, EDITED_COST)
        flagged = self.unfolded_price_edits(self.replica)
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0][0], NAME)
        self.assertEqual(flagged[0][1], "source_cost")
        self.assertEqual(flagged[0][2], EDITED_COST)

    def test_an_unfolded_imported_edit_is_also_flagged(self):
        """seed_imported rewrites imported prices, so they need the same guard."""
        journal_edit(
            self.replica, "mrp", IMPORTED_MRP, 800.0,
            row_id=IMPORTED_ROW_ID,
        )
        flagged = self.unfolded_price_edits(self.replica)
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0][0], IMPORTED_NAME)
        self.assertEqual(flagged[0][1], "mrp")
        self.assertEqual(flagged[0][2], 800.0)

    def test_a_folded_edit_is_not_flagged(self):
        journal_edit(self.replica, "source_cost", WORKBOOK_COST, EDITED_COST)
        connection = sqlite3.connect(self.replica)
        connection.execute("UPDATE price_edits SET folded = 1")
        connection.commit()
        connection.close()

        self.assertEqual(self.unfolded_price_edits(self.replica), [])

    def test_the_sync_script_names_the_fold_command(self):
        """A refusal that does not say how to fix it just blocks the user."""
        text = SYNC_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("fold_price_edits_into_research.py", text)
        self.assertIn("--force", text)


if __name__ == "__main__":
    unittest.main()
