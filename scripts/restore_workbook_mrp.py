"""Restore the workbook MRP benchmark into verified_marketplace_research.json.

`excel_prices.market_average_price` is meant to be the workbook's Mkt (Avg) Price
for a SKU -- the benchmark used when a product has no live listings. At some point
a scraper pass overwrote it with the mean of that row's marketplace listings, so
283 rows carry a listing-derived number where a workbook number belongs, and the
24 rows with no active listings surface that wrong number directly in the UI.

This restores every value from the Roopelle workbook, keyed on (name, size) so the
two same-name/different-size SKUs stay distinct. Run once; the builder guard added
in catalog_builder.py keeps it from happening again.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "Roopelle.com Final Excel Sheet.xlsx"
RESEARCH = ROOT / "verified_marketplace_research.json"


def norm(value: object) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())).strip()


def number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r"[^0-9.\-]", "", str(value).replace(",", ""))
    try:
        return float(text) if text not in {"", "-", "."} else None
    except ValueError:
        return None


def workbook_mrp() -> dict[tuple[str, str], float]:
    """(product name, size) -> the workbook's MRP benchmark."""
    book = openpyxl.load_workbook(WORKBOOK, data_only=True)
    benchmarks: dict[tuple[str, str], float] = {}

    sheet = book["Local product "]
    for row in range(2, sheet.max_row + 1):
        name = sheet.cell(row, 1).value
        mrp = number(sheet.cell(row, 4).value)
        if name and mrp:
            benchmarks[(norm(name), norm(sheet.cell(row, 3).value))] = mrp

    # Orgagenic is a distributor sheet: MRP is the retail benchmark, and the
    # distributor price is the cost basis (already correct in the research file).
    sheet = book["local product Orgagenic"]
    for row in range(2, sheet.max_row + 1):
        name = sheet.cell(row, 1).value
        mrp = number(sheet.cell(row, 4).value)
        if name and mrp:
            benchmarks[(norm(name), norm(sheet.cell(row, 2).value))] = mrp

    return benchmarks


def main() -> int:
    benchmarks = workbook_mrp()
    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    products = research.get("products", [])

    repaired: list[tuple[str, float, float]] = []
    unmatched: list[str] = []

    for product in products:
        key = (norm(product.get("product_name")), norm(product.get("size")))
        benchmark = benchmarks.get(key)
        if benchmark is None:
            unmatched.append(str(product.get("product_name")))
            continue
        prices = product.setdefault("excel_prices", {})
        stored = number(prices.get("market_average_price"))
        if stored is None or abs(stored - benchmark) > 0.005:
            repaired.append((str(product.get("product_name")), stored or 0.0, benchmark))
            prices["market_average_price"] = benchmark

    RESEARCH.write_text(
        json.dumps(research, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"products scanned : {len(products)}")
    print(f"MRP benchmarks restored : {len(repaired)}")
    print(f"unmatched to workbook   : {len(unmatched)}")
    for name in unmatched:
        print(f"  unmatched: {name}")
    for name, before, after in sorted(repaired, key=lambda item: item[2] - item[1], reverse=True)[:10]:
        print(f"  {name[:52]:52} {before:9.2f} -> {after:9.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
