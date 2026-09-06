/**
 * Audit the admin mutation surface: login, the global engine, per-SKU tunes,
 * and the reset controls. Every other audit only reads what the page painted;
 * this one drives the controls that change stored pricing and checks that what
 * the modal previewed is what got saved and repainted.
 *
 * It writes to the dev D1, so it captures the global params and every existing
 * override up front and puts them back in a finally block -- then verifies the
 * restore actually landed. Skips cleanly when admin auth is not configured.
 */
import { readFileSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = process.env.AUDIT_BASE ?? 'http://localhost:5173'
const problems = []
const bad = (a, m) => problems.push(`[${a}] ${m}`)
const report = () => {
  console.log('\n=== PROBLEMS ===')
  if (!problems.length) console.log('  none')
  else problems.forEach((s) => console.log('  !!  ' + s))
}

// The dev password lives in .dev.vars, which wrangler and vite already read.
function adminPassword() {
  if (process.env.AUDIT_ADMIN_PASSWORD) return process.env.AUDIT_ADMIN_PASSWORD
  try {
    return readFileSync(new URL('../../.dev.vars', import.meta.url), 'utf8')
      .split('\n').find((l) => l.startsWith('ADMIN_PASSWORD='))?.slice('ADMIN_PASSWORD='.length).trim()
  } catch { return undefined }
}

// Mirror of the shared formula, kept independent of the app's own module.
const sellingPrice = (cost, p) => {
  const oh = p.packaging + p.transport + p.delivery + (p.cacType === 'pct' ? (cost * p.cac) / 100 : p.cac)
  if (p.targetMarginPct >= 100) return null
  const list = (cost + oh) / (1 - p.targetMarginPct / 100)
  return Math.round(Math.max(0, p.discountType === 'pct' ? list * (1 - p.discountVal / 100) : list - p.discountVal))
}
const resolve = (g, ov) => {
  if (!ov) return g
  const out = { ...g }
  for (const k of ['packaging', 'transport', 'delivery', 'targetMarginPct']) if (ov[k] != null) out[k] = ov[k]
  if (ov.cacType != null && ov.cac != null) { out.cacType = ov.cacType; out.cac = ov.cac }
  if (ov.discountType != null && ov.discountVal != null) { out.discountType = ov.discountType; out.discountVal = ov.discountVal }
  return out
}
const parseBdt = (t) => { const m = String(t).match(/BDT\s*([\d,]+)/); return m ? Number(m[1].replaceAll(',', '')) : null }

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } })
const page = await ctx.newPage()

const engineState = async () => (await (await page.request.get(`${BASE}/api/engine`)).json())
const authState = async () => (await (await page.request.get(`${BASE}/api/auth`)).json())

const PW = adminPassword()
if (!(await authState()).configured || !PW) {
  console.log('admin auth not configured (no .dev.vars / AUDIT_ADMIN_PASSWORD) — skipping')
  await browser.close()
  report()
  process.exit(0)
}

// Everything this audit will disturb, captured before it disturbs anything.
const start = await engineState()
const ORIGINAL_GLOBAL = start.globalParams
const ORIGINAL_OVERRIDES = start.overrides ?? {}

// The app's own client sends this header; it is what makes the mutation
// same-origin rather than a cross-site form post.
const H = { Origin: BASE, Referer: `${BASE}/`, 'X-Price-Matrix-Admin': '1' }

const settle = async () => {
  await page.waitForSelector('#body tr[data-row-id]', { timeout: 15000 })
  await page.waitForFunction(() => document.getElementById('matrixViewport')?.getAttribute('aria-busy') === 'false', null, { timeout: 15000 })
  const err = await page.evaluate(() => { const e = document.getElementById('syncError'); return e && !e.hidden ? e.textContent.trim() : null })
  if (err) bad('load', `page loaded degraded: ${err}`)
}
const closeDialogs = () => page.evaluate(() => document.querySelectorAll('dialog[open]').forEach((d) => d.close()))
const sellingOf = (row) => page.$eval(`#body tr[data-row-id="${row}"] .col-selling-price .num-price`, (e) => e.textContent.trim()).catch(() => null)

