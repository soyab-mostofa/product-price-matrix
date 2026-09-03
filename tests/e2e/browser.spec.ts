import { expect, test } from '@playwright/test'
import type { CatalogPayload, PricingParams, StoredPricingOverride } from '../../src/types'
import {
  calculateMarketDiscount,
  calculateMarkup,
  calculateSellingPrice,
  resolvePricingParams,
} from '../../src/client/model'

const parseBdt = (text: string): number => {
  const match = text.match(/BDT\s*([\d,]+)/)
  if (!match?.[1]) throw new Error(`No BDT value found in: ${text}`)
  return Number(match[1].replaceAll(',', ''))
}

const rowNames = async (page: import('@playwright/test').Page): Promise<string[]> =>
  page.locator('#body tr[data-row-id] .item-name').allTextContents()

const numbersIn = async (page: import('@playwright/test').Page, selector: string): Promise<number[]> =>
  (await page.locator(selector).allTextContents()).map(parseBdt)

const isAscending = (values: readonly number[]): boolean => values.every((value, index) => index === 0 || values[index - 1]! <= value)
const isDescending = (values: readonly number[]): boolean => values.every((value, index) => index === 0 || values[index - 1]! >= value)

test.beforeEach(async ({ page, request }) => {
  const catalog = await (await request.get('/api/products')).json() as CatalogPayload
  await page.goto('/?playwright=1')
  await page.waitForLoadState('networkidle')
  expect(await page.evaluate(() => document.compatMode)).toBe('CSS1Compat')
  await expect(page.locator('#body tr[data-row-id]')).toHaveCount(catalog.product_count)
  await expect(page.locator('#matrixViewport')).toHaveAttribute('aria-busy', 'false')
})

test('the origin switch moves between the two sourcing books', async ({ page, request }) => {
  const local = await (await request.get('/api/products?origin=local')).json() as CatalogPayload
  const imported = await (await request.get('/api/products?origin=imported')).json() as CatalogPayload

  // Both counts are visible from either book, so the switch advertises the size
  // of the side you are not on.
  const localOption = page.locator('.origin-option[data-origin="local"]')
  const importedOption = page.locator('.origin-option[data-origin="imported"]')
  await expect(localOption).toHaveClass(/is-active/)
  await expect(localOption.locator('.origin-count')).toHaveText(String(local.product_count))
  await expect(importedOption.locator('.origin-count')).toHaveText(String(imported.product_count))

  await importedOption.click()
  await page.waitForURL('**/imported')
  await page.waitForLoadState('networkidle')

  await expect(page.locator('#body tr[data-row-id]')).toHaveCount(imported.product_count)
  await expect(page.locator('.origin-option[data-origin="imported"]')).toHaveClass(/is-active/)
  // Category only exists on the imported book, so its filter appears here.
  await expect(page.locator('#categoryFilter')).toBeVisible()

  await page.locator('.origin-option[data-origin="local"]').click()
  await page.waitForURL((url) => !url.pathname.startsWith('/imported'))
  await page.waitForLoadState('networkidle')
  await expect(page.locator('#body tr[data-row-id]')).toHaveCount(local.product_count)
})

test('header search and filters combine correctly', async ({ page }) => {
  await page.locator('#search').fill('Amla Powder')
  await expect(page.locator('#body tr[data-row-id]')).toHaveCount(2)
  expect(await rowNames(page)).toEqual([
    'Amla Powder/ আমলকী গুঁড়া',
    'Orgagenic Amla Powder (আমলকী)',
  ])

  await page.locator('#search').fill('')
  await page.locator('#brandFilter').selectOption('Neofarmers')
  const brandValues = await page.locator('#body tr[data-row-id] .brand-label').allTextContents()
  expect(brandValues.length).toBeGreaterThan(0)
  expect(new Set(brandValues)).toEqual(new Set(['Neofarmers']))

  await page.locator('#brandFilter').selectOption('')
  await page.locator('#sourceFilter').selectOption('Rokomari')
  await expect(page.locator('#body tr[data-row-id]')).toHaveCount(3)
  await expect(page.locator('#body tr[data-row-id] td[data-source="Rokomari"]')).toHaveCount(3)
})

