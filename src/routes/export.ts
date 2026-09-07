import { Hono } from 'hono'
import { requireAdmin } from '../server/auth'
import { fetchCatalog } from '../server/catalog'
import {
  calculateSellingPrice,
  readPricingState,
  resolvePricingParams,
} from '../server/pricing'
import { buildXlsx, type XlsxCell, type XlsxSheet } from '../server/xlsx'
import type { AppEnv, Product, SourcingOrigin } from '../types'

const exportWorkbook = new Hono<AppEnv>()

// Fetching a private export is read-only at HTTP level, but it carries the full
// commercial catalog and is explicitly admin-only. requireAdmin also enforces
// the same-origin X-Price-Matrix-Admin header used by every mutation.
exportWorkbook.use('*', requireAdmin)

interface BaselineRow {
  product_row_id: number
  field: 'source_cost' | 'mrp'
  workbook_value: number | null
  old_value: number
}

const text = (value: XlsxCell['value']): XlsxCell => ({ value, style: 'text' })
const header = (value: string): XlsxCell => ({ value, style: 'header' })
const money = (value: number | null | undefined): XlsxCell => ({ value, style: 'money' })
const percent = (value: number | null | undefined): XlsxCell => ({ value, style: 'percent' })
const integer = (value: number | null | undefined): XlsxCell => ({ value, style: 'integer' })

const BASE_HEADERS = [
  'Row ID', 'Product', 'Brand', 'Size', 'Category',
  'Source Cost', 'MRP', 'MRP Source',
  'Implied Discount %', 'MRP Markup %',
  'Selling Price', 'Target Markup %', 'Above Market?',
  'Edited?', 'Edited At', 'Workbook Source Cost', 'Workbook MRP',
  'Source Sheet', 'Source Row',
  'Packaging', 'Transport', 'Delivery', 'CAC Type', 'CAC',
  'Target Margin %', 'Discount Type', 'Discount', 'Tuned?',
] as const

/** First-ever baseline per (SKU, field), which remains the workbook figure. */
async function workbookBaselines(db: D1Database): Promise<Map<string, number>> {
  const result = await db.prepare(
    `SELECT edit.product_row_id, edit.field, edit.workbook_value, edit.old_value
       FROM price_edits edit
      WHERE edit.id = (
        SELECT MIN(first_edit.id) FROM price_edits first_edit
         WHERE first_edit.product_row_id = edit.product_row_id
           AND first_edit.field = edit.field
      )`,
  ).all<BaselineRow>()

  return new Map(
    (result.results ?? []).map((row) => [
      `${row.product_row_id}:${row.field}`,
      Number(row.workbook_value ?? row.old_value),
    ]),
  )
}

function channelOrder(local: string[], imported: string[]): string[] {
  const ordered: string[] = []
  for (const channel of [...local, ...imported]) {
    if (!ordered.includes(channel)) ordered.push(channel)
  }
  return ordered
}

function ratio(numerator: number, denominator: number): number | null {
  return denominator > 0 ? numerator / denominator : null
}

function rowFor(
  product: Product,
  channels: string[],
  baselines: Map<string, number>,
  globalParams: Awaited<ReturnType<typeof readPricingState>>['globalParams'],
  overrides: Awaited<ReturnType<typeof readPricingState>>['overrides'],
): XlsxCell[] {
  const cost = Number(product.manufactured_price)
  const mrp = Number(product.market_average_price)
  const override = overrides[String(product.row)]
  const params = resolvePricingParams(globalParams, override)
  const selling = calculateSellingPrice(cost, params)
  const sellingValue = selling ?? null

  const workbookCost = baselines.get(`${product.row}:source_cost`) ?? cost
  const workbookMrp = baselines.get(`${product.row}:mrp`) ?? mrp

  const cells: XlsxCell[] = [
    integer(product.row),
    text(product.product_name),
    text(product.brand_name),
    text(product.size),
    text(product.category),
    money(cost),
    money(mrp),
    text(product.mrp_source_type),
    percent(ratio(mrp - cost, mrp)),
    percent(ratio(mrp - cost, cost)),
    money(sellingValue),
    percent(sellingValue === null ? null : ratio(sellingValue - cost, cost)),
    text(sellingValue !== null && mrp > 0 && sellingValue > mrp ? 'Yes' : 'No'),
    text(product.price_edited_at ? 'Yes' : 'No'),
    text(product.price_edited_at),
    money(workbookCost),
    money(workbookMrp),
    text(product.source_sheet),
    integer(product.source_row),
    money(params.packaging),
    money(params.transport),
    money(params.delivery),
    text(params.cacType === 'pct' ? 'Percent of source cost' : 'BDT amount'),
    params.cacType === 'pct' ? percent(params.cac / 100) : money(params.cac),
    percent(params.targetMarginPct / 100),
    text(params.discountType === 'pct' ? 'Percent' : 'BDT amount'),
    params.discountType === 'pct' ? percent(params.discountVal / 100) : money(params.discountVal),
    text(override ? 'Yes' : 'No'),
  ]

  for (const channel of channels) {
    const listing = product.sources[channel]
    cells.push(money(listing?.price))
  }
  return cells
}

function sheetFor(
  origin: SourcingOrigin,
  products: Product[],
  channels: string[],
  baselines: Map<string, number>,
  pricing: Awaited<ReturnType<typeof readPricingState>>,
): XlsxSheet {
  const rows: XlsxCell[][] = [
    [...BASE_HEADERS, ...channels].map((label) => header(label)),
    ...products.map((product) => rowFor(
      product, channels, baselines, pricing.globalParams, pricing.overrides,
    )),
  ]

  return {
    name: origin === 'local' ? 'Local' : 'Imported',
    rows,
    freezeHeader: true,
    autoFilter: true,
    widths: [
      9, 46, 22, 14, 18,
      16, 16, 16, 18, 16,
      17, 18, 15, 11, 23, 20, 18,
      24, 12, 14, 14, 14, 22, 14, 18, 17, 14, 11,
      ...channels.map(() => 17),
    ],
  }
}

exportWorkbook.get('/', async (c) => {
  const [local, imported, pricing, baselines] = await Promise.all([
    fetchCatalog(c.env.DB, 'local'),
    fetchCatalog(c.env.DB, 'imported'),
    readPricingState(c.env.DB),
    workbookBaselines(c.env.DB),
  ])
  const channels = channelOrder(local.source_columns, imported.source_columns)
  const bytes = buildXlsx([
    sheetFor('local', local.products, channels, baselines, pricing),
    sheetFor('imported', imported.products, channels, baselines, pricing),
  ])

  const date = new Date().toISOString().slice(0, 10)
  // Copy into a concrete ArrayBuffer: Hono's body type rejects a Uint8Array
  // whose backing buffer could theoretically be SharedArrayBuffer.
  const body = new ArrayBuffer(bytes.length)
  new Uint8Array(body).set(bytes)
  return c.body(body, 200, {
    'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'Content-Disposition': `attachment; filename="product-price-matrix-${date}.xlsx"`,
    'Cache-Control': 'private, no-store',
  })
})

export default exportWorkbook
