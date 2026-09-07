-- Schema for Product Price Intelligence Matrix in Cloudflare D1

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS global_pricing_params (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  packaging REAL NOT NULL DEFAULT 45.0 CHECK (packaging >= 0 AND packaging <= 100000),
  transport REAL NOT NULL DEFAULT 0.0 CHECK (transport >= 0 AND transport <= 100000),
  delivery REAL NOT NULL DEFAULT 0.0 CHECK (delivery >= 0 AND delivery <= 100000),
  -- Flat BDT under cac_type 'amt'; a percentage of the SKU's sourcing price
  -- under 'pct'. Ships as 5% so acquisition cost stays proportionate to the
  -- trade-discount headroom rather than swamping the cheapest SKUs.
  cac REAL NOT NULL DEFAULT 5.0 CHECK (
    cac >= 0 AND
    ((cac_type = 'amt' AND cac <= 100000) OR (cac_type = 'pct' AND cac <= 100))
  ),
  cac_type TEXT NOT NULL DEFAULT 'pct' CHECK (cac_type IN ('amt', 'pct')),
  target_margin_pct REAL NOT NULL DEFAULT 0.0 CHECK (target_margin_pct >= 0 AND target_margin_pct < 100),
  discount_type TEXT NOT NULL DEFAULT 'pct' CHECK (discount_type IN ('pct', 'amt')),
  discount_val REAL NOT NULL DEFAULT 0.0 CHECK (
    discount_val >= 0 AND
    ((discount_type = 'pct' AND discount_val <= 100) OR (discount_type = 'amt' AND discount_val <= 1000000))
  ),
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
  row_id INTEGER PRIMARY KEY,
  product_name TEXT NOT NULL,
  brand_name TEXT NOT NULL,
  size TEXT,
  manufactured_price REAL NOT NULL CHECK (manufactured_price >= 0),
  market_average_price REAL NOT NULL CHECK (market_average_price >= 0),
  canonical_name TEXT,
  mrp_source_type TEXT NOT NULL DEFAULT 'reference' CHECK (mrp_source_type IN ('official', 'third_party_avg', 'reference', 'workbook', 'manual')),
  -- How this SKU reaches us: manufactured locally and bought from the
  -- manufacturer, or brought in and bought from an importer.
  sourcing_origin TEXT NOT NULL DEFAULT 'local' CHECK (sourcing_origin IN ('local', 'imported')),
  -- Skincare / Haircare / Fragrance for imported SKUs; local SKUs have none.
  category TEXT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  -- Workbook provenance: the sheet and 1-based Excel row this SKU was read
  -- from, so any price on screen can be walked back to a cell. Nullable —
  -- provenance, not a constraint. Declared last to match migration 0007,
  -- which appends them with ALTER TABLE ADD COLUMN.
  source_sheet TEXT,
  source_row INTEGER CHECK (source_row IS NULL OR source_row > 1)
);

CREATE TABLE IF NOT EXISTS marketplace_listings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  row_id INTEGER NOT NULL,
  channel_name TEXT NOT NULL,
  price REAL NOT NULL CHECK (price > 0),
  -- Null while a price is known but its product page is not.
  url TEXT CHECK (url IS NULL OR url LIKE 'http://%' OR url LIKE 'https://%'),
  matched_title TEXT,
  size TEXT,
  seller TEXT,
  confidence REAL NOT NULL DEFAULT 100.0 CHECK (confidence >= 0 AND confidence <= 100),
  available INTEGER NOT NULL DEFAULT 1 CHECK (available IN (0, 1)),
  -- Confirmed against a live product page, rather than seeded from a workbook.
  verified INTEGER NOT NULL DEFAULT 0 CHECK (verified IN (0, 1)),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (verified = 0 OR url IS NOT NULL),
  FOREIGN KEY (row_id) REFERENCES products(row_id) ON DELETE CASCADE,
  UNIQUE(row_id, channel_name)
);