test('select and clickable header sorts work in both directions', async ({ page }) => {
  const productHeader = page.getByRole('button', { name: 'Product Name ↕' })
  await expect(productHeader).toHaveCSS('border-top-width', '0px')
  await expect(productHeader).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')

  await page.locator('#sort').selectOption('mfgAsc')
  expect(isAscending(await numbersIn(page, '#body tr[data-row-id] .col-mfg'))).toBe(true)

  await page.locator('#sort').selectOption('mfgDesc')
  expect(isDescending(await numbersIn(page, '#body tr[data-row-id] .col-mfg'))).toBe(true)

  await page.locator('#sort').selectOption('marketAsc')
  expect(isAscending(await numbersIn(page, '#body tr[data-row-id] .col-market'))).toBe(true)

  await page.locator('#sort').selectOption('sellingDesc')
  expect(isDescending(await numbersIn(page, '#body tr[data-row-id] .col-selling-price'))).toBe(true)

  await page.locator('#sort').selectOption('product')
  await page.getByRole('button', { name: 'MFG Price ↕' }).click()
  await expect(page.locator('#sort')).toHaveValue('mfgAsc')
  expect(isAscending(await numbersIn(page, '#body tr[data-row-id] .col-mfg'))).toBe(true)
  await expect(page.locator('th.col-mfg')).toHaveAttribute('aria-sort', 'ascending')

  await page.getByRole('button', { name: 'MFG Price ↕' }).click()
  await expect(page.locator('#sort')).toHaveValue('mfgDesc')
  expect(isDescending(await numbersIn(page, '#body tr[data-row-id] .col-mfg'))).toBe(true)
  await expect(page.locator('th.col-mfg')).toHaveAttribute('aria-sort', 'descending')

  await page.getByRole('button', { name: 'Official Store', exact: true }).click()
  await expect(page.locator('#sort')).toHaveValue('srcAsc:Official Store')
  const officialAscending = await numbersIn(page, '#body tr[data-row-id] td[data-source="Official Store"]')
  expect(isAscending(officialAscending)).toBe(true)

  await page.getByRole('button', { name: 'Official Store', exact: true }).click()
  await expect(page.locator('#sort')).toHaveValue('srcDesc:Official Store')
  const officialDescending = await numbersIn(page, '#body tr[data-row-id] td[data-source="Official Store"]')
  expect(isDescending(officialDescending)).toBe(true)
})

test('product discount mode controls update the live calculation preview', async ({ page }) => {
  await page.locator('#body tr[data-row-id]').first().click()
  await page.locator('#tabTuneBtn').click()

  // A fresh SKU inherits the global discount, so the value input is inert
  // until a concrete mode pins it for this product.
  await expect(page.locator('#prodBtnTypeGlobal')).toHaveAttribute('aria-checked', 'true')
  await expect(page.locator('#prodInputDiscountVal')).toBeDisabled()
  await expect(page.locator('#prodSummaryPinned')).toContainText('follows global')

  await page.locator('#prodBtnTypePct').click()
  await expect(page.locator('#prodBtnTypePct')).toHaveAttribute('aria-checked', 'true')
  await expect(page.locator('#prodInputDiscountVal')).toBeEnabled()
  await page.locator('#prodInputDiscountVal').fill('10')
  const percentagePrice = parseBdt(await page.locator('#prodSummarySelling').innerText())

  await page.locator('#prodBtnTypeAmt').click()
  await expect(page.locator('#prodBtnTypeAmt')).toHaveAttribute('aria-checked', 'true')
  const amountPrice = parseBdt(await page.locator('#prodSummarySelling').innerText())

  expect(amountPrice).toBeGreaterThan(percentagePrice)

  // Returning to Global un-pins the discount entirely.
  await page.locator('#prodBtnTypeGlobal').click()
  await expect(page.locator('#prodInputDiscountVal')).toBeDisabled()
  await expect(page.locator('#prodSummaryPinned')).toContainText('follows global')
})

test('an un-pinned tune field keeps following the global engine', async ({ page, request }) => {
  // A SKU tuned only on margin must still absorb a global delivery change.
  const catalog = await (await request.get('/api/products')).json() as CatalogPayload
  const product = catalog.products[0]!
  const tunedRowId = String(product.row)

  const engineResponse = (delivery: number) => JSON.stringify({
    success: true,
    globalParams: {
      packaging: 20, transport: 0, delivery, cac: 0,
      targetMarginPct: 0, discountType: 'pct', discountVal: 0,
    } satisfies PricingParams,
    overrides: { [tunedRowId]: { targetMarginPct: 50, updatedAt: '2026-01-01T00:00:00.000Z' } },
  })

  await page.route('**/api/engine', (route) => route.fulfill({
    contentType: 'application/json',
    body: engineResponse(60),
  }))
  await page.reload()
  await page.waitForLoadState('networkidle')

  const tunedRow = page.locator(`#body tr[data-row-id="${tunedRowId}"] .col-selling-price`)
  await expect(tunedRow.locator('.custom-tune-tag')).toHaveText('Tuned')
  await expect(tunedRow.locator('.custom-tune-tag')).toHaveAttribute('title', /Target Margin/)

  const withCheapDelivery = calculateSellingPrice(product.manufactured_price, {
    packaging: 20, transport: 0, delivery: 60, cac: 0,
    targetMarginPct: 50, discountType: 'pct', discountVal: 0,
  })
  expect(parseBdt(await tunedRow.innerText())).toBe(withCheapDelivery)

  // Raise global delivery; the pinned margin stays, the delivery flows through.
  await page.route('**/api/engine', (route) => route.fulfill({
    contentType: 'application/json',
    body: engineResponse(200),
  }))
  await page.reload()
  await page.waitForLoadState('networkidle')

  const withPriceyDelivery = calculateSellingPrice(product.manufactured_price, {
    packaging: 20, transport: 0, delivery: 200, cac: 0,
    targetMarginPct: 50, discountType: 'pct', discountVal: 0,
  })
  expect(withPriceyDelivery).toBeGreaterThan(withCheapDelivery!)
  expect(parseBdt(await tunedRow.innerText())).toBe(withPriceyDelivery)
})

