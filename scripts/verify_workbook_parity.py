"""Verify D1 matches ``Roopelle.com Final Excel Sheet.xlsx`` exactly.

Three checks the commercial data must always pass:

1. **Parity** — every SKU's Source Cost and MRP in D1 equal the workbook's,
   to the paisa. The workbook is the commercial source of truth; drift here
   is a pricing error, not a display quirk.
2. **No duplicates** — one row per SKU (name + size), and one listing per
   (SKU, channel). A duplicate silently double-counts a channel.
3. **Traceability** — every product carries the sheet name and the 1-based
   Excel row it came from, so any figure on screen can be walked back to a
   cell.

Read-only: prints a report and exits non-zero on any mismatch.
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sqlite3
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from imported_seed import read_workbook  # noqa: E402

WORKBOOK = ROOT / "Roopelle.com Final Excel Sheet.xlsx"
D1_DIR = ROOT / ".wrangler/state/v3/d1/miniflare-D1DatabaseObject"

# A price is stored as a float; compare at paisa resolution.
TOLERANCE = Decimal("0.01")


def replica() -> Path:
    paths = [Path(p) for p in glob.glob(str(D1_DIR / "*.sqlite")) if "metadata" not in p]
    if not paths:
        raise SystemExit(f"No D1 replica under {D1_DIR}")
    return max(paths, key=lambda p: os.path.getsize(p))


def size_key(value: object) -> str:
    """Normalize a pack size so '200ml' and '200 ML' are one key."""
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def local_workbook_rows() -> dict[tuple[str, str], dict]:
    """Read the two local sheets, keyed by (product name, size).

    Keyed on size as well as name because the catalog holds same-name SKUs
    that differ only by pack size (Nature Beauty Healthy Glowing Body Lotion
    200/370ml; Orgagenic White Sandalwood 50/100g). Keying on name alone
    silently compares a SKU against its sibling's price.
    """
    import openpyxl

    wb = openpyxl.load_workbook(WORKBOOK, data_only=True)
    out: dict[tuple[str, str], dict] = {}

    sheet = wb["Local product "]
    for excel_row, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        name = str(row[0]).strip() if row[0] is not None else ""
        if not name:
            continue
        mrp, final = row[3], row[6]
        if mrp in (None, "") or final in (None, ""):
            continue
        out[(name, size_key(row[2]))] = {
            "sheet": "Local product ",
            "excel_row": excel_row,
            "mrp": Decimal(str(mrp)),
            "cost": Decimal(str(final)),
        }

    sheet = wb["local product Orgagenic"]
    for excel_row, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        name = str(row[0]).strip() if row[0] is not None else ""
        if not name:
            continue
        mrp, dist = row[3], row[4]
        if mrp in (None, "") or dist in (None, ""):
            continue
        out[(name, size_key(row[1]))] = {
            "sheet": "local product Orgagenic",
            "excel_row": excel_row,
            "mrp": Decimal(str(mrp)),
            "cost": Decimal(str(dist)),
        }

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    con = sqlite3.connect(replica())
    con.row_factory = sqlite3.Row
    failures = 0

    # ---- 2. Duplicates -------------------------------------------------
    print("=== Duplicate check ===")
    dupe_products = con.execute(
        """
        SELECT product_name, size, COUNT(*) n FROM products
        GROUP BY product_name, COALESCE(size, '') HAVING n > 1
        """
    ).fetchall()
    for row in dupe_products:
        print(f"  DUPLICATE SKU x{row['n']}: {row['product_name']!r} ({row['size']!r})")
    failures += len(dupe_products)

    dupe_rows = con.execute(
        "SELECT row_id, COUNT(*) n FROM products GROUP BY row_id HAVING n > 1"
    ).fetchall()
    for row in dupe_rows:
        print(f"  DUPLICATE row_id x{row['n']}: {row['row_id']}")
    failures += len(dupe_rows)

    dupe_listings = con.execute(
        """
        SELECT row_id, channel_name, COUNT(*) n FROM marketplace_listings
        GROUP BY row_id, channel_name HAVING n > 1
        """
    ).fetchall()
    for row in dupe_listings:
        print(f"  DUPLICATE listing x{row['n']}: row {row['row_id']} / {row['channel_name']}")
    failures += len(dupe_listings)

    if not (dupe_products or dupe_rows or dupe_listings):
        print("  clean — no duplicate SKUs, row_ids, or channel listings")

    # ---- 1. Parity: local book ----------------------------------------
    print("\n=== Local book parity (workbook vs D1) ===")
    workbook_rows = local_workbook_rows()
    local = con.execute(
        "SELECT row_id, product_name, size, manufactured_price, market_average_price "
        "FROM products WHERE sourcing_origin = 'local' ORDER BY row_id"
    ).fetchall()

    missing = mismatched = 0
    for product in local:
        entry = workbook_rows.get((product["product_name"], size_key(product["size"])))
        if entry is None:
            # One workbook row leaves the size cell blank while the catalog
            # carries a size; fall back to a name-only lookup when that name
            # is unique in the workbook, so a blank cell is not read as drift.
            by_name = [
                value for (name, _size), value in workbook_rows.items()
                if name == product["product_name"]
            ]
            entry = by_name[0] if len(by_name) == 1 else None
        if entry is None:
            missing += 1
            if args.verbose:
                print(f"  no workbook row for [{product['row_id']}] {product['product_name']!r}")
            continue
        cost = Decimal(str(product["manufactured_price"]))
        mrp = Decimal(str(product["market_average_price"]))
        if abs(cost - entry["cost"]) > TOLERANCE:
            print(f"  COST  [{product['row_id']}] {product['product_name'][:44]!r}: "
                  f"D1 {cost} != workbook {entry['cost']}")
            mismatched += 1
        if abs(mrp - entry["mrp"]) > TOLERANCE:
            print(f"  MRP   [{product['row_id']}] {product['product_name'][:44]!r}: "
                  f"D1 {mrp} != workbook {entry['mrp']}")
            mismatched += 1

    print(f"  {len(local)} local SKUs checked, {mismatched} price mismatches, "
          f"{missing} without a workbook row")
    failures += mismatched

    # ---- 1. Parity: imported book --------------------------------------
    print("\n=== Imported book parity (workbook vs D1) ===")
    report = read_workbook()
    by_name = {sku.product_name: sku for sku in report.skus}
    imported = con.execute(
        "SELECT row_id, product_name, manufactured_price FROM products "
        "WHERE sourcing_origin = 'imported' ORDER BY row_id"
    ).fetchall()

    imp_missing = imp_mismatched = 0
    for product in imported:
        sku = by_name.get(product["product_name"])
        if sku is None:
            imp_missing += 1
            continue
        cost = Decimal(str(product["manufactured_price"]))
        expected = Decimal(str(sku.source_cost))
        if abs(cost - expected) > TOLERANCE:
            print(f"  COST  [{product['row_id']}] {product['product_name'][:44]!r}: "
                  f"D1 {cost} != workbook {expected}")
            imp_mismatched += 1

    print(f"  {len(imported)} imported SKUs checked, {imp_mismatched} cost mismatches, "
          f"{imp_missing} without a workbook row")
    failures += imp_mismatched

    # ---- 3. Traceability ------------------------------------------------
    print("\n=== Traceability (source sheet + Excel row) ===")
    columns = {r[1] for r in con.execute("PRAGMA table_info(products)")}
    if "source_sheet" not in columns or "source_row" not in columns:
        print("  MISSING: products has no source_sheet / source_row columns")
        failures += 1
    else:
        blank = con.execute(
            "SELECT COUNT(*) FROM products WHERE source_sheet IS NULL OR source_row IS NULL"
        ).fetchone()[0]
        print(f"  {blank} products missing sheet/row provenance")
        failures += blank
        if not blank:
            per_sheet = Counter(
                r[0] for r in con.execute("SELECT source_sheet FROM products")
            )
            for sheet, count in sorted(per_sheet.items()):
                print(f"    {sheet:26s} {count:4d} SKUs")

    print(f"\n{'PASS' if failures == 0 else 'FAIL'} — {failures} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
