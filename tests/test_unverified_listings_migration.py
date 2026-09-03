from __future__ import annotations

from pathlib import Path
import sqlite3
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/0005_unverified_listings.sql"
SCHEMA = ROOT / "schema.sql"

# Listings as they stood when every price had to come from a scraped page.
LINKED_ONLY_SCHEMA = """
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
  sourcing_origin TEXT NOT NULL DEFAULT 'local'
    CHECK (sourcing_origin IN ('local', 'imported')),
  category TEXT,
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
  confidence REAL NOT NULL DEFAULT 100.0 CHECK (confidence >= 0 AND confidence <= 100),
  available INTEGER NOT NULL DEFAULT 1 CHECK (available IN (0, 1)),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (row_id) REFERENCES products(row_id) ON DELETE CASCADE,
  UNIQUE(row_id, channel_name)
);
CREATE INDEX idx_listings_channel ON marketplace_listings(channel_name);
CREATE INDEX idx_listings_row ON marketplace_listings(row_id);
CREATE INDEX idx_listings_available ON marketplace_listings(available);
"""


def _linked_only_database() -> sqlite3.Connection:
    """A catalog whose every listing was confirmed against a live page."""
    connection = sqlite3.connect(":memory:")
    connection.executescript(LINKED_ONLY_SCHEMA)
    connection.execute(
        "INSERT INTO products (row_id, product_name, brand_name, "
        "manufactured_price, market_average_price) "
        "VALUES (2, 'Bio-Screen Powder Sunblock SPF 50+', 'Bio-Screen', 1237.5, 1402.0)"
    )
    connection.execute(
        "INSERT INTO marketplace_listings (row_id, channel_name, price, url, seller) "
        "VALUES (2, 'Shajgoj', 1402.0, 'https://shajgoj.com/item', 'Shajgoj')"
    )
    return connection


class UnverifiedListingMigrationTests(unittest.TestCase):
    def test_existing_listings_are_verified(self) -> None:
        """Every listing that predates this migration came from a confirmed page."""
        connection = _linked_only_database()
        connection.commit()

        connection.executescript(MIGRATION.read_text(encoding="utf-8"))

        rows = connection.execute(
            "SELECT channel_name, price, url, verified FROM marketplace_listings"
        ).fetchall()
        self.assertEqual([("Shajgoj", 1402.0, "https://shajgoj.com/item", 1)], rows)
        connection.close()

    def test_a_price_can_be_recorded_without_a_link(self) -> None:
        """A workbook price is real research; it just has no product page yet."""
        connection = _linked_only_database()
        connection.commit()
        connection.executescript(MIGRATION.read_text(encoding="utf-8"))

        connection.execute(
            "INSERT INTO marketplace_listings "
            "(row_id, channel_name, price, url, verified) "
            "VALUES (2, 'Klassy Missy', 630.0, NULL, 0)"
        )
        stored = connection.execute(
            "SELECT price, url, verified FROM marketplace_listings "
            "WHERE channel_name = 'Klassy Missy'"
        ).fetchone()
        self.assertEqual((630.0, None, 0), stored)
        connection.close()

    def test_a_present_url_must_still_be_http(self) -> None:
        """Relaxing NOT NULL must not let a junk link through."""
        connection = _linked_only_database()
        connection.commit()
        connection.executescript(MIGRATION.read_text(encoding="utf-8"))

        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO marketplace_listings (row_id, channel_name, price, url) "
                "VALUES (2, 'Arogga', 500.0, 'javascript:alert(1)')"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO marketplace_listings (row_id, channel_name, price, url) "
                "VALUES (2, 'Daraz', 500.0, 'ftp://example.com/x')"
            )
        connection.close()

    def test_a_verified_listing_must_carry_a_link(self) -> None:
        """Verified means confirmed against a live page — that requires the page."""
        connection = _linked_only_database()
        connection.commit()
        connection.executescript(MIGRATION.read_text(encoding="utf-8"))

        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO marketplace_listings "
                "(row_id, channel_name, price, url, verified) "
                "VALUES (2, 'Skinplus', 600.0, NULL, 1)"
            )
        connection.close()

    def test_one_listing_per_channel_still_holds(self) -> None:
        """The rebuild must not lose the uniqueness that keeps channels single."""
        connection = _linked_only_database()
        connection.commit()
        connection.executescript(MIGRATION.read_text(encoding="utf-8"))

        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO marketplace_listings (row_id, channel_name, price, url) "
                "VALUES (2, 'Shajgoj', 1500.0, 'https://shajgoj.com/other')"
            )
        connection.close()

    def test_listings_still_cascade_from_products(self) -> None:
        """A rebuilt child table can silently lose its foreign key."""
        connection = _linked_only_database()
        connection.commit()
        connection.executescript(MIGRATION.read_text(encoding="utf-8"))
        connection.execute("PRAGMA foreign_keys = ON")

        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO marketplace_listings (row_id, channel_name, price, url) "
                "VALUES (999, 'Arogga', 100.0, 'https://arogga.com/ghost')"
            )

        connection.execute("DELETE FROM products WHERE row_id = 2")
        remaining = connection.execute(
            "SELECT COUNT(*) FROM marketplace_listings"
        ).fetchone()[0]
        self.assertEqual(0, remaining)
        connection.close()

    def test_listing_indexes_survive_the_rebuild(self) -> None:
        connection = _linked_only_database()
        connection.commit()
        connection.executescript(MIGRATION.read_text(encoding="utf-8"))

        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' "
                "AND tbl_name = 'marketplace_listings'"
            )
        }
        self.assertIn("idx_listings_channel", indexes)
        self.assertIn("idx_listings_row", indexes)
        self.assertIn("idx_listings_available", indexes)
        connection.close()

    def test_schema_and_migration_agree_on_listing_shape(self) -> None:
        """A fresh schema.sql database must match a migrated one."""
        migrated = _linked_only_database()
        migrated.commit()
        migrated.executescript(MIGRATION.read_text(encoding="utf-8"))
        migrated_columns = [
            (row[1], row[2], row[3])
            for row in migrated.execute("PRAGMA table_info(marketplace_listings)")
        ]

        fresh = sqlite3.connect(":memory:")
        fresh.executescript(SCHEMA.read_text(encoding="utf-8"))
        fresh_columns = [
            (row[1], row[2], row[3])
            for row in fresh.execute("PRAGMA table_info(marketplace_listings)")
        ]

        self.assertEqual(fresh_columns, migrated_columns)
        migrated.close()
        fresh.close()


if __name__ == "__main__":
    unittest.main()