try {
  // ── Login guards ────────────────────────────────────────────────────────
  // Without the custom header a rejection says nothing about the password, so
  // check that separately -- otherwise a wrong-password test passes on a 403.
  const noCsrf = await page.request.post(`${BASE}/api/auth`, { data: { password: PW }, headers: { Origin: BASE, Referer: `${BASE}/` } })
  if (noCsrf.status() !== 403) bad('auth', `login without the admin header should be 403, got ${noCsrf.status()}`)
  const wrong = await page.request.post(`${BASE}/api/auth`, { data: { password: `${PW}-wrong` }, headers: H })
  if (wrong.ok()) bad('auth', 'a wrong password was accepted')
  else if (wrong.status() === 403) bad('auth', 'wrong password was refused as cross-origin, so the credential was never checked')

  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' })
  await settle()
  await page.click('#adminLoginBtn')
  await page.waitForSelector('#authModal[open]', { timeout: 5000 })
  await page.fill('#adminPassword', PW)
  await page.click('#authForm button[type=submit]')
  await page.waitForTimeout(1000)
  if (!(await authState()).authenticated) bad('auth', 'logging in through the modal did not create a session')
  await closeDialogs()

  const cat = await (await page.request.get(`${BASE}/api/products?origin=local`)).json()
  const byRow = new Map(cat.products.map((p) => [p.row, p]))

  // ── Global engine: preview tracks the form, then saves ──────────────────
  const openEngine = async () => {
    await closeDialogs()
    await page.click('#openEngineBtn')
    await page.waitForSelector('#engineModal[open]', { timeout: 5000 })
    await page.waitForTimeout(250)
  }
  await openEngine()
  const beforeSample = await page.locator('#summarySample').textContent()
  await page.click('#btnCacTypeAmt')
  await page.fill('#inputCAC', '40')
  await page.waitForTimeout(350)
  const afterSample = await page.locator('#summarySample').textContent()
  if (beforeSample === afterSample) bad('preview', `the worked example did not move when CAC changed (stuck at ${beforeSample?.trim()})`)
  // 1000 source cost + the form's own overhead, with nothing else pinned.
  const previewParams = { ...ORIGINAL_GLOBAL, cac: 40, cacType: 'amt' }
  const wantSample = sellingPrice(1000, previewParams)
  if (parseBdt(afterSample) !== wantSample) bad('preview', `worked example ${parseBdt(afterSample)} != ${wantSample} at a 1000 source cost`)

  await page.click('#applyEngineBtn')
  await page.waitForTimeout(1200)
  const savedState = await engineState()
  const saved = savedState.globalParams
  if (saved.cac !== 40 || saved.cacType !== 'amt') bad('engine', `global save did not land: ${JSON.stringify(saved)}`)
  await closeDialogs()
  await page.waitForTimeout(600)
  const repriced = await page.$$eval('#body tr[data-row-id]', (rows) => rows.map((r) => ({
    row: Number(r.dataset.rowId), price: r.querySelector('.col-selling-price .num-price')?.textContent.trim() ?? null,
  })))
  // An already-tuned SKU keeps its pinned fields, so compare each row against
  // its own resolved params rather than against global.
  const stale = repriced.filter((c) => parseBdt(c.price)
    !== sellingPrice(Number(byRow.get(c.row).manufactured_price), resolve(saved, savedState.overrides?.[String(c.row)]))).length
  if (stale) bad('engine', `${stale} of ${repriced.length} rows did not reprice after the global save`)

  // A percentage CAC above 100 would price every SKU below its own cost.
  await openEngine()
  await page.click('#btnCacTypePct')
  await page.fill('#inputCAC', '150')
  await page.click('#applyEngineBtn')
  await page.waitForTimeout(900)
  if ((await engineState()).globalParams.cac === 150) bad('validate', 'a 150% CAC was accepted')
  await closeDialogs()

  // ── Per-SKU tune ────────────────────────────────────────────────────────
  const target = cat.products.find((p) => Number(p.manufactured_price) > 200) ?? cat.products[0]
  const openTune = async () => {
    await closeDialogs()
    await page.click(`#body tr[data-row-id="${target.row}"]`)
    await page.waitForSelector('#dialog[open]', { timeout: 5000 })
    await page.click('#tabTuneBtn')
    await page.waitForTimeout(300)
  }
  const liveGlobal = (await engineState()).globalParams
  await openTune()
  const beforeTune = await page.locator('#prodSummarySelling').textContent()
  await page.click('#prodBtnCacPct')
  await page.fill('#prodInputCAC', '12.5')
  await page.waitForTimeout(400)
  const afterTune = await page.locator('#prodSummarySelling').textContent()
  if (beforeTune === afterTune) bad('preview', `the SKU preview did not move on a 12.5% CAC (stuck at ${beforeTune?.trim()})`)
  const wantTuned = sellingPrice(Number(target.manufactured_price), { ...liveGlobal, cac: 12.5, cacType: 'pct' })
  if (parseBdt(afterTune) !== wantTuned) bad('preview', `SKU preview ${parseBdt(afterTune)} != ${wantTuned}`)

  await page.click('#saveProductCustomEngineBtn')
  await page.waitForTimeout(1200)
  const pinned = (await engineState()).overrides?.[String(target.row)]
  if (!pinned || pinned.cac !== 12.5 || pinned.cacType !== 'pct') bad('tune', `the CAC pair was not persisted: ${JSON.stringify(pinned)}`)
  await closeDialogs()
  await page.waitForTimeout(700)
  if (parseBdt(await sellingOf(target.row)) !== wantTuned) bad('tune', `the table shows ${parseBdt(await sellingOf(target.row))} where the modal previewed ${wantTuned}`)

  // Pinning a value identical to global should store nothing at all.
  await openTune()
  await page.click('#prodBtnCacGlobal')
  await page.fill('#prodInputPackaging', String(liveGlobal.packaging))
  await page.click('#saveProductCustomEngineBtn')
  await page.waitForTimeout(1200)
  const sparse = (await engineState()).overrides?.[String(target.row)]
  if (sparse?.packaging !== undefined) bad('tune', `packaging equal to global was stored anyway: ${JSON.stringify(sparse)}`)

  // Reset this SKU.
  await openTune()
  await page.click('#prodBtnCacAmt')
  await page.fill('#prodInputCAC', '77')
  await page.click('#saveProductCustomEngineBtn')
  await page.waitForTimeout(1100)
  if (!(await engineState()).overrides?.[String(target.row)]) bad('tune', 'the seed tune for the reset check did not save')
  await openTune()
  await page.click('#clearProductCustomEngineBtn')
  await page.waitForTimeout(1200)
  if ((await engineState()).overrides?.[String(target.row)]) bad('tune', 'reset to global left the override behind')
  await closeDialogs()

  // ── Reset every tune ────────────────────────────────────────────────────
  await openTune()
  await page.click('#prodBtnCacAmt')
  await page.fill('#prodInputCAC', '88')
  await page.click('#saveProductCustomEngineBtn')
  await page.waitForTimeout(1100)
  await openEngine()
  // The control demands the literal word, so an empty accept must not wipe.
  page.once('dialog', (d) => d.accept(''))
  await page.click('#resetCustomOverridesBtn')
  await page.waitForTimeout(1000)
  if (!(await engineState()).overrides?.[String(target.row)]) bad('reset', 'reset-all fired without the typed confirmation')
  page.once('dialog', (d) => d.accept('RESET'))
  await page.click('#resetCustomOverridesBtn')
  await page.waitForTimeout(1400)
  if (Object.keys((await engineState()).overrides ?? {}).length) bad('reset', 'reset-all left overrides behind')
  await closeDialogs()
} catch (err) {
  bad('crash', err.message.split('\n')[0])
} finally {
  // ── Put the dev database back exactly as it was ─────────────────────────
  try {
    await page.request.post(`${BASE}/api/engine`, { data: ORIGINAL_GLOBAL, headers: H })
    await page.request.delete(`${BASE}/api/overrides?all=true`, { headers: H })
    for (const [row, override] of Object.entries(ORIGINAL_OVERRIDES)) {
      const { updatedAt, ...pinned } = override
      if (!Object.keys(pinned).length) continue
      await page.request.post(`${BASE}/api/overrides`, { data: { productRowId: Number(row), override: pinned }, headers: H })
    }
    const back = await engineState()
    if (JSON.stringify(back.globalParams) !== JSON.stringify(ORIGINAL_GLOBAL)) {
      bad('restore', `global params not restored: ${JSON.stringify(back.globalParams)}`)
    }
    if (Object.keys(back.overrides ?? {}).length !== Object.keys(ORIGINAL_OVERRIDES).length) {
      bad('restore', `restored ${Object.keys(back.overrides ?? {}).length} overrides, started with ${Object.keys(ORIGINAL_OVERRIDES).length}`)
    }
  } catch (err) {
    bad('restore', `could not restore the dev database: ${err.message.split('\n')[0]}`)
  }
  await browser.close()
  report()
}
