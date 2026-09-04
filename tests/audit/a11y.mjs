/**
 * Accessibility + remaining-surface audit.
 * Checks computed accessible names (not raw textContent), contrast on the
 * small type, focus visibility, and the tune tab.
 */
import { chromium } from 'playwright'

const BASE = process.env.AUDIT_BASE ?? 'http://localhost:5173'
const problems = []
const warn = []
const bad = (a, m) => problems.push(`[${a}] ${m}`)
const soft = (a, m) => warn.push(`[${a}] ${m}`)

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } })
const page = await ctx.newPage()
await page.goto(`${BASE}/`, { waitUntil: 'networkidle' })
await page.waitForSelector('#body tr[data-row-id]')
await page.waitForFunction(() => document.getElementById('matrixViewport')?.getAttribute('aria-busy') === 'false')

// ── Accessible names via ARIA snapshot / computed name ────────────────────
const named = async (sel) => {
  const h = await page.$(sel)
  if (!h) return null
  return h.evaluate((el) => {
    // Approximate the accessible-name algorithm: aria-label wins, then
    // aria-labelledby, then a linked <label>, then the flattened text.
    const label = el.getAttribute('aria-label')
    if (label) return { role: el.getAttribute('role') || el.tagName.toLowerCase(), name: label }
    const by = el.getAttribute('aria-labelledby')
    if (by) {
      const t = by.split(/\s+/).map((id) => document.getElementById(id)?.textContent ?? '').join(' ').trim()
      if (t) return { role: el.getAttribute('role') || el.tagName.toLowerCase(), name: t }
    }
    if (el.id) {
      const lab = document.querySelector(`label[for="${el.id}"]`)
      if (lab) return { role: el.tagName.toLowerCase(), name: lab.textContent.trim() }
    }
    return {
      role: el.getAttribute('role') || el.tagName.toLowerCase(),
      name: (el.textContent || '').replace(/\s+/g, ' ').trim(),
    }
  })
}
const names = {
  localTab: await named('.origin-option[data-origin="local"]'),
  importedTab: await named('.origin-option[data-origin="imported"]'),
  specFlag: await named('#aboveMarketFilterBtn'),
  engineBtn: await named('#openEngineBtn'),
  exportBtn: await named('#download'),
  toggle: await named('#toggleSellingChipModeBtn'),
  search: await named('#search'),
  brandFilter: await named('#brandFilter'),
}
console.log('--- accessible names ---')
console.log(JSON.stringify(names, null, 2))

for (const [k, v] of Object.entries(names)) {
  if (!v?.name?.trim()) bad('a11y', `${k} has no accessible name`)
}
// Counts must be announced separately from the label, not glued to it.
if (/^Local\d/.test(names.localTab?.name ?? '')) soft('a11y', `Local tab announces as "${names.localTab.name}" — count runs into the label`)
if (/^Imported\d/.test(names.importedTab?.name ?? '')) soft('a11y', `Imported tab announces as "${names.importedTab.name}"`)

// ── Contrast on the smallest type ─────────────────────────────────────────
const contrast = await page.evaluate(() => {
  const lum = (rgb) => {
    const [r, g, b] = rgb.map((v) => { const s = v / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4 })
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
  }
  const parse = (s) => (s.match(/\d+(\.\d+)?/g) || []).slice(0, 3).map(Number)
  const bgOf = (el) => {
    let n = el
    while (n && n !== document.documentElement) {
      const c = getComputedStyle(n).backgroundColor
      const p = parse(c)
      if (p.length === 3 && !/rgba\(0, 0, 0, 0\)/.test(c)) return p
      n = n.parentElement
    }
    return [255, 255, 255]
  }
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m); return (x + 0.05) / (y + 0.05) }
  const out = []
  for (const sel of ['.head-basis', '.item-size', '.brand-label', '.head-label', '.spread-label',
                     '.stat-reading', '.record-spec-item dt', '.engine-field span.hint', '.markup-chip']) {
    const el = document.querySelector(sel)
    if (!el) continue
    const cs = getComputedStyle(el)
    out.push({
      sel,
      size: cs.fontSize,
      weight: cs.fontWeight,
      ratio: Number(ratio(parse(cs.color), bgOf(el)).toFixed(2)),
    })
  }
  return out
})
console.log('\n--- contrast ---')
for (const c of contrast) {
  const large = parseFloat(c.size) >= 18 || (parseFloat(c.size) >= 14 && Number(c.weight) >= 700)
  const floor = large ? 3 : 4.5
  const verdict = c.ratio >= floor ? 'ok' : 'FAIL'
  console.log(`  ${verdict}  ${c.sel} ${c.size}/${c.weight} = ${c.ratio}:1 (needs ${floor})`)
  if (c.ratio < floor) bad('contrast', `${c.sel} at ${c.size} is ${c.ratio}:1, needs ${floor}:1`)
}