test('marketplace links remain keyboard-operable and clearly named', async ({ page }) => {
  const link = page.locator('.btn-open-link').first()
  await expect(link).toHaveAttribute('aria-label', /Open .+ on .+ in a new tab/)
  await link.focus()
  const popupPromise = page.waitForEvent('popup')
  await page.keyboard.press('Enter')
  const popup = await popupPromise
  await expect(page.locator('#dialog')).not.toBeVisible()
  await popup.close()
})

test('reference-only MRP provenance is labeled correctly in product details', async ({ page, request }) => {
  const catalog = await (await request.get('/api/products')).json() as CatalogPayload
  const referenceProduct = catalog.products.find((product) => product.mrp_source_type === 'reference')
  expect(referenceProduct).toBeDefined()
  await page.locator(`#body tr[data-row-id="${referenceProduct!.row}"]`).click()
  await expect(page.locator('#tabOverviewContent')).toContainText('MRP (Reference Benchmark)')
  await expect(page.locator('#tabOverviewContent')).not.toContainText('MRP (3rd-Party Avg)')
})

test('product detail tabs support arrow-key navigation', async ({ page }) => {
  await page.locator('#body tr[data-row-id]').first().click()
  await page.locator('#tabOverviewBtn').focus()
  await page.keyboard.press('ArrowRight')
  await expect(page.locator('#tabTuneBtn')).toBeFocused()
  await expect(page.locator('#tabTuneBtn')).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('#tabOverviewBtn')).toHaveAttribute('tabindex', '-1')
  await page.keyboard.press('ArrowLeft')
  await expect(page.locator('#tabOverviewBtn')).toBeFocused()
})

test('comparison toggle keeps a visible mobile label and touch target', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const toggle = page.locator('#toggleSellingChipModeBtn')
  await expect(toggle).toContainText('Compare')
  const box = await toggle.boundingBox()
  expect(box?.width).toBeGreaterThanOrEqual(44)
  expect(box?.height).toBeGreaterThanOrEqual(44)
})

test('catalog failures show a retryable error instead of an empty-filter state', async ({ page }) => {
  await page.route('**/api/products', (route) => route.fulfill({ status: 503, body: 'Unavailable' }))
  await page.reload()
  await page.waitForLoadState('networkidle')

  await expect(page.locator('#matrixViewport')).toHaveAttribute('aria-busy', 'false')
  await expect(page.locator('#syncError')).toContainText('Catalog data could not be loaded')
  await expect(page.locator('#body')).toContainText('Unable to load the live catalog')
  await expect(page.locator('#body tr[data-row-id]')).toHaveCount(0)
})

test('pricing failures hide recommendations and do not claim a full sync', async ({ page }) => {
  await page.route('**/api/engine', (route) => route.fulfill({ status: 503, body: 'Unavailable' }))
  await page.reload()
  await page.waitForLoadState('networkidle')

  await expect(page.locator('#syncError')).toContainText('selling prices are hidden')
  await expect(page.locator('#body tr[data-row-id]').first().locator('.col-selling-price')).toHaveText('—')
  await expect(page.locator('#liveSyncDot')).not.toHaveClass(/synced/)
})

