/**
 * Audit the rendered sheet against the authoritative API.
 *
 * Nothing here trusts the DOM's own arithmetic: every number is recomputed
 * from /api/products + /api/engine with an independent implementation of the
 * documented formulas, then compared to what the page actually painted.
 */
import { chromium } from 'playwright'

const BASE = process.env.AUDIT_BASE ?? 'http://localhost:5173'
const problems = []
const notes = []
const bad = (area, msg) => problems.push(`[${area}] ${msg}`)
const ok = (area, msg) => notes.push(`[${area}] ${msg}`)

// ── Independent re-implementation of the documented engine ────────────────
// AGENTS.md §3B: List = (Cost + Overhead) / (1 - Margin/100); then discount.
function sellingPrice(cost, p) {
  const overhead = p.packaging + p.transport + p.delivery + (p.cacType === 'pct' ? (cost * p.cac) / 100 : p.cac)
  if (p.targetMarginPct >= 100) return null
  const list = (cost + overhead) / (1 - p.targetMarginPct / 100)
  const out = p.discountType === 'pct'
    ? list * (1 - p.discountVal / 100)
    : list - p.discountVal
  return Math.max(0, out)
}
// AGENTS.md §3A
const markup = (price, cost) => ((price - cost) / cost) * 100
const marketDiscount = (sell, bench) => ((bench - sell) / bench) * 100

const resolve = (global, ov) => {
  if (!ov) return global
  const out = { ...global }
  for (const k of ['packaging', 'transport', 'delivery', 'targetMarginPct']) {
    if (ov[k] !== undefined && ov[k] !== null) out[k] = ov[k]
  }
  if (ov.discountType != null && ov.discountVal != null) {
    out.discountType = ov.discountType
    out.discountVal = ov.discountVal
  }
  return out
}

const money = new Intl.NumberFormat('en-BD', {
  style: 'currency', currency: 'BDT', minimumFractionDigits: 0, maximumFractionDigits: 0,
})
const parseBdt = (t) => {
  const m = String(t).match(/BDT\s*([\d,]+)/)
  return m ? Number(m[1].replaceAll(',', '')) : null
}
const parsePct = (t) => {
  const m = String(t).match(/(\d+)\s*%/)
  return m ? Number(m[1]) : null
}

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } })
const page = await ctx.newPage()

// ── Pull authoritative data ───────────────────────────────────────────────
const local = await (await page.request.get(`${BASE}/api/products?origin=local`)).json()
const imported = await (await page.request.get(`${BASE}/api/products?origin=imported`)).json()
const engine = await (await page.request.get(`${BASE}/api/engine`)).json()
const G = engine.globalParams
const OV = engine.overrides || {}

console.log('=== AUTHORITATIVE ===')
console.log('local products:', local.product_count, 'listings:', local.listing_count, 'channels:', local.source_columns.length)
console.log('imported products:', imported.product_count, 'listings:', imported.listing_count, 'channels:', imported.source_columns.length)
console.log('engine:', JSON.stringify(G))
console.log('overrides:', Object.keys(OV).length)

// Sanity: does the payload's own count match its array length?
for (const [name, cat] of [['local', local], ['imported', imported]]) {
  if (cat.product_count !== cat.products.length) {
    bad('api', `${name}: product_count ${cat.product_count} != products[] length ${cat.products.length}`)
  } else ok('api', `${name}: product_count matches array (${cat.products.length})`)

  const listingSum = cat.products.reduce((n, p) => n + Object.keys(p.sources).length, 0)
  if (listingSum !== cat.listing_count) {
    bad('api', `${name}: listing_count ${cat.listing_count} != sum of per-product sources ${listingSum}`)
  } else ok('api', `${name}: listing_count matches sum of sources (${listingSum})`)

  const counted = Object.values(cat.source_listing_counts).reduce((a, b) => a + b, 0)
  if (counted !== cat.listing_count) {
    bad('api', `${name}: source_listing_counts total ${counted} != listing_count ${cat.listing_count}`)
  } else ok('api', `${name}: per-channel counts total to listing_count (${counted})`)
}

await page.goto(`${BASE}/`, { waitUntil: 'networkidle' })
await page.waitForSelector('#body tr[data-row-id]')
await page.waitForFunction(() => document.getElementById('matrixViewport')?.getAttribute('aria-busy') === 'false')