// ── Focus visibility ──────────────────────────────────────────────────────
await page.keyboard.press('Tab')
const focus = await page.evaluate(() => {
  const el = document.activeElement
  const cs = getComputedStyle(el)
  return { tag: el.tagName, id: el.id, outline: cs.outlineWidth, style: cs.outlineStyle }
})
if (focus.outline === '0px' || focus.style === 'none') bad('a11y', `first tab stop (${focus.id || focus.tag}) shows no focus ring`)
console.log('\nfirst tab stop:', JSON.stringify(focus))

// ── Tune tab ──────────────────────────────────────────────────────────────
await page.locator('#body tr[data-row-id]').first().click()
await page.waitForSelector('#dialog[open]')
await page.locator('#tabTuneBtn').click()
await page.waitForTimeout(250)
const tune = await page.evaluate(() => {
  const ids = ['prodInputPackaging', 'prodInputTransport', 'prodInputDelivery', 'prodInputCAC', 'prodInputMarginPct']
  return {
    placeholders: ids.map((i) => ({ id: i, ph: document.getElementById(i)?.placeholder, val: document.getElementById(i)?.value })),
    pinned: document.getElementById('prodSummaryPinned')?.textContent.trim(),
    globalPrice: document.getElementById('prodSummaryGlobalPrice')?.textContent.trim(),
    selling: document.getElementById('prodSummarySelling')?.textContent.trim(),
    readOnly: document.getElementById('productReadOnlyBanner')?.textContent.trim(),
    readOnlyHidden: document.getElementById('productReadOnlyBanner')?.hidden,
    saveDisabled: document.getElementById('saveProductCustomEngineBtn')?.disabled,
  }
})
console.log('\n--- tune tab ---')
console.log(JSON.stringify(tune, null, 2))

const engine = await (await page.request.get(`${BASE}/api/engine`)).json()
const G = engine.globalParams
// Placeholders must advertise the live global value ("blank = follows global").
const expect = { prodInputPackaging: G.packaging, prodInputTransport: G.transport, prodInputDelivery: G.delivery, prodInputCAC: G.cac, prodInputMarginPct: G.targetMarginPct }
for (const p of tune.placeholders) {
  if (p.val !== '') bad('tune', `${p.id} pre-filled "${p.val}" — should be blank to inherit`)
  if (p.ph !== `Global: ${expect[p.id]}`) bad('tune', `${p.id} placeholder "${p.ph}" vs "Global: ${expect[p.id]}"`)
}
if (!/follows global/i.test(tune.pinned)) bad('tune', `pinned summary reads "${tune.pinned}"`)
if (tune.globalPrice !== tune.selling) bad('tune', `untuned SKU: global ${tune.globalPrice} != selling ${tune.selling}`)
if (tune.readOnlyHidden) bad('tune', 'no admin session but the read-only notice is hidden')
if (!tune.saveDisabled) bad('tune', 'save enabled without an admin session')

await browser.close()
console.log('\n=== PROBLEMS ===')
if (!problems.length) console.log('  none')
else problems.forEach((s) => console.log('  !!  ' + s))
console.log('\n=== WORTH A LOOK ===')
if (!warn.length) console.log('  none')
else warn.forEach((s) => console.log('  ~   ' + s))
