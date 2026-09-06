/**
 * Audit interactive behaviour + all user-facing copy.
 * Filters, sorting, search, the out-of-spec filter, and every label/tooltip.
 */
import { chromium } from 'playwright'

const BASE = process.env.AUDIT_BASE ?? 'http://localhost:5173'
const problems = []
const bad = (a, m) => problems.push(`[${a}] ${m}`)

function sellingPrice(cost, p) {
  const oh = p.packaging + p.transport + p.delivery + (p.cacType === 'pct' ? (cost * p.cac) / 100 : p.cac)
  const list = (cost + oh) / (1 - p.targetMarginPct / 100)
  return Math.round(Math.max(0, p.discountType === 'pct' ? list * (1 - p.discountVal / 100) : list - p.discountVal))
}
const parseBdt = (t) => { const m = String(t).match(/BDT\s*([\d,]+)/); return m ? Number(m[1].replaceAll(',', '')) : null }

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } })
const page = await ctx.newPage()
const engine = await (await page.request.get(`${BASE}/api/engine`)).json()
const G = engine.globalParams
const OV = engine.overrides || {}
// Same merge the app applies: independent fields pin one at a time, CAC and
// discount pin as pairs.
const resolve = (g, ov) => {
  if (!ov) return g
  const out = { ...g }
  for (const k of ['packaging', 'transport', 'delivery', 'targetMarginPct']) {
    if (ov[k] != null) out[k] = ov[k]
  }
  if (ov.cacType != null && ov.cac != null) { out.cacType = ov.cacType; out.cac = ov.cac }
  if (ov.discountType != null && ov.discountVal != null) { out.discountType = ov.discountType; out.discountVal = ov.discountVal }
  return out
}
const cat = await (await page.request.get(`${BASE}/api/products?origin=local`)).json()

await page.goto(`${BASE}/`, { waitUntil: 'networkidle' })
await page.waitForSelector('#body tr[data-row-id]')
await page.waitForFunction(() => document.getElementById('matrixViewport')?.getAttribute('aria-busy') === 'false')

const rowIds = () => page.$$eval('#body tr[data-row-id]', (ts) => ts.map((t) => Number(t.dataset.rowId)))
const colNums = (sel) => page.$$eval(`#body tr[data-row-id] ${sel}`, (ts) => ts.map((t) => {
  const m = t.textContent.match(/BDT\s*([\d,]+)/); return m ? Number(m[1].replaceAll(',', '')) : null
}))

// ── Search ────────────────────────────────────────────────────────────────
await page.fill('#search', 'Amla')
await page.waitForTimeout(400)
let got = await rowIds()
let want = cat.products.filter((p) => /amla/i.test(p.product_name) || /amla/i.test(p.brand_name)).map((p) => p.row)
if (got.length !== want.length) bad('search', `"Amla" -> ${got.length} rows, expected ${want.length}`)
if (got.some((r) => !want.includes(r))) bad('search', `"Amla" returned rows outside the expected set`)

// Search must match brand as well as title.
await page.fill('#search', 'Neofarmers')
await page.waitForTimeout(400)
got = await rowIds()
want = cat.products.filter((p) => /neofarmers/i.test(p.product_name) || /neofarmers/i.test(p.brand_name)).map((p) => p.row)
if (got.length !== want.length) bad('search', `"Neofarmers" -> ${got.length}, expected ${want.length}`)

// A query with no hits must show the empty state, not a blank sheet.
await page.fill('#search', 'zzzznotathing')
await page.waitForTimeout(400)
const emptyState = await page.evaluate(() => {
  const e = document.getElementById('empty')
  return { hidden: e?.hidden, text: e?.textContent.trim(), rows: document.querySelectorAll('#body tr[data-row-id]').length }
})
if (emptyState.rows !== 0) bad('search', `no-hit query still rendered ${emptyState.rows} rows`)
if (emptyState.hidden) bad('search', 'no-hit query did not reveal the empty state')
await page.fill('#search', '')
await page.waitForTimeout(400)

// ── Brand filter ──────────────────────────────────────────────────────────
for (const brand of ['Guerniss', 'BioCare', 'Orgagenic']) {
  await page.selectOption('#brandFilter', brand)
  await page.waitForTimeout(300)
  got = await rowIds()
  want = cat.products.filter((p) => p.brand_name === brand).map((p) => p.row)
  if (got.length !== want.length) bad('brand-filter', `${brand} -> ${got.length} rows, expected ${want.length}`)
  const brands = await page.$$eval('#body .brand-label', (n) => [...new Set(n.map((x) => x.textContent.trim()))])
  if (brands.length !== 1 || brands[0] !== brand) bad('brand-filter', `${brand} view shows brands [${brands}]`)
  // Auto-hiding: only channels with >=1 listing in this view stay visible.
  const cols = await page.$$eval('th.source-col-head', (t) => t.map((x) => x.dataset.source))
  const expCols = cat.source_columns.filter((c) => cat.products.some((p) => p.brand_name === brand && p.sources[c]))
  if (JSON.stringify(cols) !== JSON.stringify(expCols)) bad('column-autohide', `${brand}: cols [${cols}] expected [${expCols}]`)
}
await page.selectOption('#brandFilter', '')
await page.waitForTimeout(300)

