-- Sparse per-product pricing overrides.
--
-- Before: every override row pinned all seven engine fields, so a tuned SKU
-- stopped tracking later global-engine changes entirely (raise global delivery
-- and tuned SKUs silently kept the old delivery).
--
-- After: each column is nullable and NULL means "inherit the current global
-- parameter". A tuned SKU only pins the knobs the operator actually changed.
--
-- discount_type/discount_val stay a pair: overriding a discount requires both,
-- because an amount is meaningless under a percentage mode and vice versa.

PRAGMA foreign_keys = OFF;

CREATE TABLE product_pricing_overrides_sparse (
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

-- Carry existing overrides across, dropping any field that merely echoes the
-- current global value. Those fields were never deliberate pins: the old form
-- always submitted all seven inputs prefilled from global defaults, so echoed
-- values are indistinguishable from "untouched". Sparsifying them restores
-- global tracking for knobs the operator never actually changed.
INSERT INTO product_pricing_overrides_sparse
  (product_row_id, packaging, transport, delivery, cac,
   target_margin_pct, discount_type, discount_val, updated_at)
SELECT
  override.product_row_id,
  NULLIF(override.packaging, global.packaging),
  NULLIF(override.transport, global.transport),
  NULLIF(override.delivery, global.delivery),
  NULLIF(override.cac, global.cac),
  NULLIF(override.target_margin_pct, global.target_margin_pct),
  CASE
    WHEN override.discount_type IS global.discount_type
     AND override.discount_val IS global.discount_val THEN NULL
    ELSE override.discount_type
  END,
  CASE
    WHEN override.discount_type IS global.discount_type
     AND override.discount_val IS global.discount_val THEN NULL
    ELSE override.discount_val
  END,
  COALESCE(override.updated_at, CURRENT_TIMESTAMP)
FROM product_pricing_overrides AS override
CROSS JOIN (
  SELECT packaging, transport, delivery, cac, target_margin_pct,
         discount_type, discount_val
    FROM global_pricing_params WHERE id = 1
) AS global
WHERE override.product_row_id IS NOT NULL
  AND EXISTS (SELECT 1 FROM products WHERE row_id = override.product_row_id)
  -- Skip rows that matched global on every field: they pinned nothing.
  AND (
    override.packaging IS NOT global.packaging OR
    override.transport IS NOT global.transport OR
    override.delivery IS NOT global.delivery OR
    override.cac IS NOT global.cac OR
    override.target_margin_pct IS NOT global.target_margin_pct OR
    override.discount_type IS NOT global.discount_type OR
    override.discount_val IS NOT global.discount_val
  );

DROP TABLE product_pricing_overrides;
ALTER TABLE product_pricing_overrides_sparse RENAME TO product_pricing_overrides;

PRAGMA foreign_keys = ON;

