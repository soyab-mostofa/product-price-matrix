from __future__ import annotations

import unittest

from imported_seed import (
    SeedReport,
    ImportedSku,
    derive_brand,
    find_overlaps,
    parse_price,
    parse_size,
)


class BrandDerivationTests(unittest.TestCase):
    def test_multi_word_brands_beat_their_own_prefixes(self) -> None:
        """'The Ordinary' must not resolve as 'The'."""
        self.assertEqual("The Ordinary", derive_brand("THE ORDINARY NIACINAMIDE 10%+ZINC 1% SERUM 30ML"))
        self.assertEqual("Beauty of Joseon", derive_brand("Beauty Of Joseon Rice Probiotics Relief Sun SPF50 50ml"))
        self.assertEqual("The Face Shop", derive_brand("The Face Shop Rice Water Bright Foaming Cleanser 150ml"))
        self.assertEqual("Dot & Key", derive_brand("Dot & Key Cica Calming Mattifying Sunscreen SPF50+ PA+++ 80g"))

    def test_spelling_variants_collapse_to_one_brand(self) -> None:
        """Left alone these fragment the brand filter into near-duplicates."""
        for name in [
            "HEAD & SHOULDER SHAMPOO 400ML (THAI)",
            "Head Shoulders Shampoo 400ml",
            "Head&Shoulder Shampoo SA 400ml",
        ]:
            self.assertEqual("Head & Shoulders", derive_brand(name), name)

        for name in [
            "Herbal Essence Coconut Milk Hydrate Shampoo 400ml",
            "HERBAL ESSENCE CONDITIONER 465ML (PUMP)",
        ]:
            self.assertEqual("Herbal Essences", derive_brand(name), name)

        self.assertEqual("L'Oreal", derive_brand("L'Oréal Paris Elvive Colour Protect Shampoo 250ml"))
        self.assertEqual("L'Oreal", derive_brand("LOreal Total Repair 5 Shampoo 340ml"))
        self.assertEqual("St. Ives", derive_brand("STIVES SCRUB 150ML"))

    def test_source_typo_resolves_to_the_real_brand(self) -> None:
        """The workbook misspells Joseon; a typo must not become a phantom brand."""
        self.assertEqual("Beauty of Joseon", derive_brand("Beauty Of Jiseon Sunscreen 50ml"))

    def test_sub_brand_answers_to_its_parent(self) -> None:
        """Nature Beauty sits under Q Cosmetics in the catalog's hierarchy."""
        self.assertEqual("Q Cosmetics", derive_brand("Nature Beauty Sunscreen 70ml (Q)"))

    def test_an_unknowable_brand_is_reported_not_guessed(self) -> None:
        """'Centella' is an ingredient; several Korean brands sell a sun stick."""
        self.assertIsNone(derive_brand("CENTELLA SUN STICK 20ML"))


class SizeParsingTests(unittest.TestCase):
    def test_common_units_parse(self) -> None:
        self.assertEqual("150ml", parse_size("Simple Face Wash Refreshing Gel 150ml (uk)"))
        self.assertEqual("80gm", parse_size("Dot & Key Cica Sunscreen SPF50+ 80g"))
        self.assertEqual("135gm", parse_size("Dove Pink Moisturising Cream Beauty Bar 135g"))

    def test_unicode_capital_i_is_a_millilitre(self) -> None:
        """The source writes 330mI with a capital i — six SKUs would lose their size."""
        self.assertEqual("330ml", parse_size("Dove Hair Fall Rescue Shampoo 330mI"))
        self.assertEqual("100ml", parse_size("Hugo Boss Bottled Night EDT For Men 100mI"))
        self.assertEqual("250ml", parse_size("Ossum Floral Fragrance Body Mist For Women 250mI"))

    def test_litres_normalise_to_millilitres(self) -> None:
        self.assertEqual("1000ml", parse_size("PANTENE SHAMPOO 1LTR (DUBAI)"))

    def test_a_name_without_a_size_yields_none(self) -> None:
        self.assertIsNone(parse_size("Some Product With No Pack Size"))


class PriceParsingTests(unittest.TestCase):
    def test_blanks_and_dashes_are_absences_not_zeroes(self) -> None:
        for empty in [None, "", "-", "--", "  "]:
            self.assertIsNone(parse_price(empty), repr(empty))

    def test_a_typo_is_rejected_rather_than_coerced(self) -> None:
        """'1155S' appears in a Klassy Missy cell; guessing 1155 invents data."""
        self.assertIsNone(parse_price("1155S"))

    def test_a_range_takes_the_price_a_customer_actually_pays(self) -> None:
        """'1400-1250' is a list price beside an active one."""
        self.assertEqual(1250.0, parse_price("1400-1250"))
        self.assertEqual(1250.0, parse_price("1250-1400"))

    def test_real_prices_parse(self) -> None:
        self.assertEqual(749.0, parse_price(749))
        self.assertEqual(220.2, parse_price(220.2))
        self.assertEqual(1450.0, parse_price("1,450"))

    def test_non_positive_prices_are_rejected(self) -> None:
        self.assertIsNone(parse_price(0))
        self.assertIsNone(parse_price(-50))


class OverlapReportTests(unittest.TestCase):
    def test_a_matching_local_sku_is_reported_not_merged(self) -> None:
        report = SeedReport(skus=[
            ImportedSku("CeraVe Moisturizing Cream 56ml", "CeraVe", "56ml", "Skincare", 930.0),
            ImportedSku("Anua Peach 70% Niacin Serum 30ml", "Anua", "30ml", "Skincare", 1100.0),
        ])
        find_overlaps(report, [("CeraVe Moisturizing Cream 56ml", "56ml")])

        self.assertEqual([("CeraVe Moisturizing Cream 56ml", "56ml")], report.overlaps)
        # Both rows survive: the same product sourced two ways has two costs.
        self.assertEqual(2, len(report.skus))

    def test_same_name_at_a_different_size_is_not_an_overlap(self) -> None:
        report = SeedReport(skus=[
            ImportedSku("CeraVe Moisturizing Cream 340ml", "CeraVe", "340ml", "Skincare", 1800.0),
        ])
        find_overlaps(report, [("CeraVe Moisturizing Cream 56ml", "56ml")])
        self.assertEqual([], report.overlaps)


if __name__ == "__main__":
    unittest.main()
