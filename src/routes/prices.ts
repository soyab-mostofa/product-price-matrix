import { Hono } from 'hono'
import { zValidator } from '@hono/zod-validator'
import { z } from 'zod'
import { requireAdmin } from '../server/auth'
import { productRowIdSchema } from '../server/pricing'
import type { AppEnv, MrpSourceType, SourcingOrigin } from '../types'

const prices = new Hono<AppEnv>()

/**
 * The two editable prices, named as the UI names them rather than as the
 * columns are named. `manufactured_price` is a historical column name that
 * means "what we pay to acquire one unit" — see CONTEXT.md.
 */
const PRICE_COLUMNS = {
  source_cost: 'manufactured_price',
  mrp: 'market_average_price',
} as const

type PriceField = keyof typeof PRICE_COLUMNS

/**
 * Bounded well above the dearest SKU in the catalog but far below anything that
 * would suggest a fat-fingered paste. Mirrors the CHECK constraints in
 * migrations/0009_price_edits.sql.
 */
const priceValue = z.coerce.number().finite().min(0).max(1_000_000)

const editSchema = z.object({
  productRowId: productRowIdSchema,
  field: z.enum(['source_cost', 'mrp']),
  value: priceValue,
})

const revertSchema = z.object({
  productRowId: productRowIdSchema,
  field: z.enum(['source_cost', 'mrp']),
})

// Every route here mutates stored pricing, so the whole router is admin-only.
// Prices are read through GET /api/products, which stays public.
prices.use('*', requireAdmin)

interface ProductPriceRow {
  manufactured_price: number
  market_average_price: number
  workbook_source_cost: number | null
  workbook_mrp: number | null
  sourcing_origin: SourcingOrigin
  mrp_source_type: MrpSourceType
}

function workbookBaseline(product: ProductPriceRow, field: PriceField): number {
  const baseline = field === 'source_cost' ? product.workbook_source_cost : product.workbook_mrp
  if (baseline === null) {
    throw new Error(`Missing workbook baseline for ${field}`)
  }
  return baseline
}

prices.patch('/', zValidator('json', editSchema, (result, c) => {
  if (!result.success) {
    const issue = result.error.issues[0]
    return c.json({ success: false, error: issue?.message || 'Validation failed' }, 400)
  }
}), async (c) => {
  const { productRowId, field, value } = c.req.valid('json')

  const product = await c.env.DB.prepare(
    `SELECT manufactured_price, market_average_price, workbook_source_cost,
            workbook_mrp, sourcing_origin, mrp_source_type
       FROM products WHERE row_id = ?`,
  ).bind(productRowId).first<ProductPriceRow>()
  if (!product) return c.json({ success: false, error: 'Product not found' }, 404)

  const column = PRICE_COLUMNS[field]
  const current = field === 'source_cost' ? product.manufactured_price : product.market_average_price

  // An edit that changes nothing is noise in an audit log, and the journal's
  // CHECK would reject it anyway. Answer honestly instead of erroring.
  if (current === value) {
    return c.json({ success: true, productRowId, field, value, changed: false })
  }

  const baseline = workbookBaseline(product, field)
  const editedAt = new Date().toISOString()

  // Typing the baseline figure by hand IS a revert. Journalling it as an ordinary
  // edit would leave the field marked EDITED forever: the marker reads the latest
  // unreverted row, and DELETE would then short-circuit because the current value
  // already equals its target, never appending the reverted row that clears it.
  const restoresBaseline = value === baseline

  // An edited MRP is no longer the workbook benchmark, and mrp_source_type is
  // what the UI reads to say where a number came from. Source cost has no
  // equivalent provenance column.
  let mrpSourceType = product.mrp_source_type
  if (field === 'mrp') {
    mrpSourceType = restoresBaseline && product.sourcing_origin === 'local' ? 'workbook' : 'manual'
  }

  const statements = [
    field === 'mrp'
      ? c.env.DB.prepare(
          `UPDATE products SET ${column} = ?1, mrp_source_type = ?3 WHERE row_id = ?2`,
        ).bind(value, productRowId, mrpSourceType)
      : c.env.DB.prepare(
          `UPDATE products SET ${column} = ?1 WHERE row_id = ?2`,
        ).bind(value, productRowId),
    c.env.DB.prepare(
      `INSERT INTO price_edits
         (product_row_id, field, old_value, new_value, workbook_value, edited_at, folded, reverted)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, 0, ?7)`,
    ).bind(productRowId, field, current, value, baseline, editedAt, restoresBaseline ? 1 : 0),
  ]

  await c.env.DB.batch(statements)

  return c.json({
    success: true,
    productRowId,
    field,
    value,
    changed: true,
    reverted: restoresBaseline,
    previousValue: current,
    workbookValue: baseline,
    editedAt,
    mrpSourceType,
  })
})

