-- Expand-only migration for the live legacy Pages Functions schema.
-- Keep product_name until the authenticated Hono worker is deployed and verified;
-- a later contract migration may remove it.

ALTER TABLE products ADD COLUMN mrp_source_type TEXT NOT NULL DEFAULT 'reference';
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
   END;

ALTER TABLE product_pricing_overrides ADD COLUMN product_row_id INTEGER;
UPDATE product_pricing_overrides AS override
   SET product_row_id = (
     SELECT product.row_id
       FROM products AS product
      WHERE product.product_name = override.product_name
   )
 WHERE (SELECT COUNT(*)
          FROM products AS matching
         WHERE matching.product_name = override.product_name) = 1;

-- A full unique index is intentional: SQLite permits multiple NULL values while
-- providing the conflict target required by the new worker's row-ID upserts.
CREATE UNIQUE INDEX IF NOT EXISTS idx_overrides_product_row_id
  ON product_pricing_overrides(product_row_id);

CREATE TABLE IF NOT EXISTS admin_login_attempts (
  client_key TEXT PRIMARY KEY,
  failed_attempts INTEGER NOT NULL DEFAULT 0 CHECK (failed_attempts >= 0),
  window_started DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  locked_until DATETIME,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_listings_available ON marketplace_listings(available);

