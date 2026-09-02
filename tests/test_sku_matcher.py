from __future__ import annotations

import unittest

from sku_matcher import critical_markers, is_bundle, normalize, types_compatible, validate_match


class SkuMatcherTests(unittest.TestCase):
    def test_candidate_size_metadata_cannot_mask_title_size_conflict(self) -> None:
        result = validate_match(
            brand="Orgagenic",
            product_name="Orgagenic White Sandalwood Powder",
            target_size_text="100g",
            candidate_name="Orgagenic White Sandalwood Powder 50g",
            candidate_size_text="100g",
        )
        self.assertFalse(result.accepted)
        self.assertTrue(any("size mismatch" in reason for reason in result.reasons))

    def test_promotional_free_item_is_a_bundle(self) -> None:
        self.assertTrue(is_bundle("Buy shampoo and get conditioner free"))
        self.assertTrue(is_bundle("Body wash with free loofah"))
        self.assertTrue(is_bundle("BOGO offer"))
        self.assertTrue(is_bundle("Pack of 10"))

    def test_decimal_percentage_is_preserved_as_critical_marker(self) -> None:
        self.assertIn("0.5percent", critical_markers("Salicylic Acid 0.5% Serum"))
        self.assertIn("0.5 percent", normalize("Salicylic Acid 0.5% Serum"))

    def test_distinct_oil_categories_are_not_interchangeable(self) -> None:
        self.assertFalse(types_compatible("body_oil", "hair_oil"))
        self.assertFalse(types_compatible("essential_oil", "body_oil"))

    def test_exact_listing_is_accepted(self) -> None:
        result = validate_match(
            brand="Guerniss",
            product_name="Guerniss Niacinamide 10% + Zinc 1% Serum",
            target_size_text="30ml",
            candidate_name="Guerniss Niacinamide 10% + Zinc 1% Serum 30ml",
            candidate_size_text="30ml",
        )
        self.assertTrue(result.accepted, result.reasons)

    def test_wrong_title_brand_cannot_be_overridden_by_seller_context(self) -> None:
        result = validate_match(
            brand="Guerniss",
            product_name="Guerniss Vitamin C Serum",
            target_size_text="30ml",
            candidate_name="BioCare Vitamin C Serum 30ml",
            candidate_context="Guerniss Official https://guerniss.com/products/vitamin-c-serum",
            candidate_size_text="30ml",
        )
        self.assertFalse(result.accepted)
        self.assertIn("conflicting brand in candidate title", result.reasons)

    def test_extra_cosmetic_shade_is_rejected(self) -> None:
        result = validate_match(
            brand="Guerniss",
            product_name="Guerniss Foundation Ivory Pink",
            target_size_text="30ml",
            candidate_name="Guerniss Foundation Ivory Pink Natural 07 30ml",
            candidate_size_text="30ml",
        )
        self.assertFalse(result.accepted)
        self.assertTrue(any("unexpected critical markers" in reason for reason in result.reasons))

    def test_add_on_package_size_is_rejected_for_single_sku(self) -> None:
        result = validate_match(
            brand="Guerniss",
            product_name="Guerniss Vitamin C Serum",
            target_size_text="30ml",
            candidate_name="Guerniss Vitamin C Serum 30ml + 10ml",
            candidate_size_text="30ml",
        )
        self.assertFalse(result.accepted)
        self.assertIn("multiple package sizes for single SKU", result.reasons)


if __name__ == "__main__":
    unittest.main()
