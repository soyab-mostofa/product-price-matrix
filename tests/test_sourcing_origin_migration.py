from __future__ import annotations

from pathlib import Path
import sqlite3
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/0004_sourcing_origin.sql"
SCHEMA = ROOT / "schema.sql"

# Every migration that changes the shape of `products`, in order. The
# schema-agreement test walks this chain, so a new products migration must be
# appended here and mirrored into schema.sql or the test fails.
PRODUCT_SHAPE_MIGRATIONS = (
    MIGRATION,
    ROOT / "migrations/0006_workbook_mrp_for_local.sql",
    ROOT / "migrations/0007_workbook_provenance.sql",
    ROOT / "migrations/0009_price_edits.sql",
    ROOT / "migrations/0010_workbook_baselines.sql",
)

# The catalog as it stood before sourcing origin existed: every product was a
# Local SKU, but nothing recorded that fact.
PRE_ORIGIN_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE products (
  row_id INTEGER PRIMARY KEY,
  product_name TEXT NOT NULL,
  brand_name TEXT NOT NULL,
  size TEXT,
  manufactured_price REAL NOT NULL CHECK (manufactured_price >= 0),
  market_average_price REAL NOT NULL CHECK (market_average_price >= 0),
  canonical_name TEXT,
  mrp_source_type TEXT NOT NULL DEFAULT 'reference'
    CHECK (mrp_source_type IN ('official', 'third_party_avg', 'reference')),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE marketplace_listings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  row_id INTEGER NOT NULL,
  channel_name TEXT NOT NULL,
  price REAL NOT NULL CHECK (price > 0),
  url TEXT NOT NULL CHECK (url LIKE 'http://%' OR url LIKE 'https://%'),
  matched_title TEXT,
  size TEXT,
  seller TEXT,
  confidence REAL NOT NULL DEFAULT 100.0,
  available INTEGER NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (row_id) REFERENCES products(row_id) ON DELETE CASCADE,
  UNIQUE(row_id, channel_name)
);
CREATE INDEX idx_products_brand ON products(brand_name);
"""


def _pre_origin_database() -> sqlite3.Connection:
    """A catalog of Local SKUs that predates the Sourcing Origin axis."""
    connection = sqlite3.connect(":memory:")
    connection.executescript(PRE_ORIGIN_SCHEMA)
    for row_id, name, brand in [
        (2, "Bio-Screen Powder Sunblock SPF 50+", "Bio-Screen"),
        (3, "BioCare Vitamin C Whitening Facial Cream", "BioCare"),
        (4, "Guerniss Matte Lipstick 03", "Guerniss"),
    ]:
        connection.execute(
            "INSERT INTO products "
            "(row_id, product_name, brand_name, size, manufactured_price, market_average_price) "
            "VALUES (?, ?, ?, '50ml', 1237.5, 1402.0)",
            (row_id, name, brand),
        )
    return connection


class SourcingOriginMigrationTests(unittest.TestCase):
    def test_existing_catalog_backfills_to_local(self) -> None:
        """Every SKU predating the migration is manufactured and sourced locally."""
        connection = _pre_origin_database()
        connection.commit()

        connection.executescript(MIGRATION.read_text(encoding="utf-8"))

        origins = connection.execute(
            "SELECT row_id, sourcing_origin FROM products ORDER BY row_id"
        ).fetchall()
        self.assertEqual([(2, "local"), (3, "local"), (4, "local")], origins)

        unlabelled = connection.execute(
            "SELECT COUNT(*) FROM products WHERE sourcing_origin IS NULL"
        ).fetchone()[0]
        self.assertEqual(0, unlabelled)
        connection.close()

    def test_sourcing_origin_is_required_and_constrained(self) -> None:
        """A product is local or imported — never null, never anything else."""
        connection = _pre_origin_database()
        connection.commit()
        connection.executescript(MIGRATION.read_text(encoding="utf-8"))

        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO products (row_id, product_name, brand_name, "
                "manufactured_price, market_average_price, sourcing_origin) "
                "VALUES (90, 'No Origin', 'Example', 10, 20, NULL)"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO products (row_id, product_name, brand_name, "
                "manufactured_price, market_average_price, sourcing_origin) "
                "VALUES (91, 'Bad Origin', 'Example', 10, 20, 'wholesale')"
            )

        connection.execute(
            "INSERT INTO products (row_id, product_name, brand_name, "
            "manufactured_price, market_average_price, sourcing_origin, category) "
            "VALUES (92, 'CeraVe Moisturizing Cream 56ml', 'CeraVe', 930, 1465, 'imported', 'Skincare')"
        )
        stored = connection.execute(
            "SELECT sourcing_origin, category FROM products WHERE row_id = 92"
        ).fetchone()
        self.assertEqual(("imported", "Skincare"), stored)
        connection.close()

    def test_category_is_optional_and_local_skus_have_none(self) -> None:
        """Category comes from the imported workbook; local SKUs simply lack one."""
        connection = _pre_origin_database()
        connection.commit()
        connection.executescript(MIGRATION.read_text(encoding="utf-8"))

        categories = connection.execute(
            "SELECT DISTINCT category FROM products"
        ).fetchall()
        self.assertEqual([(None,)], categories)
        connection.close()

    def test_migration_preserves_existing_product_data(self) -> None:
        """Adding an axis must not disturb the catalog it labels."""
        connection = _pre_origin_database()
        before = connection.execute(
            "SELECT row_id, product_name, brand_name, size, manufactured_price, "
            "market_average_price, mrp_source_type FROM products ORDER BY row_id"
        ).fetchall()
        connection.commit()

        connection.executescript(MIGRATION.read_text(encoding="utf-8"))

        after = connection.execute(
            "SELECT row_id, product_name, brand_name, size, manufactured_price, "
            "market_average_price, mrp_source_type FROM products ORDER BY row_id"
        ).fetchall()
        self.assertEqual(before, after)
        connection.close()

    def test_listings_survive_the_migration(self) -> None:
        """Products are rebuilt by the migration; their listings must not be orphaned."""
        connection = _pre_origin_database()
        connection.execute(
            "INSERT INTO marketplace_listings (row_id, channel_name, price, url) "
            "VALUES (2, 'Shajgoj', 1402.0, 'https://shajgoj.com/item')"
        )
        connection.commit()

        connection.executescript(MIGRATION.read_text(encoding="utf-8"))

        listings = connection.execute(
            "SELECT row_id, channel_name, price FROM marketplace_listings"
        ).fetchall()
        self.assertEqual([(2, "Shajgoj", 1402.0)], listings)

        # The foreign key must still bite after the table rebuild.
        connection.execute("PRAGMA foreign_keys = ON")
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO marketplace_listings (row_id, channel_name, price, url) "
                "VALUES (999, 'Shajgoj', 100.0, 'https://shajgoj.com/ghost')"
            )
        connection.close()

    def test_schema_and_migration_agree_on_product_shape(self) -> None:
        """A fresh schema.sql database must match a migrated one.

        Applies every migration that reshapes `products`, not just this one:
        the point is that a database built by walking the migration chain ends
        up identical to one built from schema.sql, so a new migration that
        forgets to update schema.sql (or vice versa) fails here.
        """
        migrated = _pre_origin_database()
        migrated.commit()
        for migration in PRODUCT_SHAPE_MIGRATIONS:
            migrated.executescript(migration.read_text(encoding="utf-8"))
        migrated_columns = [
            (row[1], row[2], row[3])
            for row in migrated.execute("PRAGMA table_info(products)")
        ]

        fresh = sqlite3.connect(":memory:")
        fresh.executescript(SCHEMA.read_text(encoding="utf-8"))
        fresh_columns = [
            (row[1], row[2], row[3])
            for row in fresh.execute("PRAGMA table_info(products)")
        ]

        self.assertEqual(fresh_columns, migrated_columns)
        migrated.close()
        fresh.close()

    def test_brand_index_survives_the_rebuild(self) -> None:
        """The brand filter depends on this index; a table rebuild can silently drop it."""
        connection = _pre_origin_database()
        connection.commit()
        connection.executescript(MIGRATION.read_text(encoding="utf-8"))

        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'products'"
            )
        }
        self.assertIn("idx_products_brand", indexes)
        connection.close()


if __name__ == "__main__":
    unittest.main()
