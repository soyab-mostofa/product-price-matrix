"""Fold admin price edits back into the canonical research file.

``PATCH /api/prices`` writes straight into the D1 replica, but ``seed.sql`` —
generated from ``verified_marketplace_research.json`` — re-inserts every local
row with::

    ON CONFLICT(row_id) DO UPDATE SET manufactured_price=excluded...,
                                      market_average_price=excluded...

so the next ``db:local:sync`` reverts an unfolded edit and every command still
reports success. This is the same shape as the discovery-pass bug that cost 80
verified listings, and the fix is the same: fold into the canonical artifact
BEFORE any rebuild.

Correct order:

    1. edit in the UI          (writes D1 + the price_edits journal)
    2. this script             (local -> research JSON; imported -> edit artifact)
    3. build_matrix.py         (seed.sql now carries each local edited value)
    4. db:local:sync           (seed_imported applies imported edited values last)

Local SKUs live in ``verified_marketplace_research.json``. The imported book is
rebuilt from the workbook, which has no standalone MRP column, so imported edits
land in ``imported_price_edits.json`` keyed by stable workbook sheet + row.
``scripts/seed_imported.py`` applies that artifact AFTER its workbook/listing
recompute, making the final D1 columns the same hard-overwritten static values
the admin saved — there is still no runtime resolution layer.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RESEARCH = ROOT / "verified_marketplace_research.json"
IMPORTED_EDITS = ROOT / "imported_price_edits.json"
D1_DIR = ROOT / ".wrangler/state/v3/d1/miniflare-D1DatabaseObject"

FIELD_TO_EXCEL_KEY = {
    "source_cost": "manufactured_price",
    "mrp": "market_average_price",
}


def replicas() -> list[Path]:
    """Every project-local replica, largest first.

    Vite and `wrangler d1 execute --local` can resolve the same binding to
    different hashed files, so an edit may live in either.
    """
    paths = [
        Path(p) for p in glob.glob(str(D1_DIR / "*.sqlite"))
        if "metadata" not in os.path.basename(p)
    ]
    if not paths:
        raise SystemExit(f"No D1 replica under {D1_DIR}")
    return sorted(paths, key=lambda p: p.stat().st_size, reverse=True)


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone() is not None


def latest_edits(path: Path) -> dict[tuple[int, str], sqlite3.Row]:
    """The newest unfolded edit per (row_id, field).

    A price can be edited several times before anyone folds. Only the final
    value matters to the research file, but every row is marked folded so the
    journal keeps its full audit trail.
    """
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        if not table_exists(connection, "price_edits"):
            return {}
        rows = connection.execute(
            """
            SELECT edit.id, edit.product_row_id, edit.field, edit.new_value,
                   edit.workbook_value, edit.edited_at,
                   product.product_name, product.size, product.sourcing_origin,
                   product.source_sheet, product.source_row
              FROM price_edits edit
              JOIN products product ON product.row_id = edit.product_row_id
             WHERE edit.folded = 0
             ORDER BY edit.id ASC
            """
        ).fetchall()
    finally:
        connection.close()

    # Ascending id, so the last write per key wins.
    return {(int(r["product_row_id"]), str(r["field"])): r for r in rows}


def imported_artifact() -> dict:
    """Load the imported canonical edits artifact, tolerating first-run absence."""
    if not IMPORTED_EDITS.exists():
        return {"version": 1, "edits": []}
    payload = json.loads(IMPORTED_EDITS.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or not isinstance(payload.get("edits"), list):
        raise SystemExit(f"Invalid imported price edit artifact: {IMPORTED_EDITS}")
    return payload


def imported_key(edit: dict | sqlite3.Row) -> tuple[str, int]:
    """Stable workbook identity — row_id can move when a replica is reseeded."""
    sheet = edit["source_sheet"]
    row = edit["source_row"]
    if not sheet or not row:
        raise ValueError(
            f"Imported SKU {edit['product_name']!r} has no workbook sheet/row provenance"
        )
    return str(sheet), int(row)


def mark_folded(path: Path, row_ids: list[int]) -> None:
    if not row_ids:
        return
    connection = sqlite3.connect(path, timeout=30)
    connection.execute("PRAGMA busy_timeout = 30000")
    try:
        connection.executemany(
            "UPDATE price_edits SET folded = 1 WHERE product_row_id = ? AND folded = 0",
            [(row_id,) for row_id in row_ids],
        )
        connection.commit()
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="report what would be folded without writing anything",
    )
    args = parser.parse_args()

    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    by_row = {int(product["row"]): product for product in research["products"]}

    imported = imported_artifact()
    imported_by_key = {
        (str(entry["source_sheet"]), int(entry["source_row"])): entry
        for entry in imported["edits"]
    }

    local_applied = 0
    imported_applied = 0
    missing: list[str] = []
    folded_rows: dict[Path, list[int]] = {}

    for path in replicas():
        edits = latest_edits(path)
        if not edits:
            continue

        for (row_id, field), edit in edits.items():
            new_value = float(edit["new_value"])

            if str(edit["sourcing_origin"]) == "imported":
                try:
                    key = imported_key(edit)
                except ValueError as exc:
                    missing.append(str(exc))
                    continue

                entry = imported_by_key.get(key)
                if entry is None:
                    entry = {
                        "source_sheet": key[0],
                        "source_row": key[1],
                        "product_name": str(edit["product_name"]),
                        "size": edit["size"],
                    }
                    imported["edits"].append(entry)
                    imported_by_key[key] = entry

                artifact_field = "source_cost" if field == "source_cost" else "mrp"
                workbook_value = edit["workbook_value"]
                is_revert = workbook_value is not None and new_value == float(workbook_value)

                if is_revert:
                    # Reverting an imported value means "follow the workbook /
                    # listing resolution again", so REMOVE the canonical pin.
                    # Leaving mrp=baseline in the artifact would make the seeder
                    # relabel an official/listing-derived value as 'manual'.
                    if artifact_field in entry:
                        print(
                            f"  {edit['product_name'][:44]:<46} {field:<12} "
                            f"{entry.get(artifact_field)} -> workbook/listing  [imported revert]"
                        )
                        entry.pop(artifact_field, None)
                        entry["updated_at"] = str(edit["edited_at"])
                        imported_applied += 1
                elif entry.get(artifact_field) != new_value:
                    print(
                        f"  {edit['product_name'][:44]:<46} {field:<12} "
                        f"{entry.get(artifact_field)} -> {new_value}  [imported]"
                    )
                    entry[artifact_field] = new_value
                    entry["updated_at"] = str(edit["edited_at"])
                    imported_applied += 1

                # If both pins were reverted, the identity-only shell has no
                # effect and should not remain in the canonical artifact.
                if "source_cost" not in entry and "mrp" not in entry:
                    if entry in imported["edits"]:
                        imported["edits"].remove(entry)
                    imported_by_key.pop(key, None)

                folded_rows.setdefault(path, []).append(row_id)
                continue

            product = by_row.get(row_id)
            if product is None:
                missing.append(f"row {row_id} ({edit['product_name']})")
                continue

            key = FIELD_TO_EXCEL_KEY[field]
            prices = product.setdefault("excel_prices", {})

            if prices.get(key) == new_value:
                # Already carried (a re-run, or an edit that returned the price
                # to what the file already held). Still mark it folded.
                folded_rows.setdefault(path, []).append(row_id)
                continue

            print(
                f"  {edit['product_name'][:44]:<46} {field:<12} "
                f"{prices.get(key)} -> {new_value}  [local]"
            )
            prices[key] = new_value

            # market_average_price is mirrored at the top level of each product
            # and is what build_matrix.py emits as the MRP.
            if field == "mrp":
                product["market_average_price"] = new_value
                workbook_value = edit["workbook_value"]
                product["mrp_source_type"] = (
                    "workbook"
                    if workbook_value is not None and new_value == float(workbook_value)
                    else "manual"
                )

            local_applied += 1
            folded_rows.setdefault(path, []).append(row_id)

    if missing:
        print("\nWARNING: journalled edits with no canonical target (not folded):")
        for entry in missing[:10]:
            print(f"    {entry}")

    total_applied = local_applied + imported_applied
    if args.dry_run:
        print(
            f"\nDRY RUN — {local_applied} local + {imported_applied} imported "
            "edit(s) would be folded, nothing written."
        )
        return 0

    if local_applied:
        RESEARCH.write_text(
            json.dumps(research, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if imported_applied:
        IMPORTED_EDITS.write_text(
            json.dumps(imported, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    for path, row_ids in folded_rows.items():
        mark_folded(path, row_ids)

    print(
        f"\nFolded {local_applied} local edit(s) into {RESEARCH.name} and "
        f"{imported_applied} imported edit(s) into {IMPORTED_EDITS.name}."
    )
    if total_applied:
        print(
            "Now rebuild and sync so the edits survive:\n"
            "  uv run --with openpyxl --with rapidfuzz python3 build_matrix.py\n"
            "  bun run db:local:sync"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
