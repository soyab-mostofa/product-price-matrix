"""Synchronize every project-local D1 replica from the canonical seed."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from migrate_local_d1 import D1_DIR, migrate_database, table_exists

ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "seed.sql"


def sync_database(path: Path, seed_sql: str) -> bool:
    migrate_database(path)
    connection = sqlite3.connect(path, timeout=30)
    connection.execute("PRAGMA busy_timeout = 30000")
    try:
        if not table_exists(connection, "products"):
            return False
        connection.executescript(seed_sql)
        return True
    finally:
        connection.close()


def main() -> None:
    if not SEED_PATH.exists():
        raise SystemExit(f"Missing canonical seed: {SEED_PATH}")

    seed_sql = SEED_PATH.read_text(encoding="utf-8")
    database_paths = sorted(D1_DIR.glob("*.sqlite")) if D1_DIR.exists() else []
    synced = 0
    for path in database_paths:
        if sync_database(path, seed_sql):
            synced += 1
            print(f"Synchronized {path.name}")

    if synced == 0:
        raise SystemExit("No initialized local D1 replicas were found. Apply schema.sql first.")


if __name__ == "__main__":
    main()
