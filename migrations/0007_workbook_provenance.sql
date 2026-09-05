-- Workbook provenance: which sheet and which row each SKU came from.
--
-- Before: a figure on screen could be checked against the workbook only by
-- searching for the product name — and the catalog holds same-name SKUs that
-- differ only by pack size (Nature Beauty Healthy Glowing Body Lotion
-- 200/370ml; Orgagenic White Sandalwood 50/100g), so a name search lands on
-- the wrong row as often as the right one. Reconciling a price meant guessing.
--
-- After: every product carries the sheet it was read from and the 1-based
-- Excel row number, so any Source Cost or MRP on screen walks straight back to
-- a cell. `source_row` is the row as Excel numbers it (headers are row 1, so
-- data starts at row 2) — not an array index — because the point is that a
-- human can type it into the Name Box and land on the SKU.
--
-- Both columns are nullable: they are provenance, not a constraint, and a
-- migrated database backfills them on the next seed rather than failing here.
-- Additive columns only, so no table rebuild and no risk to existing rows.

ALTER TABLE products ADD COLUMN source_sheet TEXT;
ALTER TABLE products ADD COLUMN source_row INTEGER CHECK (source_row IS NULL OR source_row > 1);

-- Reconciliation walks sheet -> row, so index that order.
CREATE INDEX IF NOT EXISTS idx_products_source ON products(source_sheet, source_row);
