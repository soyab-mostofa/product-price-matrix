/**
 * Audit the specimen record (detail modal) and the imported book's header.
 * Recomputes the cost stack, spread rail, identity strip, and channel audit.
 */
import { chromium } from 'playwright'

const BASE = process.env.AUDIT_BASE ?? 'http://localhost:5173'
const problems = []
const bad = (a, m) => problems.push(`[${a}] ${m}`)

function sellingPrice(cost, p) {
  const oh = p.packaging + p.transport + p.delivery + p.cac
  if (p.targetMarginPct >= 100) return null
  const list = (cost + oh) / (1 - p.targetMarginPct / 100)
  const out = p.discountType === 'pct' ? list * (1 - p.discountVal / 100) : list - p.discountVal
  return Math.round(Math.max(0, out))
}
const markup = (p, c) => ((p - c) / c) * 100
const marketDiscount = (s, b) => ((b - s) / b) * 100
const money = new Intl.NumberFormat('en-BD', { style: 'currency', currency: 'BDT', minimumFractionDigits: 0, maximumFractionDigits: 0 })
const parseBdt = (t) => { const m = String(t).match(/BDT\s*([\d,]+)/); return m ? Number(m[1].replaceAll(',', '')) : null }

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } })
const page = await ctx.newPage()
const engine = await (await page.request.get(`${BASE}/api/engine`)).json()
const G = engine.globalParams

// ── Imported book header ──────────────────────────────────────────────────
const imp = await (await page.request.get(`${BASE}/api/products?origin=imported`)).json()
const loc = await (await page.request.get(`${BASE}/api/products?origin=local`)).json()
await page.goto(`${BASE}/imported`, { waitUntil: 'networkidle' })
await page.waitForSelector('#body tr[data-row-id]')
await page.waitForFunction(() => document.getElementById('matrixViewport')?.getAttribute('aria-busy') === 'false')

const impHead = await page.evaluate(() => ({
  productTotal: document.getElementById('productTotal')?.textContent.trim(),
  listingTotal: document.getElementById('listingTotal')?.textContent.trim(),
  localCount: document.querySelector('.origin-option[data-origin="local"] .origin-count')?.textContent.trim(),
  importedCount: document.querySelector('.origin-option[data-origin="imported"] .origin-count')?.textContent.trim(),
  activeTab: document.querySelector('.origin-option.is-active')?.dataset.origin,
  categoryHidden: document.getElementById('categoryField')?.hidden,
  categories: [...document.querySelectorAll('#categoryFilter option')].map((o) => o.value).filter(Boolean),
  rows: document.querySelectorAll('#body tr[data-row-id]').length,
  banner: document.getElementById('aboveMarketBanner')?.textContent.trim(),
  bannerHidden: document.getElementById('aboveMarketBanner')?.hidden,
  specCount: document.getElementById('aboveMarketCount')?.textContent.trim(),
}))
const num = (s) => Number(String(s).replaceAll(',', ''))
if (num(impHead.productTotal) !== imp.product_count) bad('imported', `SKU total ${impHead.productTotal} vs ${imp.product_count}`)
if (num(impHead.listingTotal) !== imp.listing_count) bad('imported', `listing total ${impHead.listingTotal} vs ${imp.listing_count}`)
if (num(impHead.localCount) !== loc.product_count) bad('imported', `Local tab ${impHead.localCount} vs ${loc.product_count}`)
if (num(impHead.importedCount) !== imp.product_count) bad('imported', `Imported tab ${impHead.importedCount} vs ${imp.product_count}`)
if (impHead.activeTab !== 'imported') bad('imported', `active tab is "${impHead.activeTab}"`)
if (impHead.rows !== imp.product_count) bad('imported', `rendered ${impHead.rows} rows vs ${imp.product_count}`)
if (impHead.categoryHidden) bad('imported', 'category filter hidden though imported has categories')
if (JSON.stringify(impHead.categories) !== JSON.stringify(imp.categories)) bad('imported', `categories [${impHead.categories}] vs API [${imp.categories}]`)

