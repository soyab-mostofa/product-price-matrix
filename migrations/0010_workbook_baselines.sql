-- Immutable workbook baselines and explicit revert markers.
--
-- `manufactured_price` / `market_average_price` are the CURRENT static values
-- shown by the app. Admins may override them. These baseline columns are the
-- immutable figures imported from `Roopelle.com Final Excel Sheet.xlsx`, so a
-- revert never guesses from the first audit row and the parity gate can still
-- compare the commercial source of truth to the paisa.
--
-- Existing databases may already carry active manual overrides. When the journal
-- has captured a workbook value, that value wins the backfill; only never-edited
-- fields fall back to their current column. Subsequent seed runs write the
-- baseline columns directly from the workbook.

ALTER TABLE products ADD COLUMN workbook_source_cost REAL
  CHECK (workbook_source_cost IS NULL OR workbook_source_cost >= 0);
ALTER TABLE products ADD COLUMN workbook_mrp REAL
  CHECK (workbook_mrp IS NULL OR workbook_mrp >= 0);

UPDATE products
   SET workbook_source_cost = COALESCE(
         (SELECT first_edit.workbook_value FROM price_edits first_edit
           WHERE first_edit.product_row_id = products.row_id
             AND first_edit.field = 'source_cost'
             AND first_edit.workbook_value IS NOT NULL
           ORDER BY first_edit.id ASC LIMIT 1),
         manufactured_price
       ),
       workbook_mrp = COALESCE(
         (SELECT first_edit.workbook_value FROM price_edits first_edit
           WHERE first_edit.product_row_id = products.row_id
             AND first_edit.field = 'mrp'
             AND first_edit.workbook_value IS NOT NULL
           ORDER BY first_edit.id ASC LIMIT 1),
         market_average_price
       )
 WHERE workbook_source_cost IS NULL OR workbook_mrp IS NULL;

-- Comparing new_value to workbook_value is not a reliable way to identify an
-- undo: imported MRP reverts resolve from current verified listings and can be
-- different from the workbook fallback. Record the intent explicitly.
--
-- The journal is rebuilt to permit a provenance-only revert where the resolved
-- price happens to equal the manual price (old_value = new_value). That is not
-- noise: it clears `manual` and records a real admin action.
PRAGMA foreign_keys = OFF;

CREATE TABLE price_edits_with_revert (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_row_id INTEGER NOT NULL,
  field TEXT NOT NULL CHECK (field IN ('source_cost', 'mrp')),
  old_value REAL NOT NULL CHECK (old_value >= 0),
  new_value REAL NOT NULL CHECK (new_value >= 0),
  workbook_value REAL CHECK (workbook_value IS NULL OR workbook_value >= 0),
  edited_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  folded INTEGER NOT NULL DEFAULT 0 CHECK (folded IN (0, 1)),
  reverted INTEGER NOT NULL DEFAULT 0 CHECK (reverted IN (0, 1)),
  CHECK (new_value != old_value OR reverted = 1),
  FOREIGN KEY (product_row_id) REFERENCES products(row_id) ON DELETE CASCADE
);

INSERT INTO price_edits_with_revert
  (id, product_row_id, field, old_value, new_value, workbook_value,
   edited_at, folded, reverted)
SELECT id, product_row_id, field, old_value, new_value, workbook_value,
       edited_at, folded,
       CASE WHEN workbook_value IS NOT NULL AND new_value = workbook_value
            THEN 1 ELSE 0 END
  FROM price_edits;

DROP TABLE price_edits;
ALTER TABLE price_edits_with_revert RENAME TO price_edits;

CREATE INDEX idx_price_edits_row ON price_edits(product_row_id);
CREATE INDEX idx_price_edits_unfolded ON price_edits(folded) WHERE folded = 0;

PRAGMA foreign_keys = ON;