// ── Channel filter ────────────────────────────────────────────────────────
for (const chan of ['Rokomari', 'Daraz', 'Shajgoj']) {
  await page.selectOption('#sourceFilter', chan)
  await page.waitForTimeout(300)
  got = await rowIds()
  want = cat.products.filter((p) => p.sources[chan]).map((p) => p.row)
  if (got.length !== want.length) bad('channel-filter', `${chan} -> ${got.length} rows, expected ${want.length}`)
  const cells = await page.$$eval(`#body td[data-source="${chan}"]`, (t) => t.length)
  if (cells !== want.length) bad('channel-filter', `${chan}: ${cells} cells for ${want.length} rows`)
}
await page.selectOption('#sourceFilter', '')
await page.waitForTimeout(300)

// ── Combined filters ──────────────────────────────────────────────────────
await page.selectOption('#brandFilter', 'Guerniss')
await page.selectOption('#sourceFilter', 'Shajgoj')
await page.waitForTimeout(350)
got = await rowIds()
want = cat.products.filter((p) => p.brand_name === 'Guerniss' && p.sources['Shajgoj']).map((p) => p.row)
if (got.length !== want.length) bad('combined', `Guerniss+Shajgoj -> ${got.length}, expected ${want.length}`)
await page.selectOption('#brandFilter', '')
await page.selectOption('#sourceFilter', '')
await page.waitForTimeout(300)

// ── Sorting ───────────────────────────────────────────────────────────────
const asc = (v) => v.every((x, i) => i === 0 || v[i - 1] <= x)
const desc = (v) => v.every((x, i) => i === 0 || v[i - 1] >= x)
for (const [opt, sel, chk, label] of [
  ['mfgAsc', '.col-mfg', asc, 'source cost asc'],
  ['mfgDesc', '.col-mfg', desc, 'source cost desc'],
  ['marketAsc', '.col-market', asc, 'MRP asc'],
  ['marketDesc', '.col-market', desc, 'MRP desc'],
  ['sellingAsc', '.col-selling-price', asc, 'selling asc'],
  ['sellingDesc', '.col-selling-price', desc, 'selling desc'],
]) {
  await page.selectOption('#sort', opt)
  await page.waitForTimeout(350)
  const v = (await colNums(sel)).filter((x) => x !== null)
  if (!chk(v)) bad('sort', `${label} is not ordered (first 6: ${v.slice(0, 6)})`)
}
// Market discount ordering. The price and its chip share one cell, so scraping
// them apart is brittle -- check the row ORDER against the gap computed from the
// catalog instead.
const byRow = new Map(cat.products.map((p) => [p.row, p]))
const discountOf = (row) => {
  const p = byRow.get(row)
  if (!p) return null
  const sp = sellingPrice(p.manufactured_price, resolve(G, OV[String(row)]))
  const mrp = Number(p.market_average_price)
  return mrp > 0 ? ((mrp - sp) / mrp) * 100 : null
}
for (const [opt, chk, label] of [['discountAsc', asc, 'market discount asc'], ['discountDesc', desc, 'market discount desc']]) {
  await page.selectOption('#sort', opt)
  await page.waitForTimeout(350)
  const ds = (await rowIds()).map(discountOf)
  const known = ds.filter((d) => d !== null)
  if (known.length < 2) bad('sort', `${label} had ${known.length} benchmarked rows, too few to prove ordering`)
  if (!chk(known)) bad('sort', `${label} is not ordered (first 6: ${known.slice(0, 6).map((d) => d.toFixed(1)).join(', ')})`)
  // An unknown gap is not a zero gap: MRP-less SKUs belong at the tail.
  const firstMissing = ds.indexOf(null)
  if (firstMissing >= 0 && ds.slice(firstMissing).some((d) => d !== null)) {
    bad('sort', `${label} left an SKU without an MRP above a benchmarked one`)
  }
}

// Alphabetical
await page.selectOption('#sort', 'product')
await page.waitForTimeout(350)
let names = await page.$$eval('#body .item-name', (n) => n.map((x) => x.textContent.trim()))
if (JSON.stringify(names) !== JSON.stringify([...names].sort((a, b) => a.localeCompare(b)))) bad('sort', 'Product A-Z not alphabetical')
await page.selectOption('#sort', 'coverage')
await page.waitForTimeout(350)
const covIds = await rowIds()
const covCounts = covIds.map((r) => Object.keys(cat.products.find((p) => p.row === r).sources).length)
if (!desc(covCounts)) bad('sort', `Most Channels not descending (first 8: ${covCounts.slice(0, 8)})`)

