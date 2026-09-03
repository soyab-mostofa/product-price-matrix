-- Unverified listings: a price that has no product page yet.
--
-- Before: every listing had to carry an http(s) URL, because every listing came
-- from a scrape that had already found the live page. That makes it impossible
-- to record price research done by hand — a competitor price read off a
-- spreadsheet is real information, it just has no link attached.
--
-- After: url is nullable and a `verified` flag says whether the price was
-- confirmed against a live product page. Existing listings were all scraped, so
-- they migrate as verified. Seeded prices arrive unverified and render without
-- a deep link until discovery finds and attaches their page.
--
-- The two states are kept honest by a CHECK: verified requires a URL. An
-- unverified listing may have one (a link found but not yet confirmed) or not.

PRAGMA foreign_keys = OFF;
BEGIN TRANSACTION;

CREATE TABLE marketplace_listings_with_verification (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  row_id INTEGER NOT NULL,
  channel_name TEXT NOT NULL,
  price REAL NOT NULL CHECK (price > 0),
  url TEXT CHECK (url IS NULL OR url LIKE 'http://%' OR url LIKE 'https://%'),
  matched_title TEXT,
  size TEXT,
  seller TEXT,
  confidence REAL NOT NULL DEFAULT 100.0 CHECK (confidence >= 0 AND confidence <= 100),
  available INTEGER NOT NULL DEFAULT 1 CHECK (available IN (0, 1)),
  verified INTEGER NOT NULL DEFAULT 0 CHECK (verified IN (0, 1)),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  -- Verified means confirmed against a live page, which requires the page.
  CHECK (verified = 0 OR url IS NOT NULL),
  FOREIGN KEY (row_id) REFERENCES products(row_id) ON DELETE CASCADE,
  UNIQUE(row_id, channel_name)
);

-- Everything already recorded came from a scraped, linked product page.
INSERT INTO marketplace_listings_with_verification
  (id, row_id, channel_name, price, url, matched_title, size, seller,
   confidence, available, verified, created_at)
SELECT
  id, row_id, channel_name, price, url, matched_title, size, seller,
  confidence, available, 1, COALESCE(created_at, CURRENT_TIMESTAMP)
FROM marketplace_listings;

DROP TABLE marketplace_listings;
ALTER TABLE marketplace_listings_with_verification RENAME TO marketplace_listings;

-- Dropping the old table drops its indexes with it.
CREATE INDEX IF NOT EXISTS idx_listings_channel ON marketplace_listings(channel_name);
CREATE INDEX IF NOT EXISTS idx_listings_row ON marketplace_listings(row_id);
CREATE INDEX IF NOT EXISTS idx_listings_available ON marketplace_listings(available);

COMMIT;
PRAGMA foreign_keys = ON;
