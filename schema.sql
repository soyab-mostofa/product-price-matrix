-- Schema for Product Price Intelligence Matrix in Cloudflare D1

CREATE TABLE IF NOT EXISTS global_pricing_params (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  packaging REAL NOT NULL DEFAULT 20.0,
  transport REAL NOT NULL DEFAULT 40.0,
  delivery REAL NOT NULL DEFAULT 60.0,
  cac REAL NOT NULL DEFAULT 80.0,
  target_margin_pct REAL NOT NULL DEFAULT 25.0,
  discount_type TEXT NOT NULL DEFAULT 'pct', -- 'pct' or 'amt'
  discount_val REAL NOT NULL DEFAULT 10.0,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
  row_id INTEGER PRIMARY KEY,
  product_name TEXT NOT NULL,
  brand_name TEXT NOT NULL,
  size TEXT,
  manufactured_price REAL NOT NULL,
  market_average_price REAL NOT NULL,
  canonical_name TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS marketplace_listings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  row_id INTEGER NOT NULL,
  channel_name TEXT NOT NULL,
  price REAL NOT NULL,
  url TEXT NOT NULL,
  matched_title TEXT,
  size TEXT,
  seller TEXT,
  confidence REAL DEFAULT 100.0,
  available INTEGER DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (row_id) REFERENCES products(row_id) ON DELETE CASCADE,
  UNIQUE(row_id, channel_name)
);

CREATE TABLE IF NOT EXISTS product_pricing_overrides (
  product_name TEXT PRIMARY KEY,
  packaging REAL,
  transport REAL,
  delivery REAL,
  cac REAL,
  target_margin_pct REAL,
  discount_type TEXT,
  discount_val REAL,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand_name);
CREATE INDEX IF NOT EXISTS idx_listings_channel ON marketplace_listings(channel_name);
CREATE INDEX IF NOT EXISTS idx_listings_row ON marketplace_listings(row_id);
