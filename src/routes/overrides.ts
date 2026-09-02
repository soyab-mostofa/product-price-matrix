import { Hono } from 'hono'
import { zValidator } from '@hono/zod-validator'
import { z } from 'zod'
import { requireAdmin } from '../server/auth'
import { pricingSchema, productRowIdSchema } from '../server/pricing'
import type { AppEnv } from '../types'

const overrides = new Hono<AppEnv>()
const overrideSchema = pricingSchema.extend({ productRowId: productRowIdSchema })
const deleteSchema = z.object({ productRowId: productRowIdSchema.optional(), all: z.enum(['true']).optional() })

overrides.use('*', requireAdmin)

overrides.post('/', zValidator('json', overrideSchema), async (c) => {
  const { productRowId, ...params } = c.req.valid('json')
  const product = await c.env.DB.prepare('SELECT row_id FROM products WHERE row_id = ?').bind(productRowId).first()
  if (!product) return c.json({ success: false, error: 'Product not found' }, 404)
  await c.env.DB.prepare(
    `INSERT INTO product_pricing_overrides
       (product_row_id, packaging, transport, delivery, cac, target_margin_pct, discount_type, discount_val, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
     ON CONFLICT(product_row_id) DO UPDATE SET packaging=excluded.packaging,
       transport=excluded.transport, delivery=excluded.delivery, cac=excluded.cac,
       target_margin_pct=excluded.target_margin_pct, discount_type=excluded.discount_type,
       discount_val=excluded.discount_val, updated_at=CURRENT_TIMESTAMP`,
  ).bind(
    productRowId, params.packaging, params.transport, params.delivery, params.cac,
    params.targetMarginPct, params.discountType, params.discountVal,
  ).run()
  return c.json({ success: true, productRowId, override: params })
})

overrides.delete('/', zValidator('query', deleteSchema), async (c) => {
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