/**
 * Revert one field to the figure the workbook shipped.
 *
 * The revert is itself journalled: it is an edit like any other, so the trail
 * stays complete and the fold script carries the restored value through the
 * rebuild rather than leaving the research file holding the edited number.
 */
interface ImportedMrpResolution {
  value: number
  source: Exclude<MrpSourceType, 'workbook' | 'manual'>
}

/** Resolve an imported MRP exactly as scripts/seed_imported.py does. */
async function resolveImportedMrp(
  db: D1Database,
  productRowId: number,
  workbookFallback: number,
): Promise<ImportedMrpResolution> {
  const official = await db.prepare(
    `SELECT price FROM marketplace_listings
      WHERE row_id = ?1 AND channel_name = 'Official Store'
        AND available = 1 AND verified = 1`,
  ).bind(productRowId).first<{ price: number }>()
  if (official) return { value: Number(official.price), source: 'official' }

  const thirdParty = await db.prepare(
    `SELECT AVG(price) AS price FROM marketplace_listings
      WHERE row_id = ?1 AND available = 1 AND verified = 1`,
  ).bind(productRowId).first<{ price: number | null }>()
  if (thirdParty?.price !== null && thirdParty?.price !== undefined) {
    return { value: Number(thirdParty.price), source: 'third_party_avg' }
  }

  return { value: workbookFallback, source: 'reference' }
}

prices.delete('/', zValidator('query', revertSchema, (result, c) => {
  if (!result.success) {
    const issue = result.error.issues[0]
    return c.json({ success: false, error: issue?.message || 'Invalid query parameters' }, 400)
  }
}), async (c) => {
  const { productRowId, field } = c.req.valid('query')

  const product = await c.env.DB.prepare(
    `SELECT manufactured_price, market_average_price, workbook_source_cost,
            workbook_mrp, sourcing_origin, mrp_source_type
       FROM products WHERE row_id = ?`,
  ).bind(productRowId).first<ProductPriceRow>()
  if (!product) return c.json({ success: false, error: 'Product not found' }, 404)

  const column = PRICE_COLUMNS[field]
  const current = field === 'source_cost' ? product.manufactured_price : product.market_average_price
  const baseline = workbookBaseline(product, field)

  let targetValue = baseline
  let restoredMrpSource: MrpSourceType = product.mrp_source_type
  if (field === 'mrp') {
    if (product.sourcing_origin === 'local') {
      restoredMrpSource = 'workbook'
    } else {
      const resolved = await resolveImportedMrp(c.env.DB, productRowId, baseline)
      targetValue = resolved.value
      restoredMrpSource = resolved.source
    }
  }

  if (current === targetValue && (field !== 'mrp' || product.mrp_source_type === restoredMrpSource)) {
    return c.json({ success: true, productRowId, field, value: current, changed: false })
  }

  const editedAt = new Date().toISOString()

  await c.env.DB.batch([
    field === 'mrp'
      ? c.env.DB.prepare(
          `UPDATE products SET ${column} = ?1, mrp_source_type = ?2 WHERE row_id = ?3`,
        ).bind(targetValue, restoredMrpSource, productRowId)
      : c.env.DB.prepare(
          `UPDATE products SET ${column} = ?1 WHERE row_id = ?2`,
        ).bind(targetValue, productRowId),
    c.env.DB.prepare(
      `INSERT INTO price_edits
         (product_row_id, field, old_value, new_value, workbook_value, edited_at, folded, reverted)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, 0, 1)`,
    ).bind(productRowId, field, current, targetValue, baseline, editedAt),
  ])

  return c.json({
    success: true,
    productRowId,
    field,
    value: targetValue,
    changed: true,
    previousValue: current,
    workbookValue: baseline,
    editedAt,
    reverted: true,
    mrpSourceType: field === 'mrp' ? restoredMrpSource : product.mrp_source_type,
  })
})

export default prices
