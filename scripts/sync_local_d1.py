"""Synchronize every project-local D1 replica from the canonical seed."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from migrate_local_d1 import D1_DIR, migrate_database, table_exists

ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "seed.sql"


def unfolded_listings(path: Path) -> list[tuple[str, str]]:
    """Verified local listings in the replica that seed.sql would destroy.

    seed.sql opens by deleting every local listing and re-inserting from
    `verified_marketplace_research.json`. A discovery pass writes straight into
    the replica, so syncing before folding those findings back silently reverts
    them — this cost 80 freshly-scraped listings once, and the scraper's own
    success log is no evidence they survived.

    Returns the (product_name, channel) pairs present in the replica but absent
    from the seed, so the caller can refuse to run.
    """
    import re

    seed_sql = SEED_PATH.read_text(encoding="utf-8")
    seeded = set(
        re.findall(
            r"INSERT INTO marketplace_listings [^\n]*?VALUES \((\d+), '([^']*)'",
            seed_sql,
        )
    )

    connection = sqlite3.connect(path, timeout=30)
    try:
        if not table_exists(connection, "products"):
            return []
        rows = connection.execute(
            "SELECT ml.row_id, ml.channel_name, p.product_name "
            "FROM marketplace_listings ml JOIN products p ON p.row_id = ml.row_id "
            "WHERE p.sourcing_origin = 'local' AND ml.verified = 1"
        ).fetchall()
    finally:
        connection.close()

    return [
        (str(name), str(channel))
        for row_id, channel, name in rows
        if (str(row_id), str(channel)) not in seeded
    ]


def unfolded_price_edits(path: Path) -> list[tuple[str, str, float]]:
    """Admin price edits in the replica that seed.sql would overwrite.

    seed.sql re-inserts every local product with
    `ON CONFLICT(row_id) DO UPDATE SET manufactured_price=excluded...`, so an
    edit that has not been folded into the separate local/imported override
    artifact is reverted by the next sync — the same silent-revert shape as the
    80-listing loss above.

    Returns (product_name, field, new_value) for every unfolded edit. Local
    edits fold into local_price_edits.json; imported edits fold into
    imported_price_edits.json, but either would be overwritten if skipped.
    """
    connection = sqlite3.connect(path, timeout=30)
    try:
        if not table_exists(connection, "price_edits"):
            return []
        rows = connection.execute(
            "SELECT p.product_name, e.field, e.new_value "
            "FROM price_edits e JOIN products p ON p.row_id = e.product_row_id "
            "WHERE e.folded = 0"
        ).fetchall()
    finally:
        connection.close()

    return [(str(name), str(field), float(value)) for name, field, value in rows]


def sync_database(path: Path, seed_sql: str) -> bool:
    migrate_database(path)
    connection = sqlite3.connect(path, timeout=30)
    connection.execute("PRAGMA busy_timeout = 30000")
    try:
        if not table_exists(connection, "products"):
            return False
        connection.executescript(seed_sql)
    finally:
        connection.close()

    # Re-seed imported products into the replica so syncing canonical local seed
    # never leaves the replica missing the imported book. A failure here is
    # fatal, not a warning: the local seed has already deleted and rewritten the
    # catalog, so swallowing this leaves the replica with an empty imported book
    # and the `/imported` route silently serving nothing.
    from seed_imported import seed as seed_imported

    seed_imported(path)

    return True


def main() -> None:
    if not SEED_PATH.exists():
        raise SystemExit(f"Missing canonical seed: {SEED_PATH}")

    force = "--force" in sys.argv
    seed_sql = SEED_PATH.read_text(encoding="utf-8")
    database_paths = sorted(D1_DIR.glob("*.sqlite")) if D1_DIR.exists() else []

    # Refuse to revert un-folded discovery results. seed.sql deletes every local
    # listing before re-inserting from the research file, so anything a scraper
    # wrote but nobody folded back is about to vanish without a trace.
    if not force:
        for path in database_paths:
            orphans = unfolded_listings(path)
            if orphans:
                print(
                    f"REFUSING TO SYNC: {path.name} holds {len(orphans)} verified local "
                    "listing(s) that seed.sql would delete.\n"
                    "These look like un-folded discovery results. Run:\n"
                    "  uv run --with rapidfuzz python3 scripts/fold_d1_listings_into_research.py\n"
                    "  uv run --with openpyxl --with rapidfuzz python3 build_matrix.py\n"
                    "then sync again (or pass --force to discard them).\n"
                )
                for name, channel in orphans[:10]:
                    print(f"    {channel:14s} {name[:56]}")
                if len(orphans) > 10:
                    print(f"    ... and {len(orphans) - 10} more")
                raise SystemExit(1)

            # Same failure mode, different table: an admin price edit that was
            # never folded is about to be overwritten by the seed's UPSERT.
            pending = unfolded_price_edits(path)
            if pending:
                print(
                    f"REFUSING TO SYNC: {path.name} holds {len(pending)} un-folded "
                    "price edit(s) that seed.sql would overwrite.\n"
                    "Run:\n"
                    "  uv run python3 scripts/fold_price_edits_into_research.py\n"
                    "  uv run --with openpyxl --with rapidfuzz python3 build_matrix.py\n"
                    "then sync again (or pass --force to discard them).\n"
                )
                for name, field, value in pending[:10]:
                    print(f"    {field:12s} -> {value:<10} {name[:48]}")
                if len(pending) > 10:
                    print(f"    ... and {len(pending) - 10} more")
                raise SystemExit(1)

    synced = 0
    for path in database_paths:
        if sync_database(path, seed_sql):
            synced += 1
            print(f"Synchronized {path.name}")

    if synced == 0:
        raise SystemExit("No initialized local D1 replicas were found. Apply schema.sql first.")


if __name__ == "__main__":
    main()
