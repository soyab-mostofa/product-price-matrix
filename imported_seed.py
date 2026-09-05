"""Seed Imported SKUs from the source workbook.

The workbook has no brand and no size column, so both are derived from the
product name, and the category comes from the tab a row sits in. The `Price`
column is the Source Cost — the importer's quoted price.

Brand matching is a curated longest-match: multi-word brands are tried before
single tokens so "The Ordinary" never resolves as "The", and known spelling
variants collapse to one canonical brand so the brand filter does not fragment.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKBOOK = ROOT / "Roopelle.com Final Excel Sheet.xlsx"

# Tab -> category. Only imported tabs are seeded; the workbook's local tabs
# describe SKUs the catalog already holds.
IMPORTED_TABS = {
    "imported Skincare": "Skincare",
    "imported Haircare": "Haircare",
    "imported Fregrance": "Fragrance",
}

CHANNEL_COLUMNS = ["Shajgoj", "Arogga", "Klassy Missy", "Skincarebd", "themallbd", "Skinplus"]

# Canonical brands, longest first so multi-word names win over their prefixes.
BRANDS = [
    "Beauty of Joseon", "Head & Shoulders", "Herbal Essences", "The Face Shop",
    "Fair & Lovely", "Glow & Lovely", "Hugo Boss",
    "The Ordinary", "Victoria's Secret", "Yardley London", "Christian Dean",
    "Remy Marquis", "Bombay Shaving", "Forest Essentials", "Nature Republic",
    "Some By Mi", "Dr. Althea", "Park Avenue", "Wild Stone", "Mothercare",
    "Neutrogena", "Enchanteur", "Dot & Key", "3W Clinic", "Palmer's", "Cetaphil",
    "Sebamed", "Bioderma", "La Roche", "Eucerin", "Aveeno", "Medicube", "CeraVe",
    "Johnson's", "St. Ives", "Sunsilk", "Pantene", "TRESemme", "Garnier",
    "Vaseline", "Himalaya", "Mamaearth", "Biotique", "Patanjali", "Minimalist",
    "Deconstruct", "Aqualogica", "Dermafique", "Soulflower", "mCaffeine",
    "Kodomo", "Missha", "Cosrx", "Nivea", "Simple", "Streax", "Vatika", "Rasasi",
    "Ossum", "Havoc", "Havex", "Jaguar", "Denver", "Fiama", "Sesa", "Anua",
    "Axis-Y", "APLB", "Dabo", "Boots", "Olay", "Veet", "Fogg", "Axe", "Lux",
    "Dove", "Pond's", "L'Oréal", "YC", "Skinfood", "Innisfree", "Laneige",
    "Etude", "Nykaa", "Plum", "Ustraa", "Beardo", "Khadi", "Vega", "Kama",
    "Q Cosmetics", "Nature Beauty", "SKIN1004",
]

# Source spellings that mean an existing brand. Matched after normalisation
# (case-folded, punctuation-stripped), so only genuine variants need listing.
BRAND_ALIASES = {
    "loreal": "L'Oréal",
    "l oreal": "L'Oréal",
    "l oreal paris elvive": "L'Oréal",
    "head shoulder": "Head & Shoulders",
    "head shoulders": "Head & Shoulders",
    "head and shoulders": "Head & Shoulders",
    "herbal essence": "Herbal Essences",
    "ponds": "Pond's",
    "pond s": "Pond's",
    "johnson": "Johnson's",
    "stives": "St. Ives",
    "st ives": "St. Ives",
    "beauty of jiseon": "Beauty of Joseon",   # misspelling in the source sheet
    "dr davey": "Dr. Davey",
    "dr althea": "Dr. Althea",
    "victorias secret": "Victoria's Secret",
    "palmers": "Palmer's",
    "johnsons": "Johnson's",
    "tresemme": "TRESemme",
    "secret tone": "Christian Dean",
    "centella sun stick": "SKIN1004",
}

# Sub-brands answer to their parent, per the catalog's brand hierarchy.
PARENT_BRAND = {"Nature Beauty": "Q Cosmetics"}

# Unicode look-alikes: the source writes "330mI" with a capital i, and NBSP
# turns up between number and unit. Both would silently cost a SKU its size.
# Scoped to size parsing only — applying I->l to a brand name would maim every
# uppercase I in it ("THE ORDINARY" -> "the ordlnary").
_UNIT_LOOKALIKES = str.maketrans({"I": "l", "\u0131": "l", "\u00a0": " ", "\u2019": "'"})

_SIZE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(ml|l|ltr|litre|liter|gm|gr|g|kg|mg|pcs|pc|piece)\b",
    re.IGNORECASE,
)


def _normalise(text: str) -> str:
    """Case-folded, accent-free, punctuation-free form used for brand matching.

    NFKD splits an accented letter into base + combining mark; dropping the
    marks is what makes "L'Oréal" and "LOreal" the same brand.
    """
    decomposed = unicodedata.normalize("NFKD", str(text))
    unaccented = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", unaccented.lower()).strip()


def parse_size(name: str) -> str | None:
    """The pack size embedded in a product name, normalised to one unit form."""
    cleaned = str(name).translate(_UNIT_LOOKALIKES)
    match = _SIZE.search(cleaned)
    if not match:
        return None
    amount, unit = match.group(1), match.group(2).lower()
    number = float(amount)
    if unit in {"l", "ltr", "litre", "liter"}:
        number, unit = number * 1000, "ml"
    elif unit in {"gr", "g"}:
        unit = "gm"
    elif unit in {"pc", "piece"}:
        unit = "pcs"
    text = f"{number:.0f}" if number == int(number) else f"{number:g}"
    return f"{text}{unit}"


def _contains_word(haystack: str, needle: str) -> bool:
    """True when `needle` appears in `haystack` on whole-word boundaries.

    Both are already normalised to space-separated tokens, so a plain substring
    test would let a short brand match mid-word — "YC" inside "glycolic",
    "Axe" inside "waxed". Padding both sides forces a token boundary.
    """
    return f" {needle} " in f" {haystack} "


def derive_brand(name: str) -> str | None:
    """The canonical brand for a product name, or None when it cannot be told."""
    flat = _normalise(name)
    for alias in sorted(BRAND_ALIASES, key=len, reverse=True):
        if _contains_word(flat, alias):
            return PARENT_BRAND.get(BRAND_ALIASES[alias], BRAND_ALIASES[alias])
    for brand in sorted(BRANDS, key=len, reverse=True):
        if _contains_word(flat, _normalise(brand)):
            return PARENT_BRAND.get(brand, brand)
    return None


def parse_price(value: object) -> float | None:
    """A positive number, or None for blanks, dashes, and typo'd cells.

    A range like "1400-1250" is a list price beside an active one; the catalog
    records what a customer actually pays, so the lower figure wins.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    text = str(value).strip()
    if not text or text in {"-", "--", "n/a", "N/A"}:
        return None
    cleaned = re.sub(r"[,\s৳]", "", text)
    if re.fullmatch(r"\d+(?:\.\d+)?[-–]\d+(?:\.\d+)?", cleaned):
        low, high = (float(part) for part in re.split(r"[-–]", cleaned))
        return min(low, high) or None
    try:
        number = float(cleaned)
    except ValueError:
        return None  # e.g. "1155S" — a typo, not a price
    return number if number > 0 else None


