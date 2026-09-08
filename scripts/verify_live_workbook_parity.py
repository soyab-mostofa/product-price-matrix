"""Verify LIVE PRODUCTION prices against the workbook.

``verify_workbook_parity.py`` only ever reads the local D1 replica. That leaves
a real gap: production can drift on its own — an admin edit made against the
deployed site, a partial deploy, an unsynced remote database — and every local
gate still reports PASS. Production once sat on an edited Source Cost for about
seven hours with nothing to catch it.

This asks the live API what it is actually serving and compares each figure to
the workbook cell it came from, keyed on the SKU's own recorded (sheet, row)
provenance rather than a name match.

What counts as drift:

- A Source Cost that differs from its workbook cell, for either book.
- A LOCAL MRP that differs from its workbook cell. A local MRP is always the
  workbook benchmark; an imported MRP legitimately resolves from live listings
  (official -> third-party avg -> reference), so it is reported, never failed.
- A SKU with no sheet/row provenance, which cannot be traced back at all.

An admin edit shows up here as drift *by design*: this gate answers "does
production still match the commercial source of truth", and a deliberate
override is exactly the thing worth knowing about. ``--allow-edited`` downgrades
a difference that the API itself attributes to a journalled edit, for when you
want to see only *unexplained* drift.

Read-only over HTTPS. Exits non-zero on drift, so cron or CI can gate on it.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from imported_seed import read_workbook  # noqa: E402
from verify_workbook_parity import local_workbook_rows  # noqa: E402

BASE = "https://product-price-matrix.pages.dev"
TOLERANCE = Decimal("0.01")

# Cloudflare 403s urllib's default agent.
UA = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def fetch_products(base: str) -> list[dict]:
    """Both books, exactly as a visitor receives them."""
    products: list[dict] = []
    for origin in ("local", "imported"):
        url = f"{base}/api/products" + ("" if origin == "local" else "?origin=imported")
        request = urllib.request.Request(url, headers=UA)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
        except urllib.error.URLError as error:
            raise SystemExit(f"Could not reach {url}: {error}") from error
        products += payload["products"]
    return products


def workbook_by_provenance() -> dict[tuple[str, int], dict]:
    """Every workbook row, keyed by (sheet, 1-based Excel row).

    Keyed on provenance rather than name so this compares each SKU against the
    exact cell it was built from — the catalog holds same-name SKUs differing
    only by pack size, and one workbook row can back two SKUs (row 259 ships as
    both a 200ml and a 400ml).
    """
    expected: dict[tuple[str, int], dict] = {}

    for entry in local_workbook_rows().values():
        expected[(entry["sheet"], entry["excel_row"])] = {
            "cost": entry["cost"],
            "mrp": entry["mrp"],
        }

    for sku in read_workbook().skus:
        if not sku.source_sheet or not sku.source_row:
            continue
        expected[(sku.source_sheet, sku.source_row)] = {
            "cost": Decimal(str(sku.source_cost)),
            "mrp": None,  # An imported MRP resolves from listings, not the workbook.
        }

    return expected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=BASE, help=f"target origin (default {BASE})")
    parser.add_argument(
        "--allow-edited", action="store_true",
        help="treat a difference the API attributes to a journalled admin edit as expected",
    )
    args = parser.parse_args()

    expected = workbook_by_provenance()
    products = fetch_products(args.base)

    print(f"live products: {len(products)}   workbook rows: {len(expected)}")

    cost_drift: list[tuple[dict, Decimal]] = []
    mrp_drift: list[tuple[dict, Decimal]] = []
    explained: list[str] = []
    missing_provenance: list[dict] = []
    unmatched: list[dict] = []

    for product in products:
        sheet, row = product.get("source_sheet"), product.get("source_row")
        if not sheet or not row:
            missing_provenance.append(product)
            continue

        cell = expected.get((sheet, int(row)))
        if cell is None:
            unmatched.append(product)
            continue

        live_cost = Decimal(str(product["manufactured_price"]))
        if abs(live_cost - cell["cost"]) > TOLERANCE:
            if args.allow_edited and product.get("source_cost_edited_at"):
                explained.append(
                    f"row {product['row']} source_cost {live_cost} "
                    f"(workbook {cell['cost']}, edited {product['source_cost_edited_at']})"
                )
            else:
                cost_drift.append((product, cell["cost"]))

        # A local MRP is always the workbook benchmark. An imported MRP is not.
        if product["sourcing_origin"] == "local" and cell["mrp"] is not None:
            live_mrp = Decimal(str(product["market_average_price"]))
            if abs(live_mrp - cell["mrp"]) > TOLERANCE:
                if args.allow_edited and product.get("mrp_edited_at"):
                    explained.append(
                        f"row {product['row']} mrp {live_mrp} "
                        f"(workbook {cell['mrp']}, edited {product['mrp_edited_at']})"
                    )
                else:
                    mrp_drift.append((product, cell["mrp"]))

    print(f"\n=== Source Cost drift ({len(cost_drift)}) ===")
    for product, want in cost_drift:
        print(f"  row_id={product['row']} {product['product_name'][:48]!r}")
        print(f"     live={product['manufactured_price']}  workbook={want}  "
              f"({product['source_sheet']!r} row {product['source_row']})")
        print(f"     source_cost_edited_at={product.get('source_cost_edited_at')}")

    print(f"\n=== Local MRP drift ({len(mrp_drift)}) ===")
    for product, want in mrp_drift:
        print(f"  row_id={product['row']} {product['product_name'][:48]!r}")
        print(f"     live={product['market_average_price']}  workbook={want}  "
              f"({product['source_sheet']!r} row {product['source_row']})")
        print(f"     mrp_edited_at={product.get('mrp_edited_at')}")

    print(f"\n=== Traceability ===")
    print(f"  {len(missing_provenance)} without sheet/row provenance")
    print(f"  {len(unmatched)} whose provenance names no workbook row")
    for product in unmatched[:10]:
        print(f"     row_id={product['row']} {product['source_sheet']!r} row {product['source_row']}")

    if explained:
        print(f"\n=== Explained by a journalled edit ({len(explained)}) ===")
        for line in explained:
            print(f"  {line}")

    problems = len(cost_drift) + len(mrp_drift) + len(missing_provenance) + len(unmatched)
    verdict = "PASS" if problems == 0 else "DRIFT"
    print(f"\n{verdict} — {len(products)} live SKUs, {problems} problem(s) vs the workbook")
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
