"""Upgrade every Wrangler/Miniflare local D1 replica for this project.

Vite and `wrangler d1 execute --local` can resolve the same binding to
different hashed SQLite files. Migrating every project-local replica keeps both
dev paths on the current schema.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D1_DIR = ROOT / ".wrangler/state/v3/d1/miniflare-D1DatabaseObject"
SPARSE_OVERRIDES_MIGRATION_PATH = ROOT / "migrations/0003_sparse_pricing_overrides.sql"
SOURCING_ORIGIN_MIGRATION_PATH = ROOT / "migrations/0004_sourcing_origin.sql"
UNVERIFIED_LISTINGS_MIGRATION_PATH = ROOT / "migrations/0005_unverified_listings.sql"


def _unwrapped(path: Path) -> str:
    """A migration body, minus its transaction/pragma wrapper.

    migrate_database() already owns the transaction, and sqlite3 refuses a
    nested BEGIN, so the file's own BEGIN/COMMIT lines are stripped here rather
    than duplicated in Python.
    """
    text = path.read_text(encoding="utf-8")
    skipped = ("PRAGMA foreign_keys", "BEGIN TRANSACTION;", "COMMIT;")
    return "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith(skipped)
    )


def _sparse_overrides_migration() -> str:
    """The 0003 migration body, minus the transaction/pragma wrapper."""
    return _unwrapped(SPARSE_OVERRIDES_MIGRATION_PATH)


def _sourcing_origin_migration() -> str:
    """The 0004 migration body, minus the transaction/pragma wrapper."""
    return _unwrapped(SOURCING_ORIGIN_MIGRATION_PATH)


def _unverified_listings_migration() -> str:
    """The 0005 migration body, minus the transaction/pragma wrapper."""
    return _unwrapped(UNVERIFIED_LISTINGS_MIGRATION_PATH)


def columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _overrides_are_dense(connection: sqlite3.Connection) -> bool:
    """True while product_pricing_overrides still forces all seven fields.

    PRAGMA table_info reports notnull=1 for the pre-0003 shape; the sparse
    table leaves every tunable column nullable.
    """
    return any(
        str(row[1]) != "product_row_id" and str(row[1]) != "updated_at" and row[3] == 1
        for row in connection.execute("PRAGMA table_info(product_pricing_overrides)")
    )


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def migrate_database(path: Path) -> list[str]:
    changes: list[str] = []
    connection = sqlite3.connect(path, timeout=15)
    connection.execute("PRAGMA busy_timeout = 15000")

    try:
        if not table_exists(connection, "products"):
            return changes

        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("BEGIN IMMEDIATE")

        if "mrp_source_type" not in columns(connection, "products"):
            connection.execute(
                "ALTER TABLE products ADD COLUMN mrp_source_type TEXT NOT NULL "
                "DEFAULT 'reference' CHECK (mrp_source_type IN "
                "('official', 'third_party_avg', 'reference'))"
            )
            connection.execute(
                """
                UPDATE products
                   SET mrp_source_type = CASE
                     WHEN EXISTS (
                       SELECT 1 FROM marketplace_listings listing
                        WHERE listing.row_id = products.row_id
                          AND listing.channel_name = 'Official Store'
                          AND listing.available = 1
                     ) THEN 'official'
                     WHEN EXISTS (
                       SELECT 1 FROM marketplace_listings listing
                        WHERE listing.row_id = products.row_id
                          AND listing.available = 1
                     ) THEN 'third_party_avg'
                     ELSE 'reference'
                   END
                """
            )
            changes.append("products.mrp_source_type")

        if table_exists(connection, "product_pricing_overrides"):
            override_columns = columns(connection, "product_pricing_overrides")
            if "product_row_id" not in override_columns and "product_name" in override_columns:
                connection.executescript(
                    """
                    CREATE TABLE product_pricing_overrides_new (
                      product_row_id INTEGER PRIMARY KEY,
                      packaging REAL NOT NULL CHECK (packaging >= 0 AND packaging <= 100000),
                      transport REAL NOT NULL CHECK (transport >= 0 AND transport <= 100000),
                      delivery REAL NOT NULL CHECK (delivery >= 0 AND delivery <= 100000),
                      cac REAL NOT NULL CHECK (cac >= 0 AND cac <= 100000),
                      target_margin_pct REAL NOT NULL CHECK (target_margin_pct >= 0 AND target_margin_pct < 100),
                      discount_type TEXT NOT NULL CHECK (discount_type IN ('pct', 'amt')),
                      discount_val REAL NOT NULL CHECK (
                        discount_val >= 0 AND
                        ((discount_type = 'pct' AND discount_val <= 100) OR
                         (discount_type = 'amt' AND discount_val <= 1000000))
                      ),
                      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (product_row_id) REFERENCES products(row_id) ON DELETE CASCADE
                    );
                    INSERT INTO product_pricing_overrides_new
                      (product_row_id, packaging, transport, delivery, cac,
                       target_margin_pct, discount_type, discount_val, updated_at)
                    SELECT product.row_id, override.packaging, override.transport,
                           override.delivery, override.cac, override.target_margin_pct,
                           override.discount_type, override.discount_val, override.updated_at
                      FROM product_pricing_overrides override
                      JOIN products product ON product.product_name = override.product_name
                     WHERE (SELECT COUNT(*) FROM products matching
                             WHERE matching.product_name = override.product_name) = 1;
                    DROP TABLE product_pricing_overrides;
                    ALTER TABLE product_pricing_overrides_new
                      RENAME TO product_pricing_overrides;
                    """
                )
                changes.append("product_pricing_overrides.product_row_id")

            if _overrides_are_dense(connection):
                connection.executescript(_sparse_overrides_migration())
                changes.append("product_pricing_overrides.sparse")

        if "sourcing_origin" not in columns(connection, "products"):
            connection.executescript(_sourcing_origin_migration())
            changes.append("products.sourcing_origin")

        if "verified" not in columns(connection, "marketplace_listings"):
            connection.executescript(_unverified_listings_migration())
            changes.append("marketplace_listings.verified")

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_login_attempts (
              client_key TEXT PRIMARY KEY,
              failed_attempts INTEGER NOT NULL DEFAULT 0 CHECK (failed_attempts >= 0),
              window_started DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              locked_until DATETIME,
              updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_listings_available "
            "ON marketplace_listings(available)"
        )
        connection.commit()
        return changes
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def bootstrap_database(path: Path) -> None:
    """Create an empty replica from schema.sql and the canonical seed."""
    schema_sql = (ROOT / "schema.sql").read_text(encoding="utf-8")
    seed_path = ROOT / "seed.sql"
    connection = sqlite3.connect(path, timeout=30)
    try:
        connection.executescript(schema_sql)
        if seed_path.exists():
            connection.executescript(seed_path.read_text(encoding="utf-8"))
    finally:
        connection.close()


def main() -> None:
    database_paths = sorted(D1_DIR.glob("*.sqlite")) if D1_DIR.exists() else []
    initialized = [path for path in database_paths if _has_products(path)]

    if not initialized:
        D1_DIR.mkdir(parents=True, exist_ok=True)
        target = database_paths[0] if database_paths else D1_DIR / "product-price-matrix-db.sqlite"
        bootstrap_database(target)
        print(f"Bootstrapped local D1 replica from schema.sql + seed.sql: {target.name}")
        return

    migrated = 0
    for path in initialized:
        changes = migrate_database(path)
        if changes:
            migrated += 1
            print(f"Migrated {path.name}: {', '.join(changes)}")

    if migrated == 0:
        print("Local D1 replicas already match the current schema.")


def _has_products(path: Path) -> bool:
    connection = sqlite3.connect(path, timeout=15)
    try:
        return table_exists(connection, "products")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
