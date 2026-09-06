/**
 * Cell-level audit: recompute every rendered number independently and diff.
 * Covers both books, both chip modes, and every channel cell.
 */
import { chromium } from 'playwright'

const BASE = process.env.AUDIT_BASE ?? 'http://localhost:5173'
const problems = []
const bad = (a, m) => problems.push(`[${a}] ${m}`)

// The app rounds to whole BDT and then derives every chip from the ROUNDED
// price, so the chip always describes the number on screen. Mirror that.
function sellingPrice(cost, p) {
  const overhead = p.packaging + p.transport + p.delivery + (p.cacType === 'pct' ? (cost * p.cac) / 100 : p.cac)
  if (p.targetMarginPct >= 100) return null
  const list = (cost + overhead) / (1 - p.targetMarginPct / 100)
  const out = p.discountType === 'pct' ? list * (1 - p.discountVal / 100) : list - p.discountVal
  return Math.round(Math.max(0, out))
}
const markup = (price, cost) => ((price - cost) / cost) * 100
const marketDiscount = (sell, bench) => ((bench - sell) / bench) * 100
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
const money = new Intl.NumberFormat('en-BD', { style: 'currency', currency: 'BDT', minimumFractionDigits: 0, maximumFractionDigits: 0 })

// Chip tier per AGENTS.md §5, plus the above-market override.
function expectedTier(pct, above) {
  if (above) return 'above-market'
  if (pct < -0.01) return 'neg'
  if (Math.abs(pct) <= 0.01) return 'zero'
  if (pct <= 15) return 't1'
  if (pct <= 35) return 't2'
  if (pct <= 60) return 't3'
  return 't4'
}
function expectedDiscTier(d, above) {
  if (above) return 'above-market'
  if (d > 0.01) return 'mkt-disc'
  if (Math.abs(d) <= 0.01) return 'zero'
  return 'mkt-prem'
}

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } })
const page = await ctx.newPage()

const engine = await (await page.request.get(`${BASE}/api/engine`)).json()
const G = engine.globalParams
const OV = engine.overrides || {}

