"""`db:local:sync` must not silently revert un-folded discovery results.

seed.sql opens by deleting every local listing and re-inserting from
`verified_marketplace_research.json`. Scrapers write straight into the D1
replica, so syncing before folding those findings back destroys them — and the
scraper's own "+80 new listings added" log is not evidence they survived.

That is exactly what happened once: a rebuild run between the scrape and the
fold-back wiped 80 freshly-verified listings, and nothing failed. These tests
pin the guard that now refuses the sync.
"""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import sync_local_d1  # noqa: E402

SCHEMA = ROOT / "schema.sql"

SEED_TEMPLATE = """\
INSERT INTO products (row_id, product_name, brand_name, size, manufactured_price, \
market_average_price, canonical_name, mrp_source_type, sourcing_origin) \
VALUES (1, 'Widget', 'Brand', '100ml', 100.0, 200.0, 'Widget', 'workbook', 'local');
INSERT INTO marketplace_listings (row_id, channel_name, price, url, matched_title, size, \
seller, confidence, available, verified) \
VALUES (1, 'Arogga', 180.0, 'https://example.com/a', 'Widget', '100ml', '', 100.0, 1, 1);
"""


def _replica(tmp: Path) -> Path:
    path = tmp / "replica.sqlite"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.execute(
        "INSERT INTO products (row_id, product_name, brand_name, size, "
        "manufactured_price, market_average_price, mrp_source_type, sourcing_origin) "
        "VALUES (1, 'Widget', 'Brand', '100ml', 100.0, 200.0, 'workbook', 'local')"
    )
    con.commit()
    con.close()
    return path


class UnfoldedListingGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(__file__).resolve().parent / "_tmp_sync_guard"
        self._tmp.mkdir(exist_ok=True)
        self._seed = self._tmp / "seed.sql"
        self._seed.write_text(SEED_TEMPLATE, encoding="utf-8")
        self._patch = mock.patch.object(sync_local_d1, "SEED_PATH", self._seed)
        self._patch.start()

    def tearDown(self) -> None:
        self._patch.stop()
        for child in self._tmp.iterdir():
            child.unlink()
        self._tmp.rmdir()

    def _add_listing(self, path: Path, channel: str, verified: int = 1) -> None:
        con = sqlite3.connect(path)
        con.execute(
            "INSERT INTO marketplace_listings (row_id, channel_name, price, url, "
            "matched_title, available, verified) "
            "VALUES (1, ?, 150.0, 'https://example.com/x', 'Widget', 1, ?)",
            (channel, verified),
        )
        con.commit()
        con.close()

    def test_a_listing_the_seed_carries_is_not_flagged(self) -> None:
        """The seed re-inserts Arogga, so it is not at risk."""
        path = _replica(self._tmp)
        self._add_listing(path, "Arogga")
        self.assertEqual([], sync_local_d1.unfolded_listings(path))

    def test_a_scraped_listing_absent_from_the_seed_is_flagged(self) -> None:
        """This is the 80-listing loss: present in D1, absent from the seed."""
        path = _replica(self._tmp)
        self._add_listing(path, "Shajgoj")
        orphans = sync_local_d1.unfolded_listings(path)
        self.assertEqual([("Widget", "Shajgoj")], orphans)

    def test_an_unverified_listing_is_not_flagged(self) -> None:
        """Workbook prices carry no product page and are re-seeded anyway."""
        path = _replica(self._tmp)
        self._add_listing(path, "Daraz", verified=0)
        self.assertEqual([], sync_local_d1.unfolded_listings(path))


if __name__ == "__main__":
    unittest.main()
