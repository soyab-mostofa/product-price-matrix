-- Workbook MRP for local SKUs.
--
-- Before: a local SKU's MRP was taken from whatever the scraper found — the
-- brand's own store price when one existed, otherwise the mean of third-party
-- listings, and only as a last resort the workbook benchmark.
--
-- That inverted the source of truth. The workbook's cost basis is a trade
-- discount off its own Mkt (Avg) Price (40% / 30% / 25%, giving cost/MRP ratios
-- of exactly 0.60 / 0.70 / 0.75). A brand store runs promotions, so its
-- advertised checkout price drifts from that benchmark — and for six SKUs it
-- sat BELOW our sourcing cost, making a healthy margin read as an instant loss.
--
-- After: a local SKU's MRP is always the workbook benchmark, recorded as the
-- new 'workbook' provenance. Scraped listings are untouched: they keep their
-- prices, their verification state, and their deep links, and still render in
-- their own channel columns. They simply no longer overwrite the benchmark they
-- exist to be compared against.
--
-- Imported SKUs are unaffected — their MRP still comes from live listings,
-- because an importer's quoted cost carries no workbook retail benchmark.
--
-- SQLite cannot widen a CHECK constraint in place, so the products table is
-- rebuilt. Listings reference products by row_id, so foreign keys are held off
-- for the swap and the child rows are left untouched.

PRAGMA foreign_keys = OFF;

CREATE TABLE products_with_workbook_mrp (
  row_id INTEGER PRIMARY KEY,
  product_name TEXT NOT NULL,
  brand_name TEXT NOT NULL,
  size TEXT,
  manufactured_price REAL NOT NULL CHECK (manufactured_price >= 0),
  market_average_price REAL NOT NULL CHECK (market_average_price >= 0),
  canonical_name TEXT,
  mrp_source_type TEXT NOT NULL DEFAULT 'reference'
    CHECK (mrp_source_type IN ('official', 'third_party_avg', 'reference', 'workbook')),
  sourcing_origin TEXT NOT NULL DEFAULT 'local' CHECK (sourcing_origin IN ('local', 'imported')),
  category TEXT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO products_with_workbook_mrp
  (row_id, product_name, brand_name, size, manufactured_price,
   market_average_price, canonical_name, mrp_source_type,
   sourcing_origin, category, created_at)
SELECT
  row_id, product_name, brand_name, size, manufactured_price,
  market_average_price, canonical_name,
  -- Local rows are re-provenanced by the seed that follows this migration;
  -- relabel them here so the column never lies between the two steps.
  CASE WHEN sourcing_origin = 'local' THEN 'workbook' ELSE mrp_source_type END,
  sourcing_origin, category, COALESCE(created_at, CURRENT_TIMESTAMP)
FROM products;

DROP TABLE products;
ALTER TABLE products_with_workbook_mrp RENAME TO products;

-- Dropping the old table drops its indexes with it.
CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand_name);
CREATE INDEX IF NOT EXISTS idx_products_origin ON products(sourcing_origin);

PRAGMA foreign_keys = ON;