test('all rendered prices and markup chips match the authoritative API', async ({ page, request }) => {
  const catalog = await (await request.get('/api/products')).json() as CatalogPayload
  const engine = await (await request.get('/api/engine')).json() as {
    globalParams: PricingParams
    overrides: Record<string, StoredPricingOverride>
  }
  const rendered = await page.locator('#body tr[data-row-id]').evaluateAll((rows) => Object.fromEntries(rows.map((row) => {
    const sourceCells = [...row.querySelectorAll<HTMLElement>('td[data-source]')].map((cell) => [
      cell.dataset.source!,
      { text: cell.innerText, chip: cell.querySelector<HTMLElement>('.markup-chip')?.innerText ?? '' },
    ])
    return [row.getAttribute('data-row-id')!, {
      mfg: row.querySelector<HTMLElement>('.col-mfg')?.innerText ?? '',
      market: row.querySelector<HTMLElement>('.col-market')?.innerText ?? '',
      selling: row.querySelector<HTMLElement>('.col-selling-price')?.innerText ?? '',
      mrpChip: row.querySelector<HTMLElement>('.col-market .markup-chip')?.innerText ?? '',
      sellingChip: row.querySelector<HTMLElement>('.col-selling-price .markup-chip')?.innerText ?? '',
      sources: Object.fromEntries(sourceCells),
    }]
  }))) as Record<string, {
    mfg: string
    market: string
    selling: string
    mrpChip: string
    sellingChip: string
    sources: Record<string, { text: string; chip: string }>
  }>

  expect(catalog.products).toHaveLength(407)
  expect(Object.keys(rendered)).toHaveLength(407)
  for (const product of catalog.products) {
    const row = rendered[String(product.row)]
    expect(row).toBeDefined()
    expect(parseBdt(row!.mfg)).toBe(Math.round(product.manufactured_price))
    expect(parseBdt(row!.market)).toBe(Math.round(product.market_average_price))

    // Overrides are sparse: un-pinned fields resolve against the global engine.
    const params = resolvePricingParams(engine.globalParams, engine.overrides[String(product.row)])
    const sellingPrice = calculateSellingPrice(product.manufactured_price, params)
    expect(sellingPrice).not.toBeNull()
    expect(parseBdt(row!.selling)).toBe(sellingPrice)

    const mrpMarkup = calculateMarkup(product.market_average_price, product.manufactured_price)
    expect(row!.mrpChip).toContain(String(Math.abs(Number(mrpMarkup!.toFixed(0)))))

    const sellingMarkup = calculateMarkup(sellingPrice, product.manufactured_price)
    expect(row!.sellingChip).toContain(String(Math.abs(Number(sellingMarkup!.toFixed(0)))))

    for (const [source, listing] of Object.entries(product.sources)) {
      const cell = row!.sources[source]
      expect(cell).toBeDefined()
      expect(parseBdt(cell!.text)).toBe(Math.round(listing.price))
      const markup = calculateMarkup(listing.price, product.manufactured_price)
      expect(cell!.chip).toContain(String(Math.abs(Number(markup!.toFixed(0)))))
    }
  }
})

test('market-discount toggle recalculates displayed comparison chips', async ({ page, request }) => {
  const catalog = await (await request.get('/api/products')).json() as CatalogPayload
  const engine = await (await request.get('/api/engine')).json() as {
    globalParams: PricingParams
    overrides: Record<string, StoredPricingOverride>
  }
  await page.locator('#toggleSellingChipModeBtn').click()
  await expect(page.locator('#toggleSellingChipModeBtn')).toHaveAttribute('aria-pressed', 'true')

  for (const product of catalog.products.slice(0, 30)) {
    // Tuned SKUs resolve their sparse override over the global engine.
    const params = resolvePricingParams(engine.globalParams, engine.overrides[String(product.row)])
    const selling = calculateSellingPrice(product.manufactured_price, params)
    const discount = calculateMarketDiscount(selling, product.market_average_price)
    const chip = await page.locator(`#body tr[data-row-id="${product.row}"] .col-selling-price .markup-chip`).innerText()
    expect(chip).toContain(String(Math.abs(Number(discount!.toFixed(0)))))
  }
})

test('a valid zero selling price renders as BDT 0 with full-discount metrics', async ({ page }) => {
  await page.route('**/api/engine', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        globalParams: {
          packaging: 0,
          transport: 0,
          delivery: 0,
          cac: 0,
          targetMarginPct: 0,
          discountType: 'pct',
          discountVal: 100,
        } satisfies PricingParams,
        overrides: {},
      }),
    })
  })
  await page.reload()
  await page.waitForLoadState('networkidle')

  const firstSellingCell = page.locator('#body tr[data-row-id] .col-selling-price').first()
  await expect(firstSellingCell).toContainText('BDT 0')
  await expect(firstSellingCell.locator('.markup-chip')).toContainText('100%')

  await page.locator('#body tr[data-row-id]').first().click()
  await expect(page.locator('#tabOverviewContent')).toContainText('BDT 0')
  await expect(page.locator('#tabOverviewContent')).toContainText('100%')
  await page.locator('#close').click()

  await page.locator('#toggleSellingChipModeBtn').click()
  await expect(firstSellingCell.locator('.markup-chip')).toContainText('100%')
})