-- Sparse per-product overrides: NULL means "inherit the current global value",
-- so a tuned SKU keeps tracking global cost changes for knobs it never pinned.
CREATE TABLE IF NOT EXISTS product_pricing_overrides (
  product_row_id INTEGER PRIMARY KEY,
  packaging REAL CHECK (packaging IS NULL OR (packaging >= 0 AND packaging <= 100000)),
  transport REAL CHECK (transport IS NULL OR (transport >= 0 AND transport <= 100000)),
  delivery REAL CHECK (delivery IS NULL OR (delivery >= 0 AND delivery <= 100000)),
  cac REAL CHECK (
    cac IS NULL OR (
      cac >= 0 AND
      ((cac_type = 'amt' AND cac <= 100000) OR (cac_type = 'pct' AND cac <= 100))
    )
  ),
  cac_type TEXT CHECK (cac_type IS NULL OR cac_type IN ('amt', 'pct')),
  target_margin_pct REAL CHECK (target_margin_pct IS NULL OR (target_margin_pct >= 0 AND target_margin_pct < 100)),
  discount_type TEXT CHECK (discount_type IS NULL OR discount_type IN ('pct', 'amt')),
  discount_val REAL CHECK (
    discount_val IS NULL OR (
      discount_val >= 0 AND
      ((discount_type = 'pct' AND discount_val <= 100) OR
       (discount_type = 'amt' AND discount_val <= 1000000))
    )
  ),
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  -- Discount is pinned as a pair or not at all.
  CHECK ((discount_type IS NULL) = (discount_val IS NULL)),
  -- CAC likewise: a value without its mode is ambiguous.
  CHECK ((cac_type IS NULL) = (cac IS NULL)),
  -- An override row must pin at least one field; otherwise it should not exist.
  CHECK (
    packaging IS NOT NULL OR transport IS NOT NULL OR delivery IS NOT NULL OR
    cac IS NOT NULL OR target_margin_pct IS NOT NULL OR discount_type IS NOT NULL
  ),
  FOREIGN KEY (product_row_id) REFERENCES products(row_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS admin_login_attempts (
  client_key TEXT PRIMARY KEY,
  failed_attempts INTEGER NOT NULL DEFAULT 0 CHECK (failed_attempts >= 0),
  window_started DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  locked_until DATETIME,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Append-only audit log of admin edits to Source Cost / MRP. Deliberately NOT
-- part of the read path: fetchCatalog reads the static prices straight off
-- `products`. This table exists so an edit survives the rebuild (see
-- scripts/fold_price_edits_into_research.py) and so a revert can reach the
-- workbook figure rather than the previous edit. See migrations/0009.
CREATE TABLE IF NOT EXISTS price_edits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_row_id INTEGER NOT NULL,
  field TEXT NOT NULL CHECK (field IN ('source_cost', 'mrp')),
  old_value REAL NOT NULL CHECK (old_value >= 0),
  new_value REAL NOT NULL CHECK (new_value >= 0),
  workbook_value REAL CHECK (workbook_value IS NULL OR workbook_value >= 0),
  edited_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  folded INTEGER NOT NULL DEFAULT 0 CHECK (folded IN (0, 1)),
  CHECK (new_value != old_value),
  FOREIGN KEY (product_row_id) REFERENCES products(row_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand_name);
CREATE INDEX IF NOT EXISTS idx_products_origin ON products(sourcing_origin);
CREATE INDEX IF NOT EXISTS idx_listings_channel ON marketplace_listings(channel_name);
CREATE INDEX IF NOT EXISTS idx_listings_row ON marketplace_listings(row_id);
CREATE INDEX IF NOT EXISTS idx_listings_available ON marketplace_listings(available);
CREATE INDEX IF NOT EXISTS idx_price_edits_row ON price_edits(product_row_id);
CREATE INDEX IF NOT EXISTS idx_price_edits_unfolded ON price_edits(folded) WHERE folded = 0;
