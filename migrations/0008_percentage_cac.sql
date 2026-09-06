-- CAC as a percentage of the sourcing price.
--
-- Before: CAC was a flat BDT figure added to every unit. That is the same
-- mistake 0003's comments describe for delivery: the cost basis is a trade
-- discount off MRP (17-40%), so headroom is PROPORTIONAL to price — as little
-- as 12 BDT on the cheapest SKUs. A flat 40 BDT CAC swallowed that headroom
-- whole on the cheap end while barely registering on a 5,000 BDT fragrance.
--
-- After: CAC carries a mode. 'amt' keeps the old flat-BDT meaning; 'pct'
-- charges a share of the SKU's own sourcing price, so acquisition cost stays
-- proportionate across the catalog. The global engine ships at 5% ('pct').
--
-- cac/cac_type move as a PAIR, exactly like discount_type/discount_val: a bare
-- value inheriting a mode would let a global amt->pct switch silently
-- reinterpret a pinned 40 BDT as 40% of source cost. SQLite cannot add a CHECK
-- to an existing table, and the range on `cac` now depends on `cac_type`, so
-- both tables are rebuilt rather than altered.
--
-- Existing per-SKU pins are BDT figures, so they backfill to 'amt' and keep the
-- exact prices they had. The GLOBAL row is deliberately moved to 5% 'pct' —
-- this migration intentionally repositions every SKU that does not pin its own
-- CAC, which is the point of the change.

PRAGMA foreign_keys = OFF;

CREATE TABLE global_pricing_params_cac (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  packaging REAL NOT NULL DEFAULT 45.0 CHECK (packaging >= 0 AND packaging <= 100000),
  transport REAL NOT NULL DEFAULT 0.0 CHECK (transport >= 0 AND transport <= 100000),
  delivery REAL NOT NULL DEFAULT 0.0 CHECK (delivery >= 0 AND delivery <= 100000),
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

-- Every flat cost carries over untouched; CAC is repositioned to the new 5%
-- default rather than converted, because no single BDT figure is equivalent to
-- a percentage across SKUs of different cost.
INSERT INTO global_pricing_params_cac
  (id, packaging, transport, delivery, cac, cac_type, target_margin_pct,
   discount_type, discount_val, updated_at)
SELECT id, packaging, transport, delivery, 5.0, 'pct', target_margin_pct,
       discount_type, discount_val, CURRENT_TIMESTAMP
  FROM global_pricing_params WHERE id = 1;

DROP TABLE global_pricing_params;
ALTER TABLE global_pricing_params_cac RENAME TO global_pricing_params;

-- Seed the row if the source table was empty, so a fresh database still has an
-- engine to read.
INSERT INTO global_pricing_params
  (id, packaging, transport, delivery, cac, cac_type, target_margin_pct, discount_type, discount_val)
VALUES (1, 45.0, 0.0, 0.0, 5.0, 'pct', 0.0, 'pct', 0.0)
ON CONFLICT(id) DO NOTHING;

CREATE TABLE product_pricing_overrides_cac (
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

-- A pinned CAC was always a BDT figure, so it backfills to 'amt' and the SKU
-- keeps the exact price it had. Rows that pinned no CAC stay NULL and follow
-- the new 5% global.
INSERT INTO product_pricing_overrides_cac
  (product_row_id, packaging, transport, delivery, cac, cac_type,
   target_margin_pct, discount_type, discount_val, updated_at)
SELECT product_row_id, packaging, transport, delivery, cac,
       CASE WHEN cac IS NULL THEN NULL ELSE 'amt' END,
       target_margin_pct, discount_type, discount_val,
       COALESCE(updated_at, CURRENT_TIMESTAMP)
  FROM product_pricing_overrides;

DROP TABLE product_pricing_overrides;
ALTER TABLE product_pricing_overrides_cac RENAME TO product_pricing_overrides;

PRAGMA foreign_keys = ON;
