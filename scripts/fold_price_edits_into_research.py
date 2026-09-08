"""Fold admin price edits into separate canonical override artifacts.

The commercial research JSON is an immutable mirror of
``Roopelle.com Final Excel Sheet.xlsx``. Admin edits therefore NEVER rewrite
``excel_prices``. They are folded into one override artifact per book, keyed by
stable workbook sheet + row, and the seeders apply those pins only after writing
the workbook-derived baselines.

Correct order:

    1. edit in the UI          (writes D1 + the price_edits journal)
    2. this script             (local/imported -> separate override artifacts)
    3. build_matrix.py         (seed.sql resets baseline, then applies local pins)
    4. db:local:sync           (seed_imported does the same for imported pins)

A revert removes that field's pin from the artifact. The append-only journal
remains the audit history; the artifacts only describe current override state.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RESEARCH = ROOT / "verified_marketplace_research.json"
LOCAL_EDITS = ROOT / "local_price_edits.json"
IMPORTED_EDITS = ROOT / "imported_price_edits.json"
D1_DIR = ROOT / ".wrangler/state/v3/d1/miniflare-D1DatabaseObject"
REMOTE_DATABASE = "product-price-matrix-db"

EDIT_QUERY = """
SELECT edit.id, edit.product_row_id, edit.field, edit.new_value,
       edit.workbook_value, edit.edited_at, edit.reverted,
       product.product_name, product.size, product.sourcing_origin,
       product.mrp_source_type, product.source_sheet, product.source_row
  FROM price_edits edit
  JOIN products product ON product.row_id = edit.product_row_id
 WHERE edit.folded = 0
 ORDER BY edit.id ASC
