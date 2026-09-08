from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import catalog_builder
from catalog_builder import (
    DEFAULT_GLOBAL_PARAMS,
    CatalogValidationError,
    build_public_data,
    generate_seed_sql,
)


class CatalogBuilderTests(unittest.TestCase):
    def make_research(self, products: list[dict]) -> dict:
        return {
            "currency": "BDT",
            "currency_symbol": "৳",
            "source_excel": "product_marketplace_price_comparison.xlsx",
            "internal_price_basis": "test fixture",
            "matching_policy": {
                "brand_required": True,
                "product_type_required": True,
                "size_required_when_present": True,
                "variant_and_shade_required": True,
                "bundles_rejected_for_single_skus": True,
                "unverified_sources_omitted": True,
            },
            "generated_at": "2026-09-02T00:00:00Z",
            "products": products,
        }

    def product(self, *, sources: dict, market_average_price: float = 999) -> dict:
        return {
            "row": 1,
            "product_name": "Example Vitamin C Serum",
            "brand_name": "Example",
            "size": "30ml",
            "canonical_name": "Example Vitamin C Serum",
            "excel_prices": {
                "manufactured_price": 100,
                "market_average_price": market_average_price,
            },
            "sources": sources,
        }

    def listing(self, price: float, *, available: bool = True, title: str | None = None) -> dict:
        return {
            "price": price,
            "url": "https://example.com/vitamin-c-serum-30ml",
            "matched_title": title or "Example Vitamin C Serum 30ml",
            "size": "30ml",
            "seller": "Example",
            "confidence": 100,
            "available": available,
        }

    def test_unavailable_listings_are_excluded_from_public_metrics(self) -> None:
        research = self.make_research([
            self.product(sources={
                "Official Store": self.listing(300, available=False),
                "Arogga": self.listing(200),
            })
        ])

        output, _ = build_public_data(research, strict=True)

        product = output["products"][0]
        self.assertEqual({"Arogga"}, set(product["sources"]))
        self.assertEqual({"Arogga": 1}, output["source_listing_counts"])

    def test_workbook_mrp_beats_the_official_store_price(self) -> None:
        """A brand store price is a live listing, not the sourcing benchmark.

        The workbook's cost basis is a trade discount off its own MRP, so
        letting a promotional store price overwrite it breaks that arithmetic
        and can make a healthy margin read as a loss.
        """
        research = self.make_research([
            self.product(sources={
                "Official Store": self.listing(250),
                "Arogga": self.listing(200),
            })
        ])

        output, _ = build_public_data(research, strict=True)

        product = output["products"][0]
        # 999.0 is the workbook Mkt (Avg) Price supplied by `self.product`.
        self.assertEqual(999.0, product["market_average_price"])
        self.assertEqual("workbook", product["mrp_source_type"])
        # The scraped listings survive untouched, deep links and all.
        self.assertEqual({"Official Store", "Arogga"}, set(product["sources"]))
        self.assertEqual(250, product["sources"]["Official Store"]["price"])
        self.assertTrue(product["sources"]["Official Store"]["url"])

    def test_a_local_sku_without_a_workbook_mrp_fails_strict_build(self) -> None:
        research = self.make_research([
            self.product(market_average_price=0, sources={"Arogga": self.listing(200)})
        ])

        with self.assertRaises(CatalogValidationError):
            build_public_data(research, strict=True)

    def test_invalid_active_listing_fails_strict_build(self) -> None:
        research = self.make_research([
            self.product(sources={
                "Arogga": self.listing(200, title="Example Vitamin C Toner 30ml"),
            })
        ])

        with self.assertRaises(CatalogValidationError):
            build_public_data(research, strict=True)

    def test_catalog_rejects_non_finite_and_out_of_range_numbers(self) -> None:
        invalid_cases = [
            self.product(sources={"Arogga": self.listing(0)}),
            self.product(sources={"Arogga": {**self.listing(200), "confidence": 101}}),
            {
                **self.product(sources={"Arogga": self.listing(200)}),
                "excel_prices": {"manufactured_price": float("nan"), "market_average_price": 999},
            },
            {
                **self.product(sources={"Arogga": self.listing(200)}),
                "excel_prices": {"manufactured_price": 100, "market_average_price": float("inf")},
            },
        ]

        for product in invalid_cases:
            with self.subTest(product=product):
                with self.assertRaises(ValueError):
                    build_public_data(self.make_research([product]), strict=True)

    def test_catalog_rejects_duplicate_product_row_ids(self) -> None:
        first = self.product(sources={"Official Store": self.listing(250)})
        second = {
            **self.product(sources={"Arogga": self.listing(200)}),
            "product_name": "Another Example Serum",
        }

        with self.assertRaisesRegex(ValueError, "duplicate product row ID"):
            build_public_data(self.make_research([first, second]), strict=True)

    def test_seed_marks_listings_with_a_product_page_as_verified(self) -> None:
        """The deep link only renders for verified rows, so the seed must set it.

        Leaving `verified` to its column default silently downgraded every
        seeded listing to unverified, replacing the ↗ link with the ◌ marker.
        """
        research = self.make_research([
            self.product(sources={"Official Store": self.listing(250)})
        ])
        output, _ = build_public_data(research, strict=True)

        sql = generate_seed_sql(output)

        self.assertIn("available, verified", sql)
        listing_insert = next(
            line for line in sql.splitlines()
            if line.startswith("INSERT INTO marketplace_listings")
        )
        # A listing carrying a product page URL is verified.
        self.assertTrue(
            listing_insert.rstrip().endswith("1, 1);"),
            msg=listing_insert,
        )

    def test_seed_uses_product_row_id_overrides_and_canonical_defaults(self) -> None:
        research = self.make_research([
            self.product(sources={"Official Store": self.listing(250)})
        ])
        output, _ = build_public_data(research, strict=True)

        sql = generate_seed_sql(output)

        self.assertIn("row_id", sql)
        self.assertIn("45.0, 0.0, 0.0, 40.0, 0.0, 'pct', 0.0", sql)
        self.assertEqual(0, DEFAULT_GLOBAL_PARAMS["targetMarginPct"])

    def test_seed_preserves_saved_global_pricing_configuration(self) -> None:
        research = self.make_research([
            self.product(sources={"Official Store": self.listing(250)})
        ])
        output, _ = build_public_data(research, strict=True)

        connection = sqlite3.connect(":memory:")
        connection.executescript(
            (Path(__file__).resolve().parents[1] / "schema.sql").read_text(encoding="utf-8")
        )
        connection.execute(
            "INSERT INTO global_pricing_params "
            "(id, packaging, transport, delivery, cac, target_margin_pct, discount_type, discount_val) "
            "VALUES (1, 99, 88, 77, 66, 25, 'pct', 10)"
        )
        connection.executescript(generate_seed_sql(output))

        saved = connection.execute(
            "SELECT packaging, transport, delivery, cac, target_margin_pct, discount_type, discount_val "
            "FROM global_pricing_params WHERE id = 1"
        ).fetchone()
        connection.close()

        self.assertEqual((99.0, 88.0, 77.0, 66.0, 25.0, "pct", 10.0), saved)

    def test_seed_bootstraps_defaults_when_no_configuration_exists(self) -> None:
        research = self.make_research([
            self.product(sources={"Official Store": self.listing(250)})
        ])
        output, _ = build_public_data(research, strict=True)

        connection = sqlite3.connect(":memory:")
        connection.executescript(
            (Path(__file__).resolve().parents[1] / "schema.sql").read_text(encoding="utf-8")
        )
        connection.executescript(generate_seed_sql(output))

        saved = connection.execute(
            "SELECT packaging, transport, delivery, cac, target_margin_pct, discount_type, discount_val "
            "FROM global_pricing_params WHERE id = 1"
        ).fetchone()
        products = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        listings = connection.execute("SELECT COUNT(*) FROM marketplace_listings").fetchone()[0]
        connection.close()

        self.assertEqual((45.0, 0.0, 0.0, 40.0, 0.0, "pct", 0.0), saved)
        self.assertEqual(1, products)
        self.assertEqual(1, listings)

    def test_real_seed_applies_local_pins_without_mutating_workbook_baselines(self) -> None:
        research = self.make_research([
            self.product(sources={"Official Store": self.listing(250)})
        ])
        output, _ = build_public_data(research, strict=True)
        product = output["products"][0]
        product["row"] = 2
        product["source_sheet"] = "Local product "
        product["source_row"] = 2

        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "local_price_edits.json"
            artifact.write_text(json.dumps({
                "version": 1,
                "edits": [{
                    "source_sheet": "Local product ", "source_row": 2,
                    "product_name": product["product_name"],
                    "source_cost": 130, "mrp": 1100,
                }],
            }), encoding="utf-8")
            original = catalog_builder.LOCAL_PRICE_EDITS_PATH
            catalog_builder.LOCAL_PRICE_EDITS_PATH = artifact
            try:
                sql = generate_seed_sql(output)
            finally:
                catalog_builder.LOCAL_PRICE_EDITS_PATH = original

        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        connection.executescript(
            (Path(__file__).resolve().parents[1] / "schema.sql").read_text(encoding="utf-8")
        )
        connection.executescript(sql)
        row = connection.execute(
            "SELECT manufactured_price, market_average_price, mrp_source_type, "
            "workbook_source_cost, workbook_mrp FROM products WHERE row_id = 2"
        ).fetchone()
        self.assertEqual(row, (130.0, 1100.0, "manual", 100.0, 999.0))

    def test_repo_build_outputs_are_reproducible(self) -> None:
        root = Path(__file__).resolve().parents[1]
        research = json.loads((root / "verified_marketplace_research.json").read_text(encoding="utf-8"))
        output, _ = build_public_data(research, strict=True)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            (tmp_root / "public").mkdir()
            expected = json.dumps(output, ensure_ascii=False, indent=2) + "\n"
            (tmp_root / "product_pricing_data.json").write_text(expected, encoding="utf-8")
            self.assertEqual(expected, (root / "product_pricing_data.json").read_text(encoding="utf-8"))
            self.assertEqual(expected, (root / "public/product_pricing_data.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
