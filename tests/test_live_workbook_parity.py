"""The live parity gate's comparison logic, without touching the network."""
from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import verify_live_workbook_parity as gate  # noqa: E402


def product(**overrides) -> dict:
    base = {
        "row": 2,
        "product_name": "Bio-Screen Powder Sunblock SPF 50+",
        "manufactured_price": 1237.5,
        "market_average_price": 1650.0,
        "sourcing_origin": "local",
        "source_sheet": "Local product ",
        "source_row": 5,
        "source_cost_edited_at": None,
        "mrp_edited_at": None,
    }
    base.update(overrides)
    return base


EXPECTED = {("Local product ", 5): {"cost": Decimal("1237.5"), "mrp": Decimal("1650")}}


def run(products, expected=None, argv=()):
    """Drive main() with the network and workbook stubbed out."""
    with mock.patch.object(gate, "fetch_products", return_value=products), \
         mock.patch.object(gate, "workbook_by_provenance",
                           return_value=dict(expected or EXPECTED)), \
         mock.patch.object(sys, "argv", ["verify_live_workbook_parity.py", *argv]):
        return gate.main()


class LiveParityGateTests(unittest.TestCase):
    def test_matching_production_passes(self):
        self.assertEqual(run([product()]), 0)

    def test_source_cost_drift_fails(self):
        """The exact shape that went unnoticed in production for ~7 hours."""
        self.assertEqual(run([product(manufactured_price=499.0)]), 1)

    def test_local_mrp_drift_fails(self):
        self.assertEqual(run([product(market_average_price=1700.0)]), 1)

    def test_a_paisa_of_float_noise_is_tolerated(self):
        self.assertEqual(run([product(manufactured_price=1237.504)]), 0)

    def test_missing_provenance_fails(self):
        self.assertEqual(run([product(source_sheet=None, source_row=None)]), 1)

    def test_provenance_naming_no_workbook_row_fails(self):
        self.assertEqual(run([product(source_row=9999)]), 1)

    def test_imported_mrp_is_never_compared_to_the_workbook(self):
        """An imported MRP resolves from live listings, so it cannot drift."""
        expected = {("imported Skincare", 7): {"cost": Decimal("425"), "mrp": None}}
        sku = product(
            sourcing_origin="imported", source_sheet="imported Skincare",
            source_row=7, manufactured_price=425.0, market_average_price=999.0,
        )
        self.assertEqual(run([sku], expected), 0)

    def test_an_edit_is_drift_by_default(self):
        """The gate answers 'does production match the workbook', not 'was this deliberate'."""
        edited = product(manufactured_price=1400.0,
                         source_cost_edited_at="2026-09-08T05:24:00.000Z")
        self.assertEqual(run([edited]), 1)

    def test_allow_edited_downgrades_an_explained_difference(self):
        edited = product(manufactured_price=1400.0,
                         source_cost_edited_at="2026-09-08T05:24:00.000Z")
        self.assertEqual(run([edited], argv=("--allow-edited",)), 0)

    def test_allow_edited_still_fails_unexplained_drift(self):
        """--allow-edited must not become a blanket pass."""
        self.assertEqual(run([product(manufactured_price=1400.0)],
                             argv=("--allow-edited",)), 1)


if __name__ == "__main__":
    unittest.main()