"""


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


def latest_edits(path: Path) -> dict[tuple[int, str], dict]:
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
        rows = connection.execute(EDIT_QUERY).fetchall()
    finally:
        connection.close()

    # Ascending id, so the last write per key wins.
    return {
        (int(r["product_row_id"]), str(r["field"])): dict(r)
        for r in rows
    }


def _wrangler_json(sql: str) -> list[dict]:
    last_error = ""
    for attempt in range(3):
        result = subprocess.run(
            ["bunx", "wrangler", "d1", "execute", REMOTE_DATABASE,
             "--remote", "--json", "--command", sql],
            cwd=ROOT, capture_output=True, text=True,
        )
        if result.returncode == 0:
            payload = json.loads(result.stdout)
            return [dict(row) for row in payload[0].get("results", [])]
        last_error = result.stderr or result.stdout
        if attempt < 2:
            time.sleep(2 ** attempt)
    raise RuntimeError(last_error)


def remote_latest_edits() -> dict[tuple[int, str], dict]:
    """Latest unfolded edit per field from production D1."""
    rows = _wrangler_json(EDIT_QUERY)
    return {(int(r["product_row_id"]), str(r["field"])): r for r in rows}


def mark_remote_folded(row_ids: list[int]) -> None:
    if not row_ids:
        return
    ids = ",".join(str(int(row_id)) for row_id in sorted(set(row_ids)))
    _wrangler_json(
        f"UPDATE price_edits SET folded = 1 "
        f"WHERE product_row_id IN ({ids}) AND folded = 0"
    )


def price_artifact(path: Path, label: str) -> dict:
    """Load one canonical override artifact, tolerating first-run absence."""
    if not path.exists():
        return {"version": 1, "edits": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or not isinstance(payload.get("edits"), list):
        raise SystemExit(f"Invalid {label} price edit artifact: {path}")
    return payload


def artifact_key(edit: dict | sqlite3.Row) -> tuple[str, int]:
    """Stable workbook identity — row_id can move when a replica is reseeded."""
    sheet = edit["source_sheet"]
    row = edit["source_row"]
    if not sheet or not row:
        raise ValueError(
            f"SKU {edit['product_name']!r} has no workbook sheet/row provenance"
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


def _artifact_index(payload: dict) -> dict[tuple[str, int], dict]:
    return {
        (str(entry["source_sheet"]), int(entry["source_row"])): entry
        for entry in payload["edits"]
    }


def apply_to_artifact(
    edit: dict,
    payload: dict,
    by_key: dict[tuple[str, int], dict],
    label: str,
) -> bool:
    """Apply one latest journal row to an override artifact."""
    key = artifact_key(edit)
    entry = by_key.get(key)
    field = str(edit["field"])
    value = float(edit["new_value"])
    reverted = bool(edit["reverted"])

    if entry is None and reverted:
        return False
    if entry is None:
        entry = {
            "source_sheet": key[0],
            "source_row": key[1],
            "product_name": str(edit["product_name"]),
            "size": edit["size"],
        }
        payload["edits"].append(entry)
        by_key[key] = entry

    if reverted:
        if field not in entry:
            return False
        print(
            f"  {edit['product_name'][:44]:<46} {field:<12} "
            f"{entry.get(field)} -> baseline  [{label} revert]"
        )
        entry.pop(field, None)
        entry["updated_at"] = str(edit["edited_at"])
    elif entry.get(field) != value:
        print(
            f"  {edit['product_name'][:44]:<46} {field:<12} "
            f"{entry.get(field)} -> {value}  [{label}]"
        )
        entry[field] = value
        entry["updated_at"] = str(edit["edited_at"])
    else:
        return False

    if "source_cost" not in entry and "mrp" not in entry:
        payload["edits"].remove(entry)
        by_key.pop(key, None)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="report what would be folded without writing anything",
    )
    parser.add_argument(
        "--remote", action="store_true",
        help="fold unfolded edits from the production D1 database",
    )
    args = parser.parse_args()

    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    local_targets = {
        (str(product.get("source_sheet") or ""), int(product.get("source_row") or 0))
        for product in research["products"]
    }

    local = price_artifact(LOCAL_EDITS, "local")
    imported = price_artifact(IMPORTED_EDITS, "imported")
    local_by_key = _artifact_index(local)
    imported_by_key = _artifact_index(imported)

    local_applied = 0
    imported_applied = 0
    missing: list[str] = []
    folded_rows: dict[Path, list[int]] = {}
    remote_folded_rows: list[int] = []

    edit_sources: list[tuple[Path | None, dict[tuple[int, str], dict]]]
    if args.remote:
        edit_sources = [(None, remote_latest_edits())]
    else:
        edit_sources = [(path, latest_edits(path)) for path in replicas()]

    for path, edits in edit_sources:
        if not edits:
            continue

        for (row_id, _field), edit in edits.items():
            try:
                key = artifact_key(edit)
                origin = str(edit["sourcing_origin"])
                if origin == "local" and key not in local_targets:
                    raise ValueError(
                        f"Local SKU {edit['product_name']!r} does not resolve to "
                        f"{key[0]!r} row {key[1]} in the research file"
                    )
                changed = apply_to_artifact(
                    edit,
                    imported if origin == "imported" else local,
                    imported_by_key if origin == "imported" else local_by_key,
                    origin,
                )
                if changed:
                    if origin == "imported":
                        imported_applied += 1
                    else:
                        local_applied += 1
                if path is None:
                    remote_folded_rows.append(row_id)
                else:
                    folded_rows.setdefault(path, []).append(row_id)
            except ValueError as exc:
                missing.append(str(exc))

    if missing:
        print("\nWARNING: journalled edits with no canonical target (not folded):")
        for entry in missing[:10]:
            print(f"    {entry}")

    total_applied = local_applied + imported_applied
    if args.dry_run:
        print(
            f"\nDRY RUN — {local_applied} local + {imported_applied} imported "
            "override change(s) would be folded, nothing written."
        )
        return 0

    if local_applied:
        LOCAL_EDITS.write_text(
            json.dumps(local, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if imported_applied:
        IMPORTED_EDITS.write_text(
            json.dumps(imported, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    for path, row_ids in folded_rows.items():
        mark_folded(path, row_ids)
    if args.remote:
        mark_remote_folded(remote_folded_rows)

    source_label = f"remote {REMOTE_DATABASE}" if args.remote else "local replicas"
    print(
        f"\nFolded {local_applied} local override change(s) into {LOCAL_EDITS.name} and "
        f"{imported_applied} imported override change(s) into {IMPORTED_EDITS.name} "
        f"from {source_label}."
    )
    if total_applied:
        print(
            "Now rebuild and sync so the overrides survive:\n"
            "  uv run --with openpyxl --with rapidfuzz python3 build_matrix.py\n"
            "  bun run db:local:sync"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
