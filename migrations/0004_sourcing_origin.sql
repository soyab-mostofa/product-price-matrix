-- Sourcing Origin: how a SKU reaches us.
--
-- Before: every product in the catalog was manufactured in Bangladesh and
-- sourced direct from its manufacturer, but nothing recorded that. A second
-- book of business — products bought from importers — had nowhere to live.
--
-- After: every product declares a Sourcing Origin (local | imported). The 407
-- SKUs that predate this migration are all Local SKUs, so they backfill to
-- 'local'. Products also gain a nullable category, which imported SKUs carry
-- (Skincare / Haircare / Fragrance, from the source workbook tab) and local
-- SKUs leave empty.
--
-- SQLite cannot add a NOT NULL column with a CHECK to an existing table, so the
-- products table is rebuilt. Listings reference products by row_id, so foreign
-- keys are held off for the swap and the child rows are left untouched.

PRAGMA foreign_keys = OFF;
BEGIN TRANSACTION;

CREATE TABLE products_with_origin (
  row_id INTEGER PRIMARY KEY,
  product_name TEXT NOT NULL,
  brand_name TEXT NOT NULL,
  size TEXT,
  manufactured_price REAL NOT NULL CHECK (manufactured_price >= 0),
  market_average_price REAL NOT NULL CHECK (market_average_price >= 0),
  canonical_name TEXT,
  mrp_source_type TEXT NOT NULL DEFAULT 'reference' CHECK (mrp_source_type IN ('official', 'third_party_avg', 'reference')),
  sourcing_origin TEXT NOT NULL DEFAULT 'local' CHECK (sourcing_origin IN ('local', 'imported')),
  category TEXT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Everything already in the catalog is a Local SKU.
INSERT INTO products_with_origin
  (row_id, product_name, brand_name, size, manufactured_price,
   market_average_price, canonical_name, mrp_source_type,
   sourcing_origin, category, created_at)
SELECT
  row_id, product_name, brand_name, size, manufactured_price,
  market_average_price, canonical_name, mrp_source_type,
  'local', NULL, COALESCE(created_at, CURRENT_TIMESTAMP)
FROM products;

DROP TABLE products;
ALTER TABLE products_with_origin RENAME TO products;

-- Dropping the old table drops its indexes with it.
CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand_name);
CREATE INDEX IF NOT EXISTS idx_products_origin ON products(sourcing_origin);

COMMIT;
PRAGMA foreign_keys = ON;