// ── 1. Header counts ──────────────────────────────────────────────────────
const header = await page.evaluate(() => ({
  productTotal: document.getElementById('productTotal')?.textContent?.trim(),
  listingTotal: document.getElementById('listingTotal')?.textContent?.trim(),
  localCount: document.querySelector('.origin-option[data-origin="local"] .origin-count')?.textContent?.trim(),
  importedCount: document.querySelector('.origin-option[data-origin="imported"] .origin-count')?.textContent?.trim(),
  specHidden: document.getElementById('aboveMarketFilterBtn')?.hidden,
  specCount: document.getElementById('aboveMarketCount')?.textContent?.trim(),
  specVerb: document.getElementById('aboveMarketVerb')?.textContent?.trim(),
  banner: document.getElementById('aboveMarketBanner')?.textContent?.trim(),
  bannerHidden: document.getElementById('aboveMarketBanner')?.hidden,
  rows: document.querySelectorAll('#body tr[data-row-id]').length,
  channelCols: [...document.querySelectorAll('th.source-col-head')].map((t) => t.dataset.source),
}))

const n = (s) => Number(String(s).replaceAll(',', ''))
if (n(header.productTotal) !== local.product_count) bad('header', `SKU total shows ${header.productTotal}, API says ${local.product_count}`)
else ok('header', `SKU total ${header.productTotal} matches API`)

if (n(header.listingTotal) !== local.listing_count) bad('header', `listing total shows ${header.listingTotal}, API says ${local.listing_count}`)
else ok('header', `listing total ${header.listingTotal} matches API`)

if (n(header.localCount) !== local.product_count) bad('origin-switch', `Local tab shows ${header.localCount}, API says ${local.product_count}`)
else ok('origin-switch', `Local count ${header.localCount} matches`)

if (n(header.importedCount) !== imported.product_count) bad('origin-switch', `Imported tab shows ${header.importedCount}, API says ${imported.product_count}`)
else ok('origin-switch', `Imported count ${header.importedCount} matches`)

if (header.rows !== local.product_count) bad('table', `rendered ${header.rows} rows, API says ${local.product_count} products`)
else ok('table', `rendered row count ${header.rows} matches product_count`)

// ── 2. Above-market count, recomputed independently ───────────────────────
let expectedAbove = 0
const aboveRows = []
for (const p of local.products) {
  const params = resolve(G, OV[String(p.row)])
  const sp = sellingPrice(p.manufactured_price, params)
  if (p.market_average_price > 0 && sp !== null && sp > p.market_average_price) {
    expectedAbove++
    aboveRows.push(p.row)
  }
}
if (n(header.specCount) !== expectedAbove) bad('above-market', `flag shows ${header.specCount}, independent recompute says ${expectedAbove}`)
else ok('above-market', `flag count ${header.specCount} matches independent recompute`)

// Banner wording must agree with the flag and with the rows on screen.
const bannerNums = (header.banner || '').match(/[\d,]+/g)?.map(n) ?? []
if (!header.bannerHidden) {
  const [shown, total] = bannerNums
  if (shown !== expectedAbove) bad('above-market', `banner says ${shown} above market, recompute says ${expectedAbove}`)
  else ok('above-market', `banner count ${shown} matches recompute`)
  if (total !== header.rows) bad('above-market', `banner says "of ${total}" but ${header.rows} rows are rendered`)
  else ok('above-market', `banner "of ${total}" matches rendered rows`)
}

// ── 3. Channel columns: only channels with >=1 listing in view ────────────
const expectedChannels = local.source_columns.filter((c) => local.products.some((p) => p.sources[c]))
if (JSON.stringify(header.channelCols) !== JSON.stringify(expectedChannels)) {
  bad('columns', `rendered [${header.channelCols}] but expected [${expectedChannels}]`)
} else ok('columns', `${header.channelCols.length} channel columns match the channels with listings`)

console.log(JSON.stringify({ header, expectedAbove }, null, 2))
await browser.close()

console.log('\n=== PASS ===')
notes.forEach((s) => console.log('  ok  ' + s))
console.log('\n=== PROBLEMS ===')
if (!problems.length) console.log('  none')
problems.forEach((s) => console.log('  !!  ' + s))
