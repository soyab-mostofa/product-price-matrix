import { Hono } from 'hono'
import { zValidator } from '@hono/zod-validator'
import { z } from 'zod'
import { requireAdmin } from '../server/auth'
import { productRowIdSchema } from '../server/pricing'
import type { AppEnv } from '../types'

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
  sourcing_origin: string
  mrp_source_type: string
}

/**
 * The figure the workbook shipped for this SKU/field.
 *
 * D1 holds only the current value, so the baseline is captured from the FIRST
 * edit's `old_value` and carried forward on every later edit. That keeps
 * "revert to workbook" pointing at the workbook rather than at the previous
 * edit, however many times a price has been changed.
 */
async function workbookBaseline(
  db: D1Database,
  productRowId: number,
  field: PriceField,
  currentValue: number,
): Promise<number> {
  const firstEdit = await db.prepare(
    `SELECT workbook_value, old_value FROM price_edits
      WHERE product_row_id = ?1 AND field = ?2
      ORDER BY id ASC LIMIT 1`,
  ).bind(productRowId, field).first<{ workbook_value: number | null; old_value: number }>()

  if (!firstEdit) return currentValue
  return firstEdit.workbook_value ?? firstEdit.old_value
}

prices.patch('/', zValidator('json', editSchema, (result, c) => {
  if (!result.success) {
    const issue = result.error.issues[0]
    return c.json({ success: false, error: issue?.message || 'Validation failed' }, 400)
  }
}), async (c) => {
  const { productRowId, field, value } = c.req.valid('json')

  const product = await c.env.DB.prepare(
    `SELECT manufactured_price, market_average_price, sourcing_origin, mrp_source_type
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

  const baseline = await workbookBaseline(c.env.DB, productRowId, field, current)
  const editedAt = new Date().toISOString()

  // An edited MRP is no longer the workbook benchmark, and mrp_source_type is
  // what the UI reads to say where a number came from. Source cost has no
  // equivalent provenance column.
  const statements = [
    field === 'mrp'
      ? c.env.DB.prepare(
          `UPDATE products SET ${column} = ?1, mrp_source_type = 'manual' WHERE row_id = ?2`,
        ).bind(value, productRowId)
      : c.env.DB.prepare(
          `UPDATE products SET ${column} = ?1 WHERE row_id = ?2`,
        ).bind(value, productRowId),
    c.env.DB.prepare(
      `INSERT INTO price_edits
         (product_row_id, field, old_value, new_value, workbook_value, edited_at, folded)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, 0)`,
    ).bind(productRowId, field, current, value, baseline, editedAt),
  ]

  await c.env.DB.batch(statements)

  return c.json({
    success: true,
    productRowId,
    field,
    value,
    changed: true,
    previousValue: current,
    workbookValue: baseline,
    editedAt,
    mrpSourceType: field === 'mrp' ? 'manual' : product.mrp_source_type,
  })
})

/**
 * Revert one field to the figure the workbook shipped.
 *
 * The revert is itself journalled: it is an edit like any other, so the trail
 * stays complete and the fold script carries the restored value through the
 * rebuild rather than leaving the research file holding the edited number.
 */
/**
 * The provenance an imported SKU's MRP should carry once a manual edit is
 * reverted.
 *
 * The row's CURRENT value is useless here — it reads 'manual', because that is
 * what the edit being undone set it to. The pre-edit provenance has to be
 * recovered the same way the pre-edit price is: from the journal. Falling back
 * to the resolution order in AGENTS.md §2 (official -> third-party avg ->
 * reference) keeps a never-edited row honest.
 */
async function restoredImportedMrpSource(
  db: D1Database,
  productRowId: number,
  current: string,
): Promise<string> {
  const hasOfficial = await db.prepare(
    `SELECT 1 FROM marketplace_listings
      WHERE row_id = ?1 AND channel_name = 'Official Store' AND available = 1`,
  ).bind(productRowId).first()
  if (hasOfficial) return 'official'

  const hasAny = await db.prepare(
    'SELECT 1 FROM marketplace_listings WHERE row_id = ?1 AND available = 1',
  ).bind(productRowId).first()
  if (hasAny) return 'third_party_avg'

  // Nothing to resolve from: keep whatever the row had unless that is the
  // 'manual' marker we are undoing.
  return current === 'manual' ? 'reference' : current
}

prices.delete('/', zValidator('query', revertSchema, (result, c) => {
  if (!result.success) {
    const issue = result.error.issues[0]
    return c.json({ success: false, error: issue?.message || 'Invalid query parameters' }, 400)
  }
}), async (c) => {
  const { productRowId, field } = c.req.valid('query')

  const product = await c.env.DB.prepare(
    `SELECT manufactured_price, market_average_price, sourcing_origin, mrp_source_type
       FROM products WHERE row_id = ?`,
  ).bind(productRowId).first<ProductPriceRow>()
  if (!product) return c.json({ success: false, error: 'Product not found' }, 404)

  const column = PRICE_COLUMNS[field]
  const current = field === 'source_cost' ? product.manufactured_price : product.market_average_price
  const baseline = await workbookBaseline(c.env.DB, productRowId, field, current)

  if (current === baseline) {
    return c.json({ success: true, productRowId, field, value: current, changed: false })
  }

  const editedAt = new Date().toISOString()

  // A reverted local MRP is the workbook benchmark again. An imported SKU never
  // carried 'workbook' — its MRP resolves from listings — so its provenance is
  // re-resolved rather than read off the row, which currently says 'manual'.
  const restoredMrpSource = field === 'mrp'
    ? (product.sourcing_origin === 'local'
        ? 'workbook'
        : await restoredImportedMrpSource(c.env.DB, productRowId, product.mrp_source_type))
    : product.mrp_source_type

  await c.env.DB.batch([
    field === 'mrp'
      ? c.env.DB.prepare(
          `UPDATE products SET ${column} = ?1, mrp_source_type = ?2 WHERE row_id = ?3`,
        ).bind(baseline, restoredMrpSource, productRowId)
      : c.env.DB.prepare(
          `UPDATE products SET ${column} = ?1 WHERE row_id = ?2`,
        ).bind(baseline, productRowId),
    c.env.DB.prepare(
      `INSERT INTO price_edits
         (product_row_id, field, old_value, new_value, workbook_value, edited_at, folded)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, 0)`,
    ).bind(productRowId, field, current, baseline, baseline, editedAt),
  ])

  return c.json({
    success: true,
    productRowId,
    field,
    value: baseline,
    changed: true,
    previousValue: current,
    workbookValue: baseline,
    editedAt,
    reverted: true,
    mrpSourceType: field === 'mrp' ? restoredMrpSource : product.mrp_source_type,
  })
})

export default prices
