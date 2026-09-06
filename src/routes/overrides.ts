import { Hono } from 'hono'
import { zValidator } from '@hono/zod-validator'
import { z } from 'zod'
import { requireAdmin } from '../server/auth'
import {
  PRICING_DEFAULTS,
  isEmptyOverride,
  pricingOverrideSchema,
  productRowIdSchema,
  sparsifyOverride,
} from '../server/pricing'
import type { AppEnv, PricingParams } from '../types'

const overrides = new Hono<AppEnv>()
const overrideSchema = z.object({ productRowId: productRowIdSchema, override: pricingOverrideSchema })
const deleteSchema = z.object({ productRowId: productRowIdSchema.optional(), all: z.enum(['true']).optional() })

// Every route here mutates stored pricing, so the whole router is admin-only.
// Overrides are read through GET /api/engine, which stays public.
overrides.use('*', requireAdmin)

async function readGlobalParams(db: D1Database): Promise<PricingParams> {
  const row = await db.prepare(
    `SELECT packaging, transport, delivery, cac, cac_type AS cacType,
       target_margin_pct AS targetMarginPct, discount_type AS discountType,
       discount_val AS discountVal FROM global_pricing_params WHERE id = 1`,
  ).first<PricingParams>()
  return row ?? { ...PRICING_DEFAULTS }
}

overrides.post('/', zValidator('json', overrideSchema, (result, c) => {
  if (!result.success) {
    const issue = result.error.issues[0]
    return c.json({ success: false, error: issue?.message || 'Validation failed' }, 400)
  }
}), async (c) => {
  const { productRowId, override } = c.req.valid('json')

  const product = await c.env.DB.prepare('SELECT row_id FROM products WHERE row_id = ?').bind(productRowId).first()
  if (!product) return c.json({ success: false, error: 'Product not found' }, 404)

  // A field equal to the current global value is not a tune: storing it would
  // freeze that field against future global changes.
  const globalParams = await readGlobalParams(c.env.DB)
  const sparse = sparsifyOverride(globalParams, override)

  // Nothing left to pin — the SKU simply follows global, so drop the row
  // instead of persisting an all-NULL override.
  if (isEmptyOverride(sparse)) {
    await c.env.DB.prepare('DELETE FROM product_pricing_overrides WHERE product_row_id = ?')
      .bind(productRowId).run()
    return c.json({ success: true, productRowId, override: null, cleared: true })
  }

  const updatedAt = new Date().toISOString()
  await c.env.DB.prepare(
    `INSERT INTO product_pricing_overrides
       (product_row_id, packaging, transport, delivery, cac, cac_type, target_margin_pct, discount_type, discount_val, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(product_row_id) DO UPDATE SET packaging=excluded.packaging,
       transport=excluded.transport, delivery=excluded.delivery, cac=excluded.cac,
       cac_type=excluded.cac_type, target_margin_pct=excluded.target_margin_pct,
       discount_type=excluded.discount_type,
       discount_val=excluded.discount_val, updated_at=excluded.updated_at`,
  ).bind(
    productRowId,
    sparse.packaging ?? null,
    sparse.transport ?? null,
    sparse.delivery ?? null,
    sparse.cac ?? null,
    sparse.cacType ?? null,
    sparse.targetMarginPct ?? null,
    sparse.discountType ?? null,
    sparse.discountVal ?? null,
    updatedAt,
  ).run()

  return c.json({ success: true, productRowId, override: { ...sparse, updatedAt } })
})

overrides.delete('/', zValidator('query', deleteSchema, (result, c) => {
  if (!result.success) {
    const issue = result.error.issues[0]
    return c.json({ success: false, error: issue?.message || 'Invalid query parameters' }, 400)
  }
}), async (c) => {
  const query = c.req.valid('query')
  if (query.all === 'true') {
    await c.env.DB.prepare('DELETE FROM product_pricing_overrides').run()
    return c.json({ success: true, clearedAll: true })
  }
  if (!query.productRowId) return c.json({ success: false, error: 'productRowId is required' }, 400)
  await c.env.DB.prepare('DELETE FROM product_pricing_overrides WHERE product_row_id = ?').bind(query.productRowId).run()
  return c.json({ success: true, productRowId: query.productRowId })
})

export default overrides
