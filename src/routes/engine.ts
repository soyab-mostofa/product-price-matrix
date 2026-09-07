import { Hono } from 'hono'
import { zValidator } from '@hono/zod-validator'
import { requireAdmin } from '../server/auth'
import { pricingSchema, readPricingState } from '../server/pricing'
import type { AppEnv } from '../types'

const engine = new Hono<AppEnv>()

engine.get('/', async (c) => {
  const state = await readPricingState(c.env.DB)
  return c.json({ success: true, ...state })
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
       (id, packaging, transport, delivery, cac, cac_type, target_margin_pct, discount_type, discount_val, updated_at)
     VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
     ON CONFLICT(id) DO UPDATE SET packaging=excluded.packaging, transport=excluded.transport,
       delivery=excluded.delivery, cac=excluded.cac, cac_type=excluded.cac_type,
       target_margin_pct=excluded.target_margin_pct,
       discount_type=excluded.discount_type, discount_val=excluded.discount_val, updated_at=CURRENT_TIMESTAMP`,
  ).bind(
    params.packaging, params.transport, params.delivery, params.cac, params.cacType,
    params.targetMarginPct, params.discountType, params.discountVal,
  ).run()
  return c.json({ success: true, globalParams: params })
})

export default engine
