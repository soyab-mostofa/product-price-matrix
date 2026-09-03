-- Schema for Product Price Intelligence Matrix in Cloudflare D1

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS global_pricing_params (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  packaging REAL NOT NULL DEFAULT 20.0 CHECK (packaging >= 0 AND packaging <= 100000),
  transport REAL NOT NULL DEFAULT 0.0 CHECK (transport >= 0 AND transport <= 100000),
  delivery REAL NOT NULL DEFAULT 60.0 CHECK (delivery >= 0 AND delivery <= 100000),
  cac REAL NOT NULL DEFAULT 0.0 CHECK (cac >= 0 AND cac <= 100000),
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
  mrp_source_type TEXT NOT NULL DEFAULT 'reference' CHECK (mrp_source_type IN ('official', 'third_party_avg', 'reference')),
  -- How this SKU reaches us: manufactured locally and bought from the
  -- manufacturer, or brought in and bought from an importer.
  sourcing_origin TEXT NOT NULL DEFAULT 'local' CHECK (sourcing_origin IN ('local', 'imported')),
  -- Skincare / Haircare / Fragrance for imported SKUs; local SKUs have none.
  category TEXT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS marketplace_listings (
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

-- Sparse per-product overrides: NULL means "inherit the current global value",
-- so a tuned SKU keeps tracking global cost changes for knobs it never pinned.
CREATE TABLE IF NOT EXISTS product_pricing_overrides (
  product_row_id INTEGER PRIMARY KEY,
  packaging REAL CHECK (packaging IS NULL OR (packaging >= 0 AND packaging <= 100000)),
  transport REAL CHECK (transport IS NULL OR (transport >= 0 AND transport <= 100000)),
  delivery REAL CHECK (delivery IS NULL OR (delivery >= 0 AND delivery <= 100000)),
  cac REAL CHECK (cac IS NULL OR (cac >= 0 AND cac <= 100000)),
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

CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand_name);
CREATE INDEX IF NOT EXISTS idx_products_origin ON products(sourcing_origin);
CREATE INDEX IF NOT EXISTS idx_listings_channel ON marketplace_listings(channel_name);
CREATE INDEX IF NOT EXISTS idx_listings_row ON marketplace_listings(row_id);
CREATE INDEX IF NOT EXISTS idx_listings_available ON marketplace_listings(available);