let impAbove = 0
for (const p of imp.products) {
  const sp = sellingPrice(p.manufactured_price, G)
  if (p.market_average_price > 0 && sp !== null && sp > p.market_average_price) impAbove++
}
if (num(impHead.specCount) !== impAbove) bad('imported', `above-market flag ${impHead.specCount} vs recompute ${impAbove}`)
console.log('imported header:', JSON.stringify(impHead))
console.log('imported above-market recompute:', impAbove)

// ── Specimen record, across a representative sample ───────────────────────
await page.goto(`${BASE}/`, { waitUntil: 'networkidle' })
await page.waitForSelector('#body tr[data-row-id]')
await page.waitForFunction(() => document.getElementById('matrixViewport')?.getAttribute('aria-busy') === 'false')

// Pick SKUs covering: many channels, zero channels, above-market, cheapest, dearest.
const byChannels = [...loc.products].sort((a, b) => Object.keys(b.sources).length - Object.keys(a.sources).length)
const aboveOne = loc.products.find((p) => { const s = sellingPrice(p.manufactured_price, G); return p.market_average_price > 0 && s > p.market_average_price })
const noChan = loc.products.find((p) => Object.keys(p.sources).length === 0)
const sample = [...new Set([
  byChannels[0], byChannels[1],
  aboveOne,
  noChan,
  [...loc.products].sort((a, b) => a.manufactured_price - b.manufactured_price)[0],
  [...loc.products].sort((a, b) => b.manufactured_price - a.manufactured_price)[0],
].filter(Boolean))]

console.log('\nrecord sample rows:', sample.map((p) => p.row))

