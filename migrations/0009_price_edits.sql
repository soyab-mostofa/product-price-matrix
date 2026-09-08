-- Price edit journal: an append-only record of admin edits to Source Cost / MRP.
--
-- Both prices are STATIC scalars in `products`. The workbook's `Local product `
-- sheet derives its Final Price with a live formula
-- (`G = D - (D*E) + (D*F)`), but build_matrix.py reads the workbook with
-- data_only=True, so what lands in D1 is the resolved number. An admin edit
-- therefore overwrites a value, not a formula.
--
-- This table is an AUDIT LOG, not a resolution layer. Nothing in the read path
-- joins it — `fetchCatalog` still selects `manufactured_price` /
-- `market_average_price` straight off `products`. It exists for two jobs:
--
--   1. Durability. Rebuilds restore the workbook-derived baselines, then apply
--      manual pins from local_price_edits.json / imported_price_edits.json.
--      scripts/fold_price_edits_into_research.py reads unfolded rows here and
--      updates those separate override artifacts; it never rewrites excel_prices.
--   2. Provenance. `workbook_value` is the figure the workbook shipped, kept
--      separate from `old_value` (whatever the price was immediately before
--      this particular edit) so "revert to workbook" survives any number of
--      successive edits.
--
-- `folded` is the handshake with the rebuild pipeline: 0 means this edit exists
-- only in D1 and would be lost by the next `db:local:sync`, which is why
-- sync_local_d1.py refuses to run while any row here is unfolded.
--
-- Statement-only, with no BEGIN/COMMIT wrapper: remote D1 rejects an explicit
-- BEGIN TRANSACTION, and migrate_local_d1.py owns the transaction locally.

CREATE TABLE IF NOT EXISTS price_edits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_row_id INTEGER NOT NULL,
  field TEXT NOT NULL CHECK (field IN ('source_cost', 'mrp')),
  old_value REAL NOT NULL CHECK (old_value >= 0),
  new_value REAL NOT NULL CHECK (new_value >= 0),
  -- The workbook's own figure, so a revert reaches the source of truth rather
  -- than the previous edit. NULL only for a SKU with no workbook provenance.
  workbook_value REAL CHECK (workbook_value IS NULL OR workbook_value >= 0),
  edited_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  folded INTEGER NOT NULL DEFAULT 0 CHECK (folded IN (0, 1)),
  -- An edit that changes nothing is noise in an audit log.
  CHECK (new_value != old_value),
  FOREIGN KEY (product_row_id) REFERENCES products(row_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_price_edits_row ON price_edits(product_row_id);

-- The fold script and the sync guard both ask the same question — "is anything
-- still unfolded?" — so the partial index carries only those rows.
CREATE INDEX IF NOT EXISTS idx_price_edits_unfolded ON price_edits(folded) WHERE folded = 0;

-- 'manual' provenance for an admin-edited MRP.
--
-- An edited MRP is no longer the workbook benchmark, and mrp_source_type is
-- what the UI reads to say where a number came from. Leaving it as 'workbook'
-- would make an edited figure claim an authority it no longer has — precisely
-- the confusion migration 0006 existed to remove.
--
-- SQLite cannot widen a CHECK in place, so products is rebuilt, exactly as 0006
-- did to add 'workbook'. Foreign keys are held off for the swap so the listing
-- and override children are left untouched. Columns match the post-0007 shape,
-- with source_sheet/source_row carried through.

PRAGMA foreign_keys = OFF;

CREATE TABLE products_with_manual_mrp (
  row_id INTEGER PRIMARY KEY,
  product_name TEXT NOT NULL,
  brand_name TEXT NOT NULL,
  size TEXT,
  manufactured_price REAL NOT NULL CHECK (manufactured_price >= 0),
  market_average_price REAL NOT NULL CHECK (market_average_price >= 0),
  canonical_name TEXT,
  mrp_source_type TEXT NOT NULL DEFAULT 'reference'
    CHECK (mrp_source_type IN ('official', 'third_party_avg', 'reference', 'workbook', 'manual')),
  sourcing_origin TEXT NOT NULL DEFAULT 'local' CHECK (sourcing_origin IN ('local', 'imported')),
  category TEXT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  source_sheet TEXT,
  source_row INTEGER CHECK (source_row IS NULL OR source_row > 1)
);

-- Provenance is carried across unchanged: this migration widens what is legal,
-- it does not reclassify any existing row.
INSERT INTO products_with_manual_mrp
  (row_id, product_name, brand_name, size, manufactured_price,
   market_average_price, canonical_name, mrp_source_type,
   sourcing_origin, category, created_at, source_sheet, source_row)
SELECT
  row_id, product_name, brand_name, size, manufactured_price,
  market_average_price, canonical_name, mrp_source_type,
  sourcing_origin, category, COALESCE(created_at, CURRENT_TIMESTAMP),
  source_sheet, source_row
FROM products;

DROP TABLE products;
ALTER TABLE products_with_manual_mrp RENAME TO products;

-- Dropping the old table drops its indexes with it.
CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand_name);
CREATE INDEX IF NOT EXISTS idx_products_origin ON products(sourcing_origin);

PRAGMA foreign_keys = ON;
