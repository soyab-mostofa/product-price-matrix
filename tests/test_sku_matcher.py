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

    def test_body_spray_does_not_match_cream(self) -> None:
        result = validate_match(
            brand="Dove",
            product_name="Dove Body Spray 250ml",
            target_size_text="250ml",
            candidate_name="Dove Body Love Deep Moisturisation Beauty Cream 250ml",
            candidate_size_text="250ml",
        )
        self.assertFalse(result.accepted)
        self.assertTrue(any("product type mismatch" in r for r in result.reasons))

    def test_facial_foam_does_not_match_night_cream(self) -> None:
        result = validate_match(
            brand="Pond's",
            product_name="Ponds Age Miracle Ultimate Youth Hexyl Retinol Facial Foam - 45g",
            target_size_text="45gm",
            candidate_name="Pond's Age Miracle Hexyl Retinol Ultimate Youth Night Cream 45g",
            candidate_size_text="45gm",
        )
        self.assertFalse(result.accepted)
        self.assertTrue(any("product type mismatch" in r for r in result.reasons))

    def test_missing_key_active_ingredient_is_rejected(self) -> None:
        result = validate_match(
            brand="The Ordinary",
            product_name="The Ordinary Hyaluronic Acid 2% +30ml",
            target_size_text="30ml",
            candidate_name="The Ordinary Salicylic Acid 2% Solution (30ml)",
            candidate_size_text="30ml",
        )
        self.assertFalse(result.accepted)
        self.assertTrue(any("missing key active" in r for r in result.reasons))

    def test_conflicting_fragrance_variant_is_rejected(self) -> None:
        result = validate_match(
            brand="Enchanteur",
            product_name="Enchanteur Enticing Perfumed Deo Roll-on 50ml",
            target_size_text="50ml",
            candidate_name="Enchanteur Perfumed Deo Roll-on Romantic 50ml",
            candidate_size_text="50ml",
        )
        self.assertFalse(result.accepted)
        self.assertTrue(any("fragrance" in r or "variant mismatch" in r for r in result.reasons))

    def test_sub_line_sunscreen_formula_is_rejected(self) -> None:
        result = validate_match(
            brand="Beauty of Joseon",
            product_name="Beauty Of Joseon Rice Probiotics Relief Sun SPF50 50ml",
            target_size_text="50ml",
            candidate_name="Beauty of Joseon Relief Sun Aqua-Fresh : Rice + B5 SPF50+ PA++++ 50ml",
            candidate_size_text="50ml",
        )
        self.assertFalse(result.accepted)
        self.assertTrue(any("variant mismatch" in r for r in result.reasons))

    def test_unexpected_spf_on_regular_moisturizer_is_rejected(self) -> None:
        result = validate_match(
            brand="Simple",
            product_name="Simple Light Moisturiser 125ml (uk)",
            target_size_text="125ml",
            candidate_name="Simple Kind to Skin Protecting Light Moisturiser SPF15 with Pro-Vitamins B5+E 125ml",
            candidate_size_text="125ml",
        )
        self.assertFalse(result.accepted)
        self.assertTrue(any("unexpected SPF" in r for r in result.reasons))

    def test_rival_product_sub_line_is_rejected(self) -> None:
        """Streax ships Vitalized and Shine serums that differ by one word.

        Every other token matches, so token-set similarity rates them ~80%
        alike and they clear the score threshold on their own.
        """
        result = validate_match(
            brand="Streax",
            product_name="Streax Vitalized With Walnut Oil Hair Serum 115ml",
            target_size_text="115ml",
            candidate_name="Streax Shine With Walnut Oil Hair Serum (115ml)",
            candidate_size_text="115ml",
        )
        self.assertFalse(result.accepted)
        self.assertTrue(any("sub-line mismatch" in r for r in result.reasons))

    def test_candidate_dropping_the_sub_line_is_rejected(self) -> None:
        """Sunsilk's Hijab line is a different product from the plain line."""
        result = validate_match(
            brand="Sunsilk",
            product_name="Sunsilk Hijab Refresh & Hair Fall Solution Shampoo 300ml",
            target_size_text="300ml",
            candidate_name="Sunsilk Hair Fall Solution Shampoo",
            candidate_size_text=None,
        )
        self.assertFalse(result.accepted)
        self.assertTrue(any("missing sub-line" in r for r in result.reasons))

    def test_same_sub_line_reordered_is_still_accepted(self) -> None:
        """The rule must not reject the correct listing for word order."""
        result = validate_match(
            brand="Streax",
            product_name="Streax Vitalized With Walnut Oil Hair Serum 115ml",
            target_size_text="115ml",
            candidate_name="Streax Hair Serum Vitalized With Walnut Oil 115ml",
            candidate_size_text="115ml",
        )
        self.assertTrue(result.accepted, result.reasons)


if __name__ == "__main__":
    unittest.main()