for (const p of sample) {
  await page.locator(`#body tr[data-row-id="${p.row}"]`).click()
  await page.waitForSelector('#dialog[open]')
  await page.waitForTimeout(200)

  const d = await page.evaluate(() => {
    const txt = (s) => document.querySelector(s)?.textContent.trim() ?? null
    const stats = [...document.querySelectorAll('#tabOverviewContent .detail-stat-box')].map((b) => {
      const s = b.querySelector('strong')
      // The MRP box holds a price node plus a chip node; take only the text.
      const value = s
        ? ([...s.childNodes].filter((nd) => nd.nodeType === Node.TEXT_NODE)
            .map((nd) => nd.textContent.trim()).filter(Boolean).join('') || s.textContent.trim())
        : null
      return {
        label: b.querySelector('span')?.textContent.trim(),
        value,
        chip: s?.querySelector('.markup-chip')?.textContent.trim() ?? null,
        readings: [...b.querySelectorAll('.stat-reading')].map((r) => r.textContent.trim()),
        cls: b.className,
      }
    })
    const ident = [...document.querySelectorAll('.record-spec-item')].map((i) => ({
      term: i.querySelector('dt')?.textContent.trim(), val: i.querySelector('dd')?.textContent.trim(),
    }))
    const key = [...document.querySelectorAll('.cost-stack-key-item')].map((k) => k.textContent.trim().replace(/\s+/g, ' '))
    const segs = [...document.querySelectorAll('.cost-stack-seg')].map((s) => ({ cls: s.className, w: s.style.width }))
    const rows = [...document.querySelectorAll('.detail-source-row')].map((r) => {
      const fig = r.querySelector('.source-row-figure')
      // Price and chip are separate nodes; textContent would run them together.
      const chip = fig?.querySelector('.markup-chip')
      const priceNode = [...(fig?.childNodes ?? [])]
        .filter((nd) => nd.nodeType === Node.TEXT_NODE)
        .map((nd) => nd.textContent.trim()).join('')
      return {
        name: r.querySelector('.source-row-name')?.textContent.trim(),
        price: priceNode,
        chip: chip?.textContent.trim() ?? null,
        link: r.querySelector('a')?.getAttribute('href') ?? null,
        unverified: !!r.querySelector('.listing-unverified-text'),
      }
    })
    const statValue = (b) => {
      const s = b.querySelector('strong')
      if (!s) return null
      return [...s.childNodes].filter((nd) => nd.nodeType === Node.TEXT_NODE)
        .map((nd) => nd.textContent.trim()).join('') || s.textContent.trim()
    }
    return {
      brandKicker: txt('#dialogBrand'), name: txt('#dialogName'), stats, ident, key, segs, rows,
      endpoints: [...document.querySelectorAll('.spread-endpoints span')].map((s) => s.textContent.trim()),
      ticks: [...document.querySelectorAll('.spread-tick')].map((t) => ({ cls: t.className, left: t.style.left, title: t.title })),
      railPresent: !!document.querySelector('.spread-rail'),
      emptyMsg: txt('.detail-source-empty'),
    }
  })

  const tag = `record row ${p.row}`
  if (d.name !== p.product_name) bad('record', `${tag}: title "${d.name}" vs "${p.product_name}"`)
  if (d.brandKicker !== p.brand_name) bad('record', `${tag}: kicker "${d.brandKicker}" vs "${p.brand_name}"`)

  const sp = sellingPrice(p.manufactured_price, G)
  const overhead = G.packaging + G.transport + G.delivery + G.cac

  // stat boxes
  if (parseBdt(d.stats[0]?.value) !== Math.round(p.manufactured_price)) bad('record', `${tag}: source cost box ${d.stats[0]?.value} vs ${money.format(p.manufactured_price)}`)
  if (parseBdt(d.stats[1]?.value) !== Math.round(p.market_average_price)) bad('record', `${tag}: MRP box ${d.stats[1]?.value} vs ${money.format(p.market_average_price)}`)
  if (parseBdt(d.stats[2]?.value) !== overhead) bad('record', `${tag}: overhead box ${d.stats[2]?.value} vs ${overhead}`)
  if (parseBdt(d.stats[3]?.value) !== sp) bad('record', `${tag}: selling box ${d.stats[3]?.value} vs ${money.format(sp)}`)

  // vs cost / vs MRP readings
  const above = p.market_average_price > 0 && sp > p.market_average_price
  const wantCost = Math.abs(markup(sp, p.manufactured_price)).toFixed(0)
  const wantMrp = Math.abs(marketDiscount(sp, p.market_average_price)).toFixed(0)
  const rc = d.stats[3]?.readings.find((r) => /vs cost/i.test(r))
  const rm = d.stats[3]?.readings.find((r) => /vs MRP/i.test(r))
  if (!rc) bad('record', `${tag}: missing "vs cost" reading`)
  else if (rc.match(/(\d+)%/)?.[1] !== wantCost) bad('record', `${tag}: vs cost "${rc}" want ${wantCost}%`)
  if (p.market_average_price > 0) {
    if (!rm) bad('record', `${tag}: missing "vs MRP" reading`)
    else if (rm.match(/(\d+)%/)?.[1] !== wantMrp) bad('record', `${tag}: vs MRP "${rm}" want ${wantMrp}%`)
  }
  // out-of-spec styling must agree with the arithmetic
  const styledOut = /is-out-of-spec/.test(d.stats[3]?.cls ?? '')
  if (styledOut !== above) bad('record', `${tag}: selling box styled out-of-spec=${styledOut} but above=${above}`)

  // identity strip
  const chanCount = Object.keys(p.sources).length
  const wantChan = `${chanCount} of ${loc.source_columns.length}`
  const gotChan = d.ident.find((i) => i.term === 'Channels listed')?.val
  if (gotChan !== wantChan) bad('record', `${tag}: channels listed "${gotChan}" want "${wantChan}"`)
  const gotBrand = d.ident.find((i) => i.term === 'Brand')?.val
  if (gotBrand !== p.brand_name) bad('record', `${tag}: identity brand "${gotBrand}"`)
  const gotSize = d.ident.find((i) => i.term === 'Pack size')?.val
  if ((p.size || null) !== (gotSize ?? null)) bad('record', `${tag}: identity size "${gotSize}" vs "${p.size}"`)
  const gotSrc = d.ident.find((i) => i.term === 'Sourcing')?.val
  if (!gotSrc?.startsWith(p.sourcing_origin === 'local' ? 'Local' : 'Imported')) bad('record', `${tag}: sourcing "${gotSrc}" vs origin ${p.sourcing_origin}`)

  // cost stack: segments must sum to the selling price and match the key
  const kSource = Number(d.key.find((k) => /Source cost/.test(k))?.match(/BDT ([\d,]+)/)?.[1].replaceAll(',', ''))
  const kOver = Number(d.key.find((k) => /Overhead/.test(k))?.match(/BDT ([\d,]+)/)?.[1].replaceAll(',', ''))
  const kSell = Number(d.key.find((k) => /^Selling/.test(k))?.match(/BDT ([\d,]+)/)?.[1].replaceAll(',', ''))
  if (kSource !== Math.round(p.manufactured_price)) bad('record', `${tag}: stack source ${kSource} vs ${Math.round(p.manufactured_price)}`)
  if (kOver !== overhead) bad('record', `${tag}: stack overhead ${kOver} vs ${overhead}`)
  if (kSell !== sp) bad('record', `${tag}: stack selling ${kSell} vs ${sp}`)
  // With margin 0 and discount 0, cost + overhead must equal the selling price.
  if (G.targetMarginPct === 0 && G.discountVal === 0) {
    const sum = Math.round(p.manufactured_price) + overhead
    if (Math.abs(sum - sp) > 1) bad('record', `${tag}: stack ${kSource}+${kOver}=${sum} but selling ${sp}`)
  }
  const totalW = d.segs.reduce((a, s) => a + parseFloat(s.w), 0)
  if (Math.abs(totalW - 100) > 0.5) bad('record', `${tag}: stack widths total ${totalW.toFixed(2)}% (want 100)`)

  // spread rail endpoints
  if (d.railPresent) {
    const prices = Object.values(p.sources).map((s) => s.price).filter((x) => x > 0)
    const pts = [...prices, p.market_average_price, sp].filter((x) => x > 0)
    const lo = Math.min(...pts), hi = Math.max(...pts)
    if (parseBdt(d.endpoints[0]) !== Math.round(lo)) bad('record', `${tag}: rail low ${d.endpoints[0]} vs ${money.format(lo)}`)
    if (parseBdt(d.endpoints[1]) !== Math.round(hi)) bad('record', `${tag}: rail high ${d.endpoints[1]} vs ${money.format(hi)}`)
    const ours = d.ticks.find((t) => /is-ours/.test(t.cls))
    if (ours) {
      const wantLeft = (((sp - lo) / ((hi - lo) || 1)) * 100).toFixed(2)
      if (parseFloat(ours.left).toFixed(2) !== wantLeft) bad('record', `${tag}: ours tick at ${ours.left} want ${wantLeft}%`)
      const outStyled = /is-out-of-spec/.test(ours.cls)
      if (outStyled !== above) bad('record', `${tag}: ours tick out-of-spec=${outStyled} but above=${above}`)
    }
  }

  // channel audit rows
  if (chanCount === 0) {
    if (!d.emptyMsg) bad('record', `${tag}: no listings but no empty message`)
    if (d.rows.length) bad('record', `${tag}: no listings but ${d.rows.length} rows rendered`)
  } else {
    if (d.rows.length !== chanCount) bad('record', `${tag}: ${d.rows.length} channel rows vs ${chanCount} listings`)
    for (const row of d.rows) {
      const l = p.sources[row.name]
      if (!l) { bad('record', `${tag}: channel row "${row.name}" not in API`); continue }
      if (parseBdt(row.price) !== Math.round(l.price)) bad('record', `${tag}: ${row.name} ${row.price} vs ${money.format(l.price)}`)
      const want = Math.abs(markup(l.price, p.manufactured_price)).toFixed(0)
      const got = row.chip?.match(/(\d+)%/)?.[1]
      if (got !== want) bad('record', `${tag}: ${row.name} chip ${got}% want ${want}%`)
      if (l.verified && l.url) { if (row.link !== l.url) bad('record', `${tag}: ${row.name} link "${row.link}" vs "${l.url}"`) }
      else if (!row.unverified) bad('record', `${tag}: ${row.name} unverified but no notice`)
    }
  }
  console.log(`  ok row ${p.row}: ${chanCount} channels, selling ${money.format(sp)}, above=${above}`)
  await page.locator('#close').click()
  await page.waitForTimeout(120)
}

await browser.close()
console.log('\n=== PROBLEMS ===')
if (!problems.length) console.log('  none')
else problems.forEach((s) => console.log('  !!  ' + s))