for (const [book, route] of [['local', '/'], ['imported', '/imported']]) {
  const cat = await (await page.request.get(`${BASE}/api/products?origin=${book}`)).json()
  const byRow = new Map(cat.products.map((p) => [p.row, p]))

  await page.goto(`${BASE}${route}`, { waitUntil: 'networkidle' })
  await page.waitForSelector('#body tr[data-row-id]')
  await page.waitForFunction(() => document.getElementById('matrixViewport')?.getAttribute('aria-busy') === 'false')

  const scraped = await page.evaluate(() => [...document.querySelectorAll('#body tr[data-row-id]')].map((tr) => {
    const chip = (td) => {
      const c = td?.querySelector('.markup-chip')
      if (!c) return null
      return { cls: [...c.classList].filter((x) => x !== 'markup-chip').join(' '), text: c.textContent.trim(), title: c.title }
    }
    const src = {}
    for (const td of tr.querySelectorAll('td.source-data-cell')) {
      const name = td.dataset.source
      if (!name) continue
      src[name] = {
        price: td.querySelector('.price-val')?.textContent.trim() ?? null,
        chip: chip(td),
        hasLink: !!td.querySelector('a.btn-open-link'),
        href: td.querySelector('a.btn-open-link')?.getAttribute('href') ?? null,
        unverified: !!td.querySelector('.listing-unverified'),
        dash: !!td.querySelector('.cell-dash'),
      }
    }
    return {
      row: Number(tr.dataset.rowId),
      name: tr.querySelector('.item-name')?.textContent.trim(),
      nameTitle: tr.querySelector('.item-name')?.getAttribute('title'),
      size: tr.querySelector('.item-size')?.textContent.trim() ?? null,
      brand: tr.querySelector('.brand-label')?.textContent.trim(),
      mfg: tr.querySelector('td.col-mfg .num-price')?.textContent.trim(),
      mrp: tr.querySelector('td.col-market .num-price')?.textContent.trim(),
      mrpCls: tr.querySelector('td.col-market .num-price')?.className,
      mrpTitle: tr.querySelector('td.col-market .dual-metric-cell')?.getAttribute('title'),
      mrpChip: chip(tr.querySelector('td.col-market')),
      selling: tr.querySelector('td.col-selling-price .num-price')?.textContent.trim() ?? null,
      sellingChip: chip(tr.querySelector('td.col-selling-price')),
      tuned: !!tr.querySelector('.custom-tune-tag'),
      sources: src,
    }
  }))

  if (scraped.length !== cat.products.length) bad(book, `rendered ${scraped.length} rows vs ${cat.products.length} products`)

  for (const r of scraped) {
    const p = byRow.get(r.row)
    if (!p) { bad(book, `row ${r.row} rendered but absent from API`); continue }
    const tag = `${book} row ${r.row} "${p.product_name.slice(0, 34)}"`

    // Identity
    if (r.name !== p.product_name) bad(book, `${tag}: name renders "${r.name}"`)
    if (r.nameTitle !== p.product_name) bad(book, `${tag}: title attr "${r.nameTitle}" != product_name`)
    if (r.brand !== p.brand_name) bad(book, `${tag}: brand renders "${r.brand}" vs "${p.brand_name}"`)
    // The API represents "no pack size" as an empty string; the app renders no
    // size line at all. Both are the same absence.
    const apiSize = p.size || null
    if ((r.size ?? null) !== apiSize) bad(book, `${tag}: size renders "${r.size}" vs "${p.size}"`)

    // Source cost + MRP
    if (r.mfg !== money.format(p.manufactured_price)) bad(book, `${tag}: source cost "${r.mfg}" vs ${money.format(p.manufactured_price)}`)
    if (r.mrp !== money.format(p.market_average_price)) bad(book, `${tag}: MRP "${r.mrp}" vs ${money.format(p.market_average_price)}`)

    // MRP chip = markup of MRP over source cost
    if (p.market_average_price > 0 && p.manufactured_price > 0) {
      const m = markup(p.market_average_price, p.manufactured_price)
      const want = expectedTier(m, false)
      if (!r.mrpChip) bad(book, `${tag}: MRP chip missing`)
      else {
        if (r.mrpChip.cls !== want) bad(book, `${tag}: MRP chip class "${r.mrpChip.cls}" want "${want}" (markup ${m.toFixed(1)}%)`)
        const shown = Number(r.mrpChip.text.match(/(\d+)/)?.[1])
        if (shown !== Number(Math.abs(m).toFixed(0))) bad(book, `${tag}: MRP chip shows ${shown}% want ${Math.abs(m).toFixed(0)}%`)
      }
    }

    // MRP provenance label must match mrp_source_type
    const wantLabel = { workbook: 'Workbook MRP', official: 'Official Brand MRP', third_party_avg: '3rd-Party Market Average', reference: 'Reference Benchmark MRP' }[p.mrp_source_type]
    if (wantLabel && r.mrpTitle && !r.mrpTitle.includes(wantLabel)) {
      bad(book, `${tag}: mrp_source_type=${p.mrp_source_type} but tooltip is "${String(r.mrpTitle).slice(0, 60)}"`)
    }

    // Selling price + its chip
    const params = resolve(G, OV[String(p.row)])
    const sp = sellingPrice(p.manufactured_price, params)
    if (sp === null) {
      if (r.selling) bad(book, `${tag}: selling rendered "${r.selling}" but formula yields null`)
    } else {
      if (r.selling !== money.format(sp)) bad(book, `${tag}: selling "${r.selling}" vs computed ${money.format(sp)}`)
      const above = p.market_average_price > 0 && sp > p.market_average_price
      const m = markup(sp, p.manufactured_price)
      const want = expectedTier(m, above)
      if (!r.sellingChip) bad(book, `${tag}: selling chip missing`)
      else {
        if (r.sellingChip.cls !== want) bad(book, `${tag}: selling chip "${r.sellingChip.cls}" want "${want}" (markup ${m.toFixed(1)}%, above=${above})`)
        const shown = Number(r.sellingChip.text.match(/(\d+)/)?.[1])
        if (shown !== Number(Math.abs(m).toFixed(0))) bad(book, `${tag}: selling chip ${shown}% want ${Math.abs(m).toFixed(0)}%`)
        if (above && !/[Aa]bove market/.test(r.sellingChip.title || '')) bad(book, `${tag}: above-market chip lacks explanatory title`)
      }
    }

    // Tuned pill only when an override exists
    const hasOv = !!OV[String(p.row)]
    if (r.tuned !== hasOv) bad(book, `${tag}: Tuned pill=${r.tuned} but override exists=${hasOv}`)

    // Channel cells
    for (const [chan, cell] of Object.entries(r.sources)) {
      const listing = p.sources[chan]
      if (!listing) {
        if (!cell.dash) bad(book, `${tag}: ${chan} has no listing but rendered "${cell.price}"`)
        continue
      }
      if (cell.price !== money.format(listing.price)) bad(book, `${tag}: ${chan} price "${cell.price}" vs ${money.format(listing.price)}`)
      const m = markup(listing.price, p.manufactured_price)
      const want = expectedTier(m, false)
      if (!cell.chip) bad(book, `${tag}: ${chan} chip missing`)
      else {
        if (cell.chip.cls !== want) bad(book, `${tag}: ${chan} chip "${cell.chip.cls}" want "${want}" (${m.toFixed(1)}%)`)
        const shown = Number(cell.chip.text.match(/(\d+)/)?.[1])
        if (shown !== Number(Math.abs(m).toFixed(0))) bad(book, `${tag}: ${chan} chip ${shown}% want ${Math.abs(m).toFixed(0)}%`)
      }
      // Verified => deep link; unverified => marker, never a fake link
      if (listing.verified && listing.url) {
        if (!cell.hasLink) bad(book, `${tag}: ${chan} verified w/ url but no link rendered`)
        else if (cell.href !== listing.url) bad(book, `${tag}: ${chan} link href mismatch`)
      } else if (!cell.unverified) {
        bad(book, `${tag}: ${chan} unverified but no unverified marker`)
      }
    }
    // Every API listing must have produced a cell
    for (const chan of Object.keys(p.sources)) {
      if (!(chan in r.sources)) bad(book, `${tag}: ${chan} listing exists but no column rendered`)
    }
  }

  // ── Discount-mode pass: flip the cord, re-verify selling chips ──────────
  await page.locator('#toggleSellingChipModeBtn').click()
  await page.waitForTimeout(500)
  const discScraped = await page.evaluate(() => [...document.querySelectorAll('#body tr[data-row-id]')].map((tr) => {
    const c = tr.querySelector('td.col-selling-price .markup-chip')
    return { row: Number(tr.dataset.rowId), cls: c ? [...c.classList].filter((x) => x !== 'markup-chip').join(' ') : null, text: c?.textContent.trim() ?? null }
  }))
  for (const r of discScraped) {
    const p = byRow.get(r.row)
    if (!p) continue
    const sp = sellingPrice(p.manufactured_price, resolve(G, OV[String(p.row)]))
    if (sp === null || !(p.market_average_price > 0)) continue
    const above = sp > p.market_average_price
    const d = marketDiscount(sp, p.market_average_price)
    const want = expectedDiscTier(d, above)
    if (r.cls !== want) bad(book, `discount-mode row ${p.row}: chip "${r.cls}" want "${want}" (disc ${d.toFixed(1)}%)`)
    const shown = Number(String(r.text).match(/(\d+)/)?.[1])
    if (shown !== Number(Math.abs(d).toFixed(0))) bad(book, `discount-mode row ${p.row}: chip ${shown}% want ${Math.abs(d).toFixed(0)}%`)
  }
  console.log(`audited ${book}: ${scraped.length} rows, ${scraped.reduce((n, r) => n + Object.keys(r.sources).length, 0)} channel cells, + discount-mode pass`)
}

await browser.close()
console.log('\n=== PROBLEMS ===')
if (!problems.length) console.log('  none')
else {
  console.log(`  ${problems.length} found`)
  problems.slice(0, 60).forEach((s) => console.log('  !!  ' + s))
  if (problems.length > 60) console.log(`  ... and ${problems.length - 60} more`)
}