@dataclass
class ImportedSku:
    product_name: str
    brand_name: str | None
    size: str | None
    category: str
    source_cost: float
    channel_prices: dict[str, float] = field(default_factory=dict)
    # Workbook provenance: the sheet and 1-based Excel row this SKU was read
    # from, so a price on the dashboard walks back to a cell.
    source_sheet: str | None = None
    source_row: int | None = None


@dataclass
class SeedReport:
    skus: list[ImportedSku] = field(default_factory=list)
    unresolved_brands: list[str] = field(default_factory=list)
    missing_sizes: list[str] = field(default_factory=list)
    overlaps: list[tuple[str, str]] = field(default_factory=list)
    rejected_prices: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def listing_count(self) -> int:
        return sum(len(sku.channel_prices) for sku in self.skus)


def read_workbook(path: Path = WORKBOOK) -> SeedReport:
    from openpyxl import load_workbook

    workbook = load_workbook(path, data_only=True)
    report = SeedReport()

    for tab, category in IMPORTED_TABS.items():
        if tab not in workbook.sheetnames:
            continue
        rows = list(workbook[tab].iter_rows(values_only=True))
        header_index = next(
            (i for i, row in enumerate(rows[:10])
             if sum(1 for cell in row if cell not in (None, "")) >= 3),
            None,
        )
        if header_index is None:
            continue
        header = [str(cell).strip() if cell is not None else "" for cell in rows[header_index]]
        column = {name: i for i, name in enumerate(header) if name}

        name_at = column.get("Product Name")
        price_at = column.get("Price")
        if name_at is None or price_at is None:
            continue

        # `rows` is 0-indexed; Excel numbers from 1. Offsetting by the header
        # index keeps `source_row` typeable straight into the Name Box.
        for offset, row in enumerate(rows[header_index + 1:]):
            excel_row = header_index + offset + 2
            if not any(cell not in (None, "") for cell in row):
                continue
            raw_name = row[name_at] if name_at < len(row) else None
            if raw_name in (None, ""):
                continue
            name = " ".join(str(raw_name).split())
            cost = parse_price(row[price_at] if price_at < len(row) else None)
            if cost is None:
                report.rejected_prices.append((name, "Price", str(row[price_at])))
                continue

            brand = derive_brand(name)
            size = parse_size(name)
            if brand is None:
                report.unresolved_brands.append(name)
            if size is None:
                report.missing_sizes.append(name)

            sku = ImportedSku(
                name, brand, size, category, cost,
                source_sheet=tab, source_row=excel_row,
            )
            for channel in CHANNEL_COLUMNS:
                at = column.get(channel)
                if at is None or at >= len(row):
                    continue
                raw = row[at]
                if raw in (None, ""):
                    continue
                price = parse_price(raw)
                if price is None:
                    if str(raw).strip() not in {"-", "--"}:
                        report.rejected_prices.append((name, channel, str(raw)))
                    continue
                sku.channel_prices[channel] = price
            report.skus.append(sku)

    return report


def find_overlaps(report: SeedReport, existing: list[tuple[str, str | None]]) -> None:
    """Flag imported SKUs matching a local SKU on name and size, never merging.

    The same product sourced two ways has two costs and two margins; that
    comparison is the point. Overlaps are surfaced for a human to look at.
    """
    index = {(_normalise(name), (size or "").lower()) for name, size in existing}
    for sku in report.skus:
        if (_normalise(sku.product_name), (sku.size or "").lower()) in index:
            report.overlaps.append((sku.product_name, sku.size or ""))
