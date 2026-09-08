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
  row_id: number
  workbook_source_cost: number | null
  workbook_mrp: number | null
}

const text = (value: XlsxCell['value']): XlsxCell => ({ value, style: 'text' })
const header = (value: string): XlsxCell => ({ value, style: 'header' })
const money = (value: number | null | undefined): XlsxCell => ({ value, style: 'money' })
const percent = (value: number | null | undefined): XlsxCell => ({ value, style: 'percent' })
const integer = (value: number | null | undefined): XlsxCell => ({ value, style: 'integer' })

const BASE_COLUMNS = [
  ['Excel Row', 11], ['Excel Sheet', 24], ['Row ID', 9],
  ['Product', 46], ['Brand', 22], ['Size', 14], ['Category', 18],
  ['Source Cost', 16], ['MRP', 16], ['MRP Source', 16],
  ['Implied Discount %', 18], ['MRP Markup %', 16],
  ['Selling Price', 17], ['Target Markup %', 18], ['Above Market?', 15],
  ['Source Cost Edited?', 20], ['Source Cost Edited At', 23],
  ['MRP Edited?', 14], ['MRP Edited At', 23],
  ['Workbook Source Cost', 22], ['Workbook MRP', 18],
  ['Source Sheet', 24], ['Source Row', 12],
  ['Packaging', 14], ['Transport', 14], ['Delivery', 14],
  ['CAC Type', 22], ['CAC', 14], ['Target Margin %', 18],
  ['Discount Type', 17], ['Discount', 14], ['Tuned?', 11],
] as const

const BASE_HEADERS = BASE_COLUMNS.map(([label]) => label)

/** Immutable workbook baselines stored beside the current static prices. */
async function workbookBaselines(db: D1Database): Promise<Map<string, number>> {
  const result = await db.prepare(
    `SELECT row_id, workbook_source_cost, workbook_mrp FROM products`,
  ).all<BaselineRow>()

  const baselines = new Map<string, number>()
  for (const row of result.results ?? []) {
    if (row.workbook_source_cost !== null) {
      baselines.set(`${row.row_id}:source_cost`, Number(row.workbook_source_cost))
    }
    if (row.workbook_mrp !== null) {
      baselines.set(`${row.row_id}:mrp`, Number(row.workbook_mrp))
    }
  }
  return baselines
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
    // The workbook coordinate leads every row, matching the dashboard's pinned
    // leftmost column, so a figure here can be typed into Excel's Name Box.
    integer(product.source_row),
    text(product.source_sheet),
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
    text(product.source_cost_edited_at ? 'Yes' : 'No'),
    text(product.source_cost_edited_at),
    text(product.mrp_edited_at ? 'Yes' : 'No'),
    text(product.mrp_edited_at),
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
      ...BASE_COLUMNS.map(([, width]) => width),
      ...channels.map(() => 17),
    ],
  }
}

exportWorkbook.get('/', async (c) => {
  const requested = c.req.query('origin')
  if (requested !== 'local' && requested !== 'imported') {
    return c.json({ success: false, error: "origin must be 'local' or 'imported'" }, 400)
  }
  const origin: SourcingOrigin = requested
  const [catalog, pricing, baselines] = await Promise.all([
    fetchCatalog(c.env.DB, origin),
    readPricingState(c.env.DB),
    workbookBaselines(c.env.DB),
  ])
  const bytes = buildXlsx([
    sheetFor(origin, catalog.products, catalog.source_columns, baselines, pricing),
  ])

  const date = new Date().toISOString().slice(0, 10)
  // Copy into a concrete ArrayBuffer: Hono's body type rejects a Uint8Array
  // whose backing buffer could theoretically be SharedArrayBuffer.
  const body = new ArrayBuffer(bytes.length)
  new Uint8Array(body).set(bytes)
  return c.body(body, 200, {
    'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'Content-Disposition': `attachment; filename="product-price-matrix-${origin}-${date}.xlsx"`,
    'Cache-Control': 'private, no-store',
  })
})

export default exportWorkbook