// Header click toggles
await page.selectOption('#sort', 'product')
await page.waitForTimeout(250)
await page.locator('th.col-mfg button').click()
await page.waitForTimeout(300)
if (await page.locator('#sort').inputValue() !== 'mfgAsc') bad('sort', 'header click 1 did not set mfgAsc')
if (await page.locator('th.col-mfg').getAttribute('aria-sort') !== 'ascending') bad('a11y', 'th.col-mfg aria-sort not ascending')
await page.locator('th.col-mfg button').click()
await page.waitForTimeout(300)
if (await page.locator('#sort').inputValue() !== 'mfgDesc') bad('sort', 'header click 2 did not set mfgDesc')
if (await page.locator('th.col-mfg').getAttribute('aria-sort') !== 'descending') bad('a11y', 'th.col-mfg aria-sort not descending')
await page.selectOption('#sort', 'product')
await page.waitForTimeout(300)

// ── Out-of-spec filter ────────────────────────────────────────────────────
const expAbove = cat.products.filter((p) => {
  const sp = sellingPrice(p.manufactured_price, G)
  return p.market_average_price > 0 && sp > p.market_average_price
}).map((p) => p.row)

await page.locator('#aboveMarketFilterBtn').click()
await page.waitForTimeout(400)
const filtered = await rowIds()
if (filtered.length !== expAbove.length) bad('spec-filter', `filtered to ${filtered.length}, expected ${expAbove.length}`)
if (filtered.some((r) => !expAbove.includes(r))) bad('spec-filter', 'filtered set contains an in-spec SKU')
const st = await page.evaluate(() => ({
  pressed: document.getElementById('aboveMarketFilterBtn')?.getAttribute('aria-pressed'),
  verb: document.getElementById('aboveMarketVerb')?.textContent.trim(),
  bannerHidden: document.getElementById('aboveMarketBanner')?.hidden,
  count: document.getElementById('aboveMarketCount')?.textContent.trim(),
}))
if (st.pressed !== 'true') bad('spec-filter', `aria-pressed="${st.pressed}" while active`)
if (st.verb !== 'Showing') bad('spec-filter', `verb reads "${st.verb}" while active (want "Showing")`)
if (!st.bannerHidden) bad('spec-filter', 'banner still shown while already filtered to those SKUs')
if (Number(st.count) !== expAbove.length) bad('spec-filter', `count ${st.count} vs ${expAbove.length}`)
// Every row in the filtered view must actually carry an above-market chip.
const chips = await page.$$eval('#body td.col-selling-price .markup-chip', (c) => c.map((x) => x.className))
const notFlagged = chips.filter((c) => !/above-market/.test(c)).length
if (notFlagged) bad('spec-filter', `${notFlagged} filtered rows lack the above-market chip`)

await page.locator('#aboveMarketFilterBtn').click()
await page.waitForTimeout(400)
if ((await rowIds()).length !== cat.product_count) bad('spec-filter', 'releasing the filter did not restore the full sheet')
if (await page.evaluate(() => document.getElementById('aboveMarketVerb')?.textContent.trim()) !== 'Show') bad('spec-filter', 'verb did not revert to "Show"')

// ── Copy / labels ─────────────────────────────────────────────────────────
const copy = await page.evaluate(() => ({
  heads: [...document.querySelectorAll('thead th')].map((th) => ({
    label: th.querySelector('.head-label')?.textContent.replace(/\s+/g, ' ').trim(),
    basis: th.querySelector('.head-basis')?.textContent.trim(),
    title: th.querySelector('button')?.title,
  })),
  toggle: document.getElementById('sellingChipBtnLabel')?.textContent.trim(),
  engineBtn: document.getElementById('openEngineBtn')?.textContent.trim(),
  exportBtn: document.getElementById('download')?.textContent.trim(),
  metaPill: document.querySelector('.header-meta-pill')?.textContent.replace(/\s+/g, ' ').trim(),
  brandTitle: document.querySelector('.brand-title')?.textContent.trim(),
  emptyText: document.getElementById('empty')?.textContent.trim(),
  origins: [...document.querySelectorAll('.origin-option')].map((o) => o.textContent.replace(/\s+/g, ' ').trim()),
}))
console.log('\n--- copy ---')
console.log(JSON.stringify(copy, null, 2))

// Every head must carry a label, a basis line, and a tooltip.
for (const h of copy.heads) {
  if (!h.label) bad('copy', `a column head has no label`)
  if (!h.basis) bad('copy', `head "${h.label}" has no basis line`)
  if (!h.title) bad('copy', `head "${h.label}" has no tooltip`)
}
// Currency columns must say BDT in the basis line.
for (const name of ['SOURCE COST', 'MRP', 'SELLING PRICE']) {
  const h = copy.heads.find((x) => x.label?.startsWith(name))
  if (h && !/BDT/.test(h.basis)) bad('copy', `"${name}" basis "${h.basis}" does not state the unit`)
}

await browser.close()
console.log('\n=== PROBLEMS ===')
if (!problems.length) console.log('  none')
else problems.forEach((s) => console.log('  !!  ' + s))
