import { Hono } from 'hono'
import { zValidator } from '@hono/zod-validator'
import { requireAdmin } from '../server/auth'
import { PRICING_DEFAULTS, pricingSchema } from '../server/pricing'
import type { AppEnv, StoredPricingOverride } from '../types'

const engine = new Hono<AppEnv>()

interface GlobalRow {
  packaging: number
  transport: number
  delivery: number
  cac: number
  targetMarginPct: number
  discountType: 'pct' | 'amt'
  discountVal: number
}

/** Override rows are sparse: NULL means the SKU inherits that global field. */
interface OverrideRow {
  productRowId: number
  packaging: number | null
  transport: number | null
  delivery: number | null
  cac: number | null
  targetMarginPct: number | null
  discountType: 'pct' | 'amt' | null
  discountVal: number | null
  updatedAt: string | null
}

engine.get('/', async (c) => {
  const [globalResult, overridesResult] = await c.env.DB.batch([
    c.env.DB.prepare(`SELECT packaging, transport, delivery, cac,
      target_margin_pct AS targetMarginPct, discount_type AS discountType,
      discount_val AS discountVal FROM global_pricing_params WHERE id = 1`),
    c.env.DB.prepare(`SELECT product_row_id AS productRowId, packaging, transport, delivery, cac,
      target_margin_pct AS targetMarginPct, discount_type AS discountType,
      discount_val AS discountVal, updated_at AS updatedAt FROM product_pricing_overrides
      WHERE product_row_id IS NOT NULL`),
  ])
  const globalRow = globalResult?.results[0] as unknown as GlobalRow | undefined
  const globalParams = globalRow ?? PRICING_DEFAULTS
  const overrides: Record<string, StoredPricingOverride> = {}
  const overrideRows = (overridesResult?.results ?? []) as unknown as OverrideRow[]
  for (const row of overrideRows) {
    // Only pinned fields travel to the client; absent keys mean "inherit global".
    const override: StoredPricingOverride = { updatedAt: row.updatedAt }
    if (row.packaging !== null) override.packaging = row.packaging
    if (row.transport !== null) override.transport = row.transport
    if (row.delivery !== null) override.delivery = row.delivery
    if (row.cac !== null) override.cac = row.cac
    if (row.targetMarginPct !== null) override.targetMarginPct = row.targetMarginPct
    if (row.discountType !== null && row.discountVal !== null) {
      override.discountType = row.discountType
      override.discountVal = row.discountVal
    }
    overrides[String(row.productRowId)] = override
  }
  return c.json({ success: true, globalParams, overrides })
})

// Reading the engine is public: the dashboard renders selling prices for
// everyone. Writing it repositions every SKU at once, so it stays admin-only.
engine.post('/', requireAdmin, zValidator('json', pricingSchema, (result, c) => {
  if (!result.success) {
    const issue = result.error.issues[0]
    return c.json({ success: false, error: issue?.message || 'Validation failed' }, 400)
  }
}), async (c) => {
  const params = c.req.valid('json')
  await c.env.DB.prepare(
    `INSERT INTO global_pricing_params
       (id, packaging, transport, delivery, cac, target_margin_pct, discount_type, discount_val, updated_at)
     VALUES (1, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
     ON CONFLICT(id) DO UPDATE SET packaging=excluded.packaging, transport=excluded.transport,
       delivery=excluded.delivery, cac=excluded.cac, target_margin_pct=excluded.target_margin_pct,
       discount_type=excluded.discount_type, discount_val=excluded.discount_val, updated_at=CURRENT_TIMESTAMP`,
  ).bind(
    params.packaging, params.transport, params.delivery, params.cac,
    params.targetMarginPct, params.discountType, params.discountVal,
  ).run()
  return c.json({ success: true, globalParams: params })
})

export default engine
