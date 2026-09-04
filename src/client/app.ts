import type { CatalogPayload, PricingOverride, PricingParams, Product, StoredPricingOverride } from '../types'
import {
  calculateMarketDiscount,
  calculateMarkup,
  calculateSellingPrice,
  filterProducts,
  nextPinnedSort,
  overriddenFields,
  PINNED_SORT_VALUES,
  PRICING_DEFAULTS,
  resolvePricingParams,
  sortProducts,
  type SortValue,
} from './model'

interface EngineResponse {
  success: boolean
  globalParams?: PricingParams
  overrides?: Record<string, StoredPricingOverride>
  error?: string
}

interface AuthStatusResponse {
  success: boolean
  configured: boolean
  authenticated: boolean
  error?: string
}

const money = new Intl.NumberFormat('en-BD', {
  style: 'currency',
  currency: 'BDT',
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
})

let products: Product[] = []
/** row id -> product, so row clicks don't linear-scan the catalog. */
let productsByRow = new Map<number, Product>()
let sources: string[] = []
let globalCostParams: PricingParams = { ...PRICING_DEFAULTS }
let productOverrides: Record<string, StoredPricingOverride> = {}
let sellingChipMode: 'markup' | 'discount' = 'markup'
let activeProductDetail: Product | null = null
let currentGlobalDiscountType: 'pct' | 'amt' = 'pct'
/** 'global' = inherit the global discount; 'pct'/'amt' pin it for this SKU. */
let currentProdDiscountType: 'global' | 'pct' | 'amt' = 'global'
let isAdminAuthenticated = false
let authConfigured = false
let catalogLoaded = false
let pricingLoaded = false

/** Tunable input IDs, kept in one place so the modal markup and the client agree. */
const ENGINE_INPUT_IDS = [
  'inputPackaging', 'inputTransport', 'inputDelivery', 'inputCAC', 'inputMarginPct', 'inputDiscountVal',
] as const
const PRODUCT_INPUT_IDS = [
  'prodInputPackaging', 'prodInputTransport', 'prodInputDelivery', 'prodInputCAC',
  'prodInputMarginPct', 'prodInputDiscountVal',
] as const

const searchInput = document.getElementById('search') as HTMLInputElement | null
const brandFilter = document.getElementById('brandFilter') as HTMLSelectElement | null
const sourceFilter = document.getElementById('sourceFilter') as HTMLSelectElement | null
const categoryFilter = document.getElementById('categoryFilter') as HTMLSelectElement | null
const sortSelect = document.getElementById('sort') as HTMLSelectElement | null
const bodyElement = document.getElementById('body') as HTMLTableSectionElement | null
const emptyElement = document.getElementById('empty') as HTMLDivElement | null
const headerRow = document.getElementById('headerRow') as HTMLTableRowElement | null
const matrixViewport = document.getElementById('matrixViewport') as HTMLElement | null
const syncError = document.getElementById('syncError') as HTMLElement | null
const aboveMarketBanner = document.getElementById('aboveMarketBanner') as HTMLElement | null
const liveSyncDot = document.getElementById('liveSyncDot') as HTMLElement | null
const productTotal = document.getElementById('productTotal') as HTMLElement | null
const listingTotal = document.getElementById('listingTotal') as HTMLElement | null
const toggleSellingChipBtn = document.getElementById('toggleSellingChipModeBtn') as HTMLButtonElement | null
const sellingChipBtnLabel = document.getElementById('sellingChipBtnLabel') as HTMLElement | null
const openEngineBtn = document.getElementById('openEngineBtn') as HTMLButtonElement | null
const adminLoginBtn = document.getElementById('adminLoginBtn') as HTMLButtonElement | null
const authModal = document.getElementById('authModal') as HTMLDialogElement | null
const engineModal = document.getElementById('engineModal') as HTMLDialogElement | null
const productModal = document.getElementById('dialog') as HTMLDialogElement | null

function esc(value: unknown): string {
  return String(value ?? '').replace(/[&<>'"]/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
  }[char] || char))
}

function getMarkupChip(pct: number | null, isAboveMarket = false, aboveMarketTitle = ''): string {
  if (pct === null) return ''
  if (isAboveMarket) {
    const defaultTitle = `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}% vs source cost · Above market reference`
    return `<span class="markup-chip above-market" title="${esc(aboveMarketTitle || defaultTitle)}">${pct >= 0 ? '↑+' : '↓'}${pct.toFixed(0)}%</span>`
  }
  if (pct < -0.01) {
    return `<span class="markup-chip neg" title="${Math.abs(pct).toFixed(1)}% below source cost">↓${pct.toFixed(0)}%</span>`
  }
  if (Math.abs(pct) <= 0.01) {
    return '<span class="markup-chip zero" title="Equal to source cost">0%</span>'
  }
  if (pct <= 15) return `<span class="markup-chip t1" title="+${pct.toFixed(1)}% markup over source cost">↑+${pct.toFixed(0)}%</span>`
  if (pct <= 35) return `<span class="markup-chip t2" title="+${pct.toFixed(1)}% markup over source cost">↑+${pct.toFixed(0)}%</span>`
  if (pct <= 60) return `<span class="markup-chip t3" title="+${pct.toFixed(1)}% markup over source cost">↑+${pct.toFixed(0)}%</span>`
  return `<span class="markup-chip t4" title="+${pct.toFixed(1)}% markup over source cost">↑+${pct.toFixed(0)}%</span>`
}

function getMarketDiscountChip(discPct: number | null, isAboveMarket = false, aboveMarketTitle = ''): string {
  if (discPct === null) return ''
  if (isAboveMarket) {
    const defaultTitle = `${Math.abs(discPct).toFixed(1)}% above market reference`
    return `<span class="markup-chip above-market" title="${esc(aboveMarketTitle || defaultTitle)}">↑+${Math.abs(discPct).toFixed(0)}%</span>`
  }
  if (discPct > 0.01) {
    return `<span class="markup-chip mkt-disc" title="${discPct.toFixed(1)}% discount off Market Average price">↓-${discPct.toFixed(0)}%</span>`
  }
  if (Math.abs(discPct) <= 0.01) {
    return '<span class="markup-chip zero" title="Selling at Par with Market Average price">0%</span>'
  }
  return `<span class="markup-chip mkt-prem" title="${Math.abs(discPct).toFixed(1)}% above Market Average price">↑+${Math.abs(discPct).toFixed(0)}%</span>`
}

function parseApiError(data: unknown, fallback: string): string {
  if (!data || typeof data !== 'object') return fallback
  const err = (data as { error?: unknown }).error
  if (typeof err === 'string' && err.trim()) return err
  if (err && typeof err === 'object') {
    if ('message' in err && typeof (err as { message: unknown }).message === 'string') {
      const msg = (err as { message: string }).message
      try {
        const parsed = JSON.parse(msg)
        if (Array.isArray(parsed) && parsed[0]?.message) return String(parsed[0].message)
      } catch {}
      return msg
    }
    if ('issues' in err && Array.isArray((err as { issues: unknown[] }).issues)) {
      const first = (err as { issues: Array<{ message?: string }> }).issues[0]
      if (first?.message) return first.message
    }
  }
  return fallback
}

/** Human labels for the tunable fields, used in the Tuned pill tooltip. */
const FIELD_LABELS: Record<string, string> = {
  packaging: 'Packaging',
  transport: 'Transport',
  delivery: 'Delivery',
  cac: 'CAC',
  targetMarginPct: 'Target Margin',
  discountType: 'Discount',
  discountVal: 'Discount',
}

/**
 * Effective parameters for one SKU: the live global engine with this product's
 * pinned fields laid over it. Un-pinned fields keep tracking global.
 */
function getProductParams(rowId: number): PricingParams {
  return resolvePricingParams(globalCostParams, productOverrides[String(rowId)])
}

/** e.g. "Target Margin, Discount" — what this SKU pins against the global engine. */
function describeOverride(override: StoredPricingOverride | undefined): string {
  const labels = overriddenFields(override).map((field) => FIELD_LABELS[field] ?? field)
  return [...new Set(labels)].join(', ')
}

function computeSellingPrice(mfgPrice: number, rowId?: number): number | null {
  if (!pricingLoaded) return null
  const params = rowId ? getProductParams(rowId) : globalCostParams
  return calculateSellingPrice(mfgPrice, params)
}

function updateSellingChipToggleUI() {
  if (!toggleSellingChipBtn || !sellingChipBtnLabel) return
  if (sellingChipMode === 'discount') {
    toggleSellingChipBtn.classList.add('active-mode')
    toggleSellingChipBtn.setAttribute('aria-pressed', 'true')
    toggleSellingChipBtn.setAttribute('aria-label', 'Show product markup percentage')
    sellingChipBtnLabel.textContent = 'View Product Markup %'
  } else {
    toggleSellingChipBtn.classList.remove('active-mode')
    toggleSellingChipBtn.setAttribute('aria-pressed', 'false')
    toggleSellingChipBtn.setAttribute('aria-label', 'Show market discount percentage')
    sellingChipBtnLabel.textContent = 'View Market Discount %'
  }
}

/**
 * Reflect the current admin state across the UI.
 *
 * Reading is public: the matrix, the engine values, and every tune are visible
 * to anyone. Writing is admin-only, so without a session the inputs stay
 * readable but disabled and a banner says why.
 */
function updateAdminUI() {
  if (adminLoginBtn) {
    adminLoginBtn.hidden = !authConfigured
    adminLoginBtn.textContent = isAdminAuthenticated ? 'Log out' : 'Admin Login'
  }
  if (openEngineBtn) openEngineBtn.hidden = false

  const readOnly = !isAdminAuthenticated
  const notice = authConfigured
    ? 'Read-only view. Log in as admin to change pricing.'
    : 'Read-only view. Admin authentication is not configured on this deployment.'

  for (const id of ['engineReadOnlyBanner', 'productReadOnlyBanner']) {
    const banner = document.getElementById(id)
    if (!banner) continue
    banner.hidden = !readOnly
    banner.textContent = notice
  }

  for (const id of ['saveProductCustomEngineBtn', 'clearProductCustomEngineBtn', 'applyEngineBtn', 'resetCustomOverridesBtn']) {
    const button = document.getElementById(id) as HTMLButtonElement | null
    if (button) button.disabled = readOnly
  }

  // Inputs stay readable so the numbers behind a price are always inspectable.
  for (const id of [...ENGINE_INPUT_IDS, ...PRODUCT_INPUT_IDS]) {
    const input = document.getElementById(id) as HTMLInputElement | null
    if (input) input.readOnly = readOnly
  }
  for (const button of document.querySelectorAll<HTMLButtonElement>('.discount-type-btn')) {
    button.disabled = readOnly
  }
}

function getVisibleSources(list: Product[]): string[] {
  if (!list.length) return []
  return sources.filter((source) => list.some((p) => p.sources[source]?.price !== undefined && p.sources[source]?.price !== null))
}

function updateHeaders(activeSources: string[]) {
  if (!headerRow) return
  headerRow.querySelectorAll('th.source-col-head').forEach((el) => el.remove())

  activeSources.forEach((source) => {
    const th = document.createElement('th')
    th.className = 'source-col-head'
    th.dataset.source = source
    th.setAttribute('aria-sort', 'none')
    th.innerHTML = `
      <button type="button" class="sort-button source-head-wrap" title="Sort ${esc(source)} prices">
        <span>${esc(source)}</span>
      </button>
    `
    th.querySelector('button')?.addEventListener('click', () => {
      if (!sortSelect) return
      if (sortSelect.value === `srcAsc:${source}`) {
        sortSelect.value = `srcDesc:${source}`
      } else {
        if (![...sortSelect.options].some((opt) => opt.value === `srcAsc:${source}`)) {
          sortSelect.add(new Option(`${source}: Low → High`, `srcAsc:${source}`))
          sortSelect.add(new Option(`${source}: High → Low`, `srcDesc:${source}`))
        }
        sortSelect.value = `srcAsc:${source}`
      }
      render()
    })
    headerRow.appendChild(th)
  })
}

function mrpProvenance(p: Product): { label: string; tooltip: string; className: string } {
  const mktAvg = Number(p.market_average_price)
  const official = p.sources['Official Store']
  if (p.mrp_source_type === 'workbook') {
    return {
      label: 'Workbook MRP',
      tooltip: `Workbook MRP: ${money.format(mktAvg)} — the agreed retail benchmark this SKU was sourced against. Channel prices on the right are live listings and may sit above or below it.`,
      className: 'num-price mrp-ref',
    }
  }
  if (p.mrp_source_type === 'official' && official) {
    const seller = official.seller || `${p.brand_name} Official Store`
    return {
      label: 'Official Store',
      tooltip: `Official Brand MRP: ${money.format(mktAvg)} (${seller})`,
      className: 'num-price mrp-official',
    }
  }
  if (p.mrp_source_type === 'third_party_avg') {
    return {
      label: '3rd-Party Avg',
      tooltip: `3rd-Party Market Average: ${money.format(mktAvg)} (No official store listing; calculated across active 3rd-party channels)`,
      className: 'num-price mrp-thirdparty',
    }
  }
  return {
    label: 'Reference Benchmark',
    tooltip: `Reference Benchmark MRP: ${money.format(mktAvg)} (No verified marketplace listings; sourced from the internal workbook benchmark)`,
    className: 'num-price mrp-ref',
  }
}

function sourceCell(p: Product, source: string): string {
  const listing = p.sources[source]
  if (!listing) return '<td class="source-data-cell"><span class="cell-dash">—</span></td>'
  const price = Number(listing.price)
  const mfg = Number(p.manufactured_price)
  const markupPct = calculateMarkup(price, mfg)
  const markupChip = getMarkupChip(markupPct)
  // A price seeded from the workbook has no product page to open yet, so it
  // shows an unverified marker in place of the deep link.
  const link = listing.verified && listing.url
    ? `<a href="${esc(listing.url)}" class="btn-open-link" target="_blank" rel="noopener noreferrer" aria-label="Open ${esc(p.product_name)} on ${esc(source)} in a new tab" title="Open listing on ${esc(source)}" onclick="event.stopPropagation()">↗</a>`
    : `<span class="listing-unverified" role="img" aria-label="Unverified price on ${esc(source)} — no confirmed product page yet" title="Unverified: price recorded from research, no confirmed product page yet">◌</span>`

  return `
    <td class="source-data-cell" data-source="${esc(source)}">
      <div class="price-card">
        <div class="price-left-group">
          <span class="price-val">${esc(money.format(price))}</span>
          ${markupChip}
        </div>
        ${link}
      </div>
    </td>
  `
}

function filtered(): Product[] {
  const list = filterProducts(products, {
    query: searchInput?.value || '',
    brand: brandFilter?.value || '',
    source: sourceFilter?.value || '',
    category: categoryFilter?.value || '',
  })
  return sortProducts(
    list,
    (sortSelect?.value || 'product') as SortValue,
    (product) => computeSellingPrice(product.manufactured_price, product.row),
    sources,
  )
}

function updateSortIndicators(): void {
  if (!headerRow) return
  const current = sortSelect?.value || 'product'
  headerRow.querySelectorAll<HTMLTableCellElement>('th').forEach((header) => header.setAttribute('aria-sort', 'none'))

  headerRow.querySelectorAll<HTMLButtonElement>('button[data-sort]').forEach((button) => {
    const key = button.dataset.sort
    if (!key || !(key in PINNED_SORT_VALUES)) return
    const [ascending, descending] = PINNED_SORT_VALUES[key as keyof typeof PINNED_SORT_VALUES]
    const header = button.closest('th')
    if (current === ascending) header?.setAttribute('aria-sort', 'ascending')
    if (current === descending) header?.setAttribute('aria-sort', 'descending')
  })

  headerRow.querySelectorAll<HTMLTableCellElement>('th[data-source]').forEach((header) => {
    const source = header.dataset.source
    if (current === `srcAsc:${source}`) header.setAttribute('aria-sort', 'ascending')
    if (current === `srcDesc:${source}`) header.setAttribute('aria-sort', 'descending')
  })
}

function render() {
  if (!bodyElement || !emptyElement) return
  const list = filtered()
  const activeSources = getVisibleSources(list)
  let aboveMarketCount = 0

  updateHeaders(activeSources)
  updateSortIndicators()
  updateSellingChipToggleUI()

  bodyElement.innerHTML = list.map((p) => {
    const mfg = Number(p.manufactured_price)
    const mktAvg = Number(p.market_average_price)
    let avgMarkupChip = ''

    if (mktAvg > 0 && mfg > 0) {
      const mrpMarkupPct = calculateMarkup(mktAvg, mfg)
      avgMarkupChip = getMarkupChip(mrpMarkupPct)
    }

    const provenance = mrpProvenance(p)
    const mrpTooltip = provenance.tooltip
    const mrpClass = provenance.className

    const marketAvgDisplay = `
      <div class="dual-metric-cell" title="${esc(mrpTooltip)}">
        <span class="${mrpClass}">${esc(money.format(mktAvg))}</span>
        ${avgMarkupChip}
      </div>
    `

    const override = productOverrides[String(p.row)]
    const pinnedFields = describeOverride(override)
    const hasOverride = pinnedFields.length > 0
    const calculatedSelling = computeSellingPrice(mfg, p.row)
    let sellingDisplay = '<span class="cell-dash">—</span>'

    if (calculatedSelling !== null && mfg > 0) {
      const aboveMarket = mktAvg > 0 && calculatedSelling > mktAvg
      const overBy = aboveMarket ? Math.round(((calculatedSelling - mktAvg) / mktAvg) * 100) : 0
      const aboveTitle = aboveMarket
        ? `Above market: Recommended price ${money.format(calculatedSelling)} is ${overBy}% above ${provenance.label} reference (${money.format(mktAvg)})`
        : ''

      let activeChipHtml = ''
      if (sellingChipMode === 'discount' && mktAvg > 0) {
        const mktDiscPct = calculateMarketDiscount(calculatedSelling, mktAvg)
        activeChipHtml = getMarketDiscountChip(mktDiscPct, aboveMarket, aboveTitle)
      } else {
        const sellingMarkupPct = calculateMarkup(calculatedSelling, mfg)
        activeChipHtml = getMarkupChip(sellingMarkupPct, aboveMarket, aboveTitle)
      }

      const tunedOn = override?.updatedAt ? ` · tuned ${new Date(override.updatedAt).toLocaleDateString()}` : ''
      const tuneTitle = `Custom pricing for this SKU — pinned: ${pinnedFields}${tunedOn}. Everything else follows the global engine.`
      const priceClass = hasOverride ? 'custom-tuned' : 'selling'
      sellingDisplay = `
        <div class="dual-metric-cell">
          ${hasOverride ? `<span class="custom-tune-tag" title="${esc(tuneTitle)}">Tuned</span>` : ''}
          <span class="num-price ${priceClass}">${esc(money.format(calculatedSelling))}</span>
          ${activeChipHtml}
        </div>
      `
      if (aboveMarket) aboveMarketCount += 1
    }

    return `
      <tr tabindex="0" data-row-id="${p.row}">
        <td class="col-product">
          <div class="item-name" title="${esc(p.product_name)}">${esc(p.product_name)}</div>
          ${p.size ? `<div class="item-size">${esc(p.size)}</div>` : ''}
        </td>
        <td class="col-brand"><span class="brand-label">${esc(p.brand_name)}</span></td>
        <td class="col-mfg"><span class="num-price mfg">${esc(money.format(p.manufactured_price))}</span></td>
        <td class="col-market">${marketAvgDisplay}</td>
        <td class="col-selling-price">${sellingDisplay}</td>
        ${activeSources.map((s) => sourceCell(p, s)).join('')}
      </tr>
    `
  }).join('')

  emptyElement.hidden = list.length > 0

  // Catalog-level summary: one over-market SKU is a tuning job, a hundred is a
  // broken global model, and the operator should not have to scroll to find out.
  if (aboveMarketBanner) {
    if (aboveMarketCount > 0) {
      const noun = aboveMarketCount === 1 ? 'SKU prices' : 'SKUs price'
      aboveMarketBanner.textContent =
        `${aboveMarketCount.toLocaleString()} of ${list.length.toLocaleString()} shown ${noun} above the market reference at the current engine settings.`
      aboveMarketBanner.hidden = false
    } else {
      aboveMarketBanner.hidden = true
    }
  }
}

/** Coalesce burst input (typing) into a single repaint. */
let renderTimer: ReturnType<typeof setTimeout> | undefined
function debouncedRender(): void {
  clearTimeout(renderTimer)
  renderTimer = setTimeout(render, 140)
}

function openDetail(p: Product) {
  activeProductDetail = p
  const dialogBrand = document.getElementById('dialogBrand')
  const dialogName = document.getElementById('dialogName')
  if (dialogBrand) dialogBrand.textContent = p.size ? `${p.brand_name} · ${p.size}` : p.brand_name
  if (dialogName) dialogName.textContent = p.product_name

  const mfg = Number(p.manufactured_price)
  const mktAvg = Number(p.market_average_price)
  const calculatedSelling = computeSellingPrice(mfg, p.row)
  const params = getProductParams(p.row)
  const overhead = Number(params.packaging) + Number(params.transport) + Number(params.delivery) + Number(params.cac)
  // Label each stat by what is actually pinned: a margin-only tune must not
  // claim the overhead is custom when every cost field still follows global.
  const detailOverride = productOverrides[String(p.row)]
  const detailPinned = describeOverride(detailOverride)
  const overheadIsTuned = overriddenFields(detailOverride)
    .some((field) => field === 'packaging' || field === 'transport' || field === 'delivery' || field === 'cac')
  const sellingMarkupPct = calculatedSelling !== null && mfg > 0 ? calculateMarkup(calculatedSelling, mfg) : null
  const marketDiscPct = calculatedSelling !== null && mktAvg > 0 ? calculateMarketDiscount(calculatedSelling, mktAvg) : null
  const detailProvenance = mrpProvenance(p)
  const detailAboveMarket = mktAvg > 0 && calculatedSelling !== null && calculatedSelling > mktAvg
  const detailOverBy = detailAboveMarket ? Math.round(((calculatedSelling - mktAvg) / mktAvg) * 100) : 0
  const detailAboveTitle = detailAboveMarket
    ? `Above market: Recommended price ${money.format(calculatedSelling)} is ${detailOverBy}% above ${detailProvenance.label} (${money.format(mktAvg)})`
    : ''

  let out = `
    <div class="detail-stats-grid">
      <div class="detail-stat-box"><span>Source Cost</span><strong>${esc(money.format(mfg))}</strong></div>
      <div class="detail-stat-box" title="${esc(detailProvenance.tooltip)}">
        <span>MRP (${esc(detailProvenance.label)})</span>
        <strong style="display:flex;align-items:center;gap:6px;">
          ${esc(money.format(mktAvg))}
          ${getMarkupChip(calculateMarkup(mktAvg, mfg))}
        </strong>
      </div>
      <div class="detail-stat-box">
        <span>Variable Overhead ${overheadIsTuned ? '(Tuned)' : ''}</span>
        <strong>${esc(money.format(overhead))}</strong>
      </div>
      <div class="detail-stat-box"${detailPinned ? ` title="${esc(`Pinned for this SKU: ${detailPinned}. Everything else follows the global engine.`)}"` : ''}>
        <span>Selling Price ${detailPinned ? '(Tuned)' : ''}</span>
        <strong style="color:var(--brand-blue);display:flex;align-items:center;flex-wrap:wrap;gap:6px;">
          ${calculatedSelling !== null ? esc(money.format(calculatedSelling)) : '—'}
          ${getMarkupChip(sellingMarkupPct, detailAboveMarket, detailAboveTitle)}
          ${marketDiscPct !== null ? getMarketDiscountChip(marketDiscPct, detailAboveMarket, detailAboveTitle) : ''}
        </strong>
      </div>
    </div>
    <div class="detail-sources-list">
  `

  const matchedSources = sources.filter((s) => p.sources[s])
  if (!matchedSources.length) {
    out += '<div style="color:var(--text-muted);padding:10px 0;font-size:12px;">No external verified listings found.</div>'
  } else {
    matchedSources.forEach((s) => {
      const item = p.sources[s]
      if (!item) return
      const markupPct = calculateMarkup(Number(item.price), mfg)
      const markupChip = getMarkupChip(markupPct)
      const detailLink = item.verified && item.url
        ? `<a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">Open link ↗</a>`
        : '<span class="listing-unverified-text">Unverified — no confirmed product page</span>'
      out += `
        <div class="detail-source-row">
          <div>
            <div style="font-weight:600;font-size:13px;color:var(--text-main);">${esc(s)}</div>
            <div style="font-size:11.5px;color:var(--text-muted);margin-top:2px;">${esc(item.matched_title || '')}</div>
          </div>
          <div style="text-align:right;">
            <div style="font-weight:700;font-size:15px;color:var(--brand-blue);display:flex;align-items:center;justify-content:flex-end;gap:6px;">
              ${esc(money.format(item.price))} ${markupChip}
            </div>
            ${detailLink}
          </div>
        </div>
      `
    })
  }
  out += '</div>'

  const tabOverviewContent = document.getElementById('tabOverviewContent')
  if (tabOverviewContent) tabOverviewContent.innerHTML = out

  // Populate per-product inputs. A pinned field shows its value; an inherited
  // field stays blank and advertises the live global value as its placeholder,
  // so "blank = follows global" is legible at a glance.
  const overrideForForm = productOverrides[String(p.row)]
  const tunableInputs: Array<[string, keyof PricingParams]> = [
    ['prodInputPackaging', 'packaging'],
    ['prodInputTransport', 'transport'],
    ['prodInputDelivery', 'delivery'],
    ['prodInputCAC', 'cac'],
    ['prodInputMarginPct', 'targetMarginPct'],
  ]
  for (const [id, field] of tunableInputs) {
    const input = document.getElementById(id) as HTMLInputElement | null
    if (!input) continue
    const pinned = overrideForForm?.[field]
    input.value = pinned === undefined || pinned === null ? '' : String(pinned)
    input.placeholder = `Global: ${globalCostParams[field]}`
    input.classList.toggle('is-pinned', input.value !== '')
  }

  const discountInput = document.getElementById('prodInputDiscountVal') as HTMLInputElement | null
  const discountPinned = overrideForForm?.discountType !== undefined && overrideForForm?.discountVal !== undefined
  if (discountInput) {
    discountInput.value = discountPinned ? String(overrideForForm?.discountVal) : ''
    discountInput.placeholder = `Global: ${globalCostParams.discountVal}${globalCostParams.discountType === 'pct' ? '%' : ' BDT'}`
    discountInput.classList.toggle('is-pinned', discountPinned)
  }

  setProductDiscountType(discountPinned ? (overrideForForm?.discountType ?? 'pct') : 'global')

  const productTuneStatus = document.getElementById('productTuneStatus')
  if (productTuneStatus) {
    productTuneStatus.textContent = ''
    productTuneStatus.className = 'status-message'
  }

  updateProdTuneSummary()
  switchDetailTab('overview')
  productModal?.showModal()
}

function switchDetailTab(tab: 'overview' | 'tune') {
  const tabOverviewBtn = document.getElementById('tabOverviewBtn')
  const tabTuneBtn = document.getElementById('tabTuneBtn')
  const tabOverviewContent = document.getElementById('tabOverviewContent')
  const tabTuneContent = document.getElementById('tabTuneContent')

  tabOverviewBtn?.classList.toggle('active', tab === 'overview')
  tabOverviewBtn?.setAttribute('aria-selected', String(tab === 'overview'))
  if (tabOverviewBtn instanceof HTMLElement) tabOverviewBtn.tabIndex = tab === 'overview' ? 0 : -1
  tabTuneBtn?.classList.toggle('active', tab === 'tune')
  tabTuneBtn?.setAttribute('aria-selected', String(tab === 'tune'))
  if (tabTuneBtn instanceof HTMLElement) tabTuneBtn.tabIndex = tab === 'tune' ? 0 : -1

  if (tabOverviewContent) tabOverviewContent.style.display = tab === 'overview' ? 'grid' : 'none'
  if (tabTuneContent) tabTuneContent.style.display = tab === 'tune' ? 'grid' : 'none'
}

function setGlobalDiscountType(type: 'pct' | 'amt'): void {
  currentGlobalDiscountType = type
  const pct = document.getElementById('btnTypePct')
  const amt = document.getElementById('btnTypeAmt')
  const hint = document.getElementById('discountHint')
  pct?.classList.toggle('active', type === 'pct')
  pct?.setAttribute('aria-checked', String(type === 'pct'))
  amt?.classList.toggle('active', type === 'amt')
  amt?.setAttribute('aria-checked', String(type === 'amt'))
  if (hint) hint.textContent = type === 'pct' ? 'Promotional discount percentage' : 'Fixed promotional discount in BDT'
  const input = document.getElementById('inputDiscountVal') as HTMLInputElement | null
  if (input) {
    input.max = type === 'pct' ? '100' : '1000000'
  }
  updateEngineSummary()
}

function setProductDiscountType(type: 'global' | 'pct' | 'amt'): void {
  currentProdDiscountType = type
  const global = document.getElementById('prodBtnTypeGlobal')
  const pct = document.getElementById('prodBtnTypePct')
  const amt = document.getElementById('prodBtnTypeAmt')
  global?.classList.toggle('active', type === 'global')
  global?.setAttribute('aria-checked', String(type === 'global'))
  pct?.classList.toggle('active', type === 'pct')
  pct?.setAttribute('aria-checked', String(type === 'pct'))
  amt?.classList.toggle('active', type === 'amt')
  amt?.setAttribute('aria-checked', String(type === 'amt'))

  // Inheriting the global discount means there is no per-SKU value to type.
  const input = document.getElementById('prodInputDiscountVal') as HTMLInputElement | null
  if (input) {
    input.disabled = type === 'global'
    if (type === 'global') {
      input.value = ''
      input.removeAttribute('max')
      input.classList.remove('is-pinned')
      input.placeholder = `Global: ${globalCostParams.discountVal}${globalCostParams.discountType === 'pct' ? '%' : ' BDT'}`
    } else if (type === 'pct') {
      input.max = '100'
      input.placeholder = 'Discount % (0-100)'
    } else {
      input.max = '1000000'
      input.placeholder = 'Discount in BDT'
    }
  }
  updateProdTuneSummary()
}

/**
 * Read the tune form as a sparse override: blank input = inherit global.
 */
function readTuneForm(): PricingOverride {
  const numeric = (id: string): number | undefined => {
    const input = document.getElementById(id) as HTMLInputElement | null
    const raw = input?.value.trim()
    if (!raw) return undefined
    const parsed = Number(raw)
    return Number.isFinite(parsed) ? parsed : undefined
  }

  const override: PricingOverride = {}
  const packaging = numeric('prodInputPackaging')
  const transport = numeric('prodInputTransport')
  const delivery = numeric('prodInputDelivery')
  const cac = numeric('prodInputCAC')
  const margin = numeric('prodInputMarginPct')
  if (packaging !== undefined) override.packaging = packaging
  if (transport !== undefined) override.transport = transport
  if (delivery !== undefined) override.delivery = delivery
  if (cac !== undefined) override.cac = cac
  if (margin !== undefined) override.targetMarginPct = margin

  // Discount pins as a pair, and only when a concrete mode is selected.
  if (currentProdDiscountType !== 'global') {
    const discountVal = numeric('prodInputDiscountVal') ?? 0
    override.discountType = currentProdDiscountType
    override.discountVal = discountVal
  }
  return override
}

function updateProdTuneSummary() {
  if (!activeProductDetail) return
  const mfg = Number(activeProductDetail.manufactured_price)
  const override = readTuneForm()
  const resolved = resolvePricingParams(globalCostParams, override)

  const pinnedLabels = [...new Set(overriddenFields(override).map((field) => FIELD_LABELS[field] ?? field))]
  const pinnedEl = document.getElementById('prodSummaryPinned')
  if (pinnedEl) pinnedEl.textContent = pinnedLabels.length ? pinnedLabels.join(', ') : 'Nothing — follows global'

  const globalPrice = calculateSellingPrice(mfg, globalCostParams)
  const globalEl = document.getElementById('prodSummaryGlobalPrice')
  if (globalEl) globalEl.textContent = globalPrice === null ? '—' : money.format(globalPrice)

  const summary = document.getElementById('prodSummarySelling')
  if (!summary) return
  const price = calculateSellingPrice(mfg, resolved)
  summary.textContent = price === null ? 'Invalid margin' : money.format(price)
}

function updateEngineSummary() {
  const params: PricingParams = {
    packaging: Number((document.getElementById('inputPackaging') as HTMLInputElement | null)?.value) || 0,
    transport: Number((document.getElementById('inputTransport') as HTMLInputElement | null)?.value) || 0,
    delivery: Number((document.getElementById('inputDelivery') as HTMLInputElement | null)?.value) || 0,
    cac: Number((document.getElementById('inputCAC') as HTMLInputElement | null)?.value) || 0,
    targetMarginPct: Number((document.getElementById('inputMarginPct') as HTMLInputElement | null)?.value) || 0,
    discountType: currentGlobalDiscountType,
    discountVal: Number((document.getElementById('inputDiscountVal') as HTMLInputElement | null)?.value) || 0,
  }
  const overhead = params.packaging + params.transport + params.delivery + params.cac
  const summaryOverhead = document.getElementById('summaryOverhead')
  if (summaryOverhead) summaryOverhead.textContent = money.format(overhead)
  const sample = calculateSellingPrice(1000, params)
  const summarySample = document.getElementById('summarySample')
  if (summarySample) summarySample.textContent = sample === null ? '—' : money.format(sample)
}

async function syncAuth() {
  try {
    const res = await fetch('/api/auth')
    if (res.ok) {
      const data = await res.json() as AuthStatusResponse
      isAdminAuthenticated = data.authenticated
      authConfigured = data.configured
    }
  } catch {
    // Treat an unreachable auth endpoint as logged-out: the UI stays read-only.
  }
  updateAdminUI()
}

// The page decides which book it shows; the API call follows the route.
const pageOrigin = window.location.pathname.startsWith('/imported') ? 'imported' : 'local'

async function syncData() {
  const messages: string[] = []
  try {
    const [pRes, eRes] = await Promise.allSettled([
      fetch(`/api/products?origin=${pageOrigin}`),
      fetch('/api/engine'),
    ])

    if (pRes.status === 'fulfilled' && pRes.value.ok) {
      try {
        const data = await pRes.value.json() as CatalogPayload
        if (data.success && Array.isArray(data.products)) {
          products = data.products
          productsByRow = new Map(products.map((product) => [product.row, product]))
          sources = data.source_columns
          catalogLoaded = true
          if (productTotal) productTotal.textContent = products.length.toLocaleString()
          if (listingTotal) listingTotal.textContent = data.listing_count.toLocaleString()

          if (brandFilter) {
            const currentBrand = brandFilter.value
            const brands = [...new Set(products.map((p) => p.brand_name))].sort()
            brandFilter.innerHTML = '<option value="">All Brands</option>'
            brands.forEach((brand) => brandFilter.add(new Option(brand, brand)))
            brandFilter.value = currentBrand
          }

          if (sourceFilter) {
            const currentSource = sourceFilter.value
            sourceFilter.innerHTML = '<option value="">All Channels</option>'
            sources.forEach((source) => sourceFilter.add(new Option(source, source)))
            sourceFilter.value = currentSource
          }

          // Local SKUs carry no category, so the control stays hidden on that book.
          const categoryField = document.getElementById('categoryField')
          if (categoryFilter) {
            const currentCategory = categoryFilter.value
            const categories = data.categories ?? []
            categoryFilter.innerHTML = '<option value="">All Categories</option>'
            categories.forEach((category) => categoryFilter.add(new Option(category, category)))
            categoryFilter.value = currentCategory
            const isHidden = categories.length === 0
            categoryFilter.hidden = isHidden
            if (categoryField) categoryField.hidden = isHidden
          }
        } else {
          messages.push('Catalog data is unavailable or invalid.')
        }
      } catch {
        messages.push('Catalog data could not be decoded.')
      }
    } else {
      messages.push('Catalog data could not be loaded.')
    }

    if (eRes.status === 'fulfilled' && eRes.value.ok) {
      try {
        const eData = await eRes.value.json() as EngineResponse
        if (eData.success && eData.globalParams) {
          globalCostParams = { ...globalCostParams, ...eData.globalParams }
          productOverrides = eData.overrides || {}
          pricingLoaded = true
        } else {
          messages.push('Pricing settings are unavailable; selling prices are hidden.')
        }
      } catch {
        messages.push('Pricing settings could not be decoded; selling prices are hidden.')
      }
    } else {
      messages.push('Pricing settings could not be loaded; selling prices are hidden.')
    }

    liveSyncDot?.classList.toggle('synced', catalogLoaded && pricingLoaded)
  } catch (err) {
    console.error('Data synchronization failed', err)
    messages.push('Live data synchronization failed.')
  } finally {
    if (syncError) {
      syncError.textContent = messages.join(' ')
      syncError.hidden = messages.length === 0
    }
    if (catalogLoaded) {
      render()
    } else if (bodyElement) {
      bodyElement.innerHTML = '<tr><td colspan="5" class="empty-state">Unable to load the live catalog. Please refresh to retry.</td></tr>'
    }
    matrixViewport?.setAttribute('aria-busy', 'false')
  }
}

// Warm the other book once this one is painted, so switching origin is served
// from cache. Best-effort: a failed prefetch costs nothing but a cache miss.
function prefetchOtherOrigin() {
  const other = pageOrigin === 'imported' ? 'local' : 'imported'
  void fetch(`/api/products?origin=${other}`).catch(() => {})
}

// Attach event listeners on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  syncAuth()
  syncData()
  if ('requestIdleCallback' in window) {
    (window as any).requestIdleCallback(prefetchOtherOrigin, { timeout: 3000 })
  } else {
    setTimeout(prefetchOtherOrigin, 1200)
  }

  // Typing rebuilds every visible cell, so coalesce keystrokes into one paint.
  searchInput?.addEventListener('input', debouncedRender)
  brandFilter?.addEventListener('change', render)
  sourceFilter?.addEventListener('change', render)
  categoryFilter?.addEventListener('change', render)
  sortSelect?.addEventListener('change', render)
  headerRow?.querySelectorAll<HTMLButtonElement>('button[data-sort]').forEach((button) => {
    button.addEventListener('click', () => {
      if (!sortSelect) return
      const key = button.dataset.sort
      if (!key || !(key in PINNED_SORT_VALUES)) return
      sortSelect.value = nextPinnedSort(sortSelect.value, key as keyof typeof PINNED_SORT_VALUES)
      render()
    })
  })

  toggleSellingChipBtn?.addEventListener('click', () => {
    sellingChipMode = sellingChipMode === 'markup' ? 'discount' : 'markup'
    updateSellingChipToggleUI()
    render()
  })

  // Table row click
  bodyElement?.addEventListener('click', (e) => {
    const target = e.target as HTMLElement | null
    const row = target?.closest('tr[data-row-id]') as HTMLElement | null
    if (row && !target?.closest('a')) {
      const found = productsByRow.get(Number(row.dataset.rowId))
      if (found) openDetail(found)
    }
  })

  bodyElement?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      const target = e.target as HTMLElement | null
      if (target?.closest('a, button, input, select, textarea')) return
      const row = target?.closest('tr[data-row-id]') as HTMLElement | null
      if (row) {
        e.preventDefault()
        const found = productsByRow.get(Number(row.dataset.rowId))
        if (found) openDetail(found)
      }
    }
  })

  // Modals close buttons
  document.getElementById('close')?.addEventListener('click', () => productModal?.close())
  document.getElementById('closeEngineModal')?.addEventListener('click', () => engineModal?.close())
  document.getElementById('closeAuthModal')?.addEventListener('click', () => authModal?.close())

  // Tab switching inside product modal
  document.getElementById('tabOverviewBtn')?.addEventListener('click', () => switchDetailTab('overview'))
  document.getElementById('tabTuneBtn')?.addEventListener('click', () => switchDetailTab('tune'))
  document.querySelector('.tab-nav')?.addEventListener('keydown', (event) => {
    if (!(event instanceof KeyboardEvent) || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    const tabs = [
      document.getElementById('tabOverviewBtn'),
      document.getElementById('tabTuneBtn'),
    ].filter((tab): tab is HTMLElement => tab instanceof HTMLElement)
    if (!tabs.length) return
    const currentIndex = tabs.indexOf(document.activeElement as HTMLElement)
    let nextIndex = currentIndex
    if (event.key === 'Home') nextIndex = 0
    if (event.key === 'End') nextIndex = tabs.length - 1
    if (event.key === 'ArrowRight') nextIndex = (Math.max(currentIndex, 0) + 1) % tabs.length
    if (event.key === 'ArrowLeft') nextIndex = (currentIndex <= 0 ? tabs.length : currentIndex) - 1
    event.preventDefault()
    const nextTab = tabs[nextIndex]
    switchDetailTab(nextTab?.id === 'tabTuneBtn' ? 'tune' : 'overview')
    nextTab?.focus()
  })
  document.getElementById('btnTypePct')?.addEventListener('click', () => setGlobalDiscountType('pct'))
  document.getElementById('btnTypeAmt')?.addEventListener('click', () => setGlobalDiscountType('amt'))
  document.getElementById('prodBtnTypeGlobal')?.addEventListener('click', () => setProductDiscountType('global'))
  document.getElementById('prodBtnTypePct')?.addEventListener('click', () => setProductDiscountType('pct'))
  document.getElementById('prodBtnTypeAmt')?.addEventListener('click', () => setProductDiscountType('amt'))

  for (const id of ENGINE_INPUT_IDS) {
    document.getElementById(id)?.addEventListener('input', updateEngineSummary)
  }
  for (const id of PRODUCT_INPUT_IDS) {
    document.getElementById(id)?.addEventListener('input', (event) => {
      // Mark the field as pinned the moment it holds a value, so operators can
      // see at a glance which knobs have left the global engine.
      const input = event.currentTarget as HTMLInputElement | null
      input?.classList.toggle('is-pinned', !!input.value.trim())
      updateProdTuneSummary()
    })
  }

  // Engine open
  openEngineBtn?.addEventListener('click', () => {
    const engineStatus = document.getElementById('engineStatus')
    if (engineStatus) {
      engineStatus.textContent = ''
      engineStatus.className = 'status-message'
    }
    const inputs: Record<string, number> = {
      inputPackaging: globalCostParams.packaging,
      inputTransport: globalCostParams.transport,
      inputDelivery: globalCostParams.delivery,
      inputCAC: globalCostParams.cac,
      inputMarginPct: globalCostParams.targetMarginPct,
      inputDiscountVal: globalCostParams.discountVal,
    }
    Object.entries(inputs).forEach(([id, val]) => {
      const input = document.getElementById(id) as HTMLInputElement | null
      if (input) input.value = String(val)
    })
    setGlobalDiscountType(globalCostParams.discountType)
    updateEngineSummary()
    engineModal?.showModal()
  })

  // Admin login button
  adminLoginBtn?.addEventListener('click', async () => {
    if (isAdminAuthenticated) {
      // Logout
      await fetch('/api/auth', { method: 'DELETE', headers: { 'X-Price-Matrix-Admin': '1' } })
      isAdminAuthenticated = false
      updateAdminUI()
    } else {
      authModal?.showModal()
    }
  })

  // Admin login form submit
  document.getElementById('authForm')?.addEventListener('submit', async (e) => {
    e.preventDefault()
    const passwordInput = document.getElementById('adminPassword') as HTMLInputElement | null
    const authStatus = document.getElementById('authStatus')
    if (!passwordInput || !authStatus) return
    authStatus.textContent = 'Verifying…'
    authStatus.className = 'status-message'

    try {
      const res = await fetch('/api/auth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Price-Matrix-Admin': '1' },
        body: JSON.stringify({ password: passwordInput.value }),
      })
      const data = await res.json() as { success: boolean; error?: string }
      if (data.success) {
        isAdminAuthenticated = true
        updateAdminUI()
        authModal?.close()
        passwordInput.value = ''
        authStatus.textContent = ''
      } else {
        authStatus.textContent = data.error || 'Authentication failed'
        authStatus.className = 'status-message error'
      }
    } catch {
      authStatus.textContent = 'Network error'
      authStatus.className = 'status-message error'
    }
  })

  // Global Engine form submit
  document.getElementById('engineForm')?.addEventListener('submit', async (e) => {
    e.preventDefault()
    const engineStatus = document.getElementById('engineStatus')
    if (engineStatus) {
      engineStatus.textContent = 'Saving…'
      engineStatus.className = 'status-message'
    }

    const payload: PricingParams = {
      packaging: Number((document.getElementById('inputPackaging') as HTMLInputElement).value) || 0,
      transport: Number((document.getElementById('inputTransport') as HTMLInputElement).value) || 0,
      delivery: Number((document.getElementById('inputDelivery') as HTMLInputElement).value) || 0,
      cac: Number((document.getElementById('inputCAC') as HTMLInputElement).value) || 0,
      targetMarginPct: Number((document.getElementById('inputMarginPct') as HTMLInputElement).value) || 0,
      discountType: currentGlobalDiscountType,
      discountVal: Number((document.getElementById('inputDiscountVal') as HTMLInputElement).value) || 0,
    }

    try {
      const res = await fetch('/api/engine', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Price-Matrix-Admin': '1' },
        body: JSON.stringify(payload),
      })
      const data = await res.json() as { success: boolean; error?: string }
      if (data.success) {
        globalCostParams = { ...payload }
        engineModal?.close()
        render()
      } else if (engineStatus) {
        engineStatus.textContent = parseApiError(data, 'Save failed')
        engineStatus.className = 'status-message error'
      }
    } catch {
      if (engineStatus) {
        engineStatus.textContent = 'Network error'
        engineStatus.className = 'status-message error'
      }
    }
  })

  // Reset all overrides
  document.getElementById('resetCustomOverridesBtn')?.addEventListener('click', async () => {
    const tuned = Object.keys(productOverrides).length
    const engineStatus = document.getElementById('engineStatus')
    if (!tuned) {
      if (engineStatus) {
        engineStatus.textContent = 'No custom SKU tunes to reset.'
        engineStatus.className = 'status-message'
      }
      return
    }
    // Irreversible and catalog-wide, so make the operator name the scale of it.
    const answer = prompt(
      `This deletes ${tuned} custom SKU tune${tuned === 1 ? '' : 's'} and cannot be undone.\n\nType RESET to confirm:`,
    )
    if (answer?.trim().toUpperCase() !== 'RESET') return
    try {
      const res = await fetch('/api/overrides?all=true', {
        method: 'DELETE',
        headers: { 'X-Price-Matrix-Admin': '1' },
      })
      if (res.ok) {
        productOverrides = {}
        render()
        if (engineStatus) {
          engineStatus.textContent = `Reset ${tuned} SKU tune${tuned === 1 ? '' : 's'}.`
          engineStatus.className = 'status-message'
        }
      } else if (engineStatus) {
        const data = await res.json().catch(() => ({})) as unknown
        engineStatus.textContent = parseApiError(data, 'Reset failed')
        engineStatus.className = 'status-message error'
      }
    } catch {
      if (engineStatus) {
        engineStatus.textContent = 'Network error'
        engineStatus.className = 'status-message error'
      }
    }
  })

  // Product Tune form submit
  document.getElementById('tabTuneContent')?.addEventListener('submit', async (e) => {
    e.preventDefault()
    if (!activeProductDetail) return
    const status = document.getElementById('productTuneStatus')
    if (status) {
      status.textContent = 'Saving…'
      status.className = 'status-message'
    }

    const rowId = activeProductDetail.row
    const override = readTuneForm()

    try {
      const res = await fetch('/api/overrides', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Price-Matrix-Admin': '1' },
        body: JSON.stringify({ productRowId: rowId, override }),
      })
      const data = await res.json() as {
        success: boolean
        error?: string
        override?: StoredPricingOverride | null
      }
      if (data.success) {
        // The worker strips fields that merely echo global, so trust its
        // response rather than the raw form: an all-inherit save clears the row.
        if (data.override) {
          productOverrides[String(rowId)] = data.override
        } else {
          delete productOverrides[String(rowId)]
        }
        productModal?.close()
        render()
      } else if (status) {
        status.textContent = parseApiError(data, 'Save failed')
        status.className = 'status-message error'
      }
    } catch {
      if (status) {
        status.textContent = 'Network error'
        status.className = 'status-message error'
      }
    }
  })

  // Clear single product override
  document.getElementById('clearProductCustomEngineBtn')?.addEventListener('click', async () => {
    if (!activeProductDetail) return
    const rowId = activeProductDetail.row
    const status = document.getElementById('productTuneStatus')
    if (status) {
      status.textContent = 'Resetting…'
      status.className = 'status-message'
    }
    try {
      const res = await fetch(`/api/overrides?productRowId=${rowId}`, {
        method: 'DELETE',
        headers: { 'X-Price-Matrix-Admin': '1' },
      })
      if (res.ok) {
        delete productOverrides[String(rowId)]
        productModal?.close()
        render()
      } else {
        const data = await res.json().catch(() => ({})) as unknown
        if (status) {
          status.textContent = parseApiError(data, 'Reset failed')
          status.className = 'status-message error'
        }
      }
    } catch {
      if (status) {
        status.textContent = 'Network error'
        status.className = 'status-message error'
      }
    }
  })

  // Export JSON
  document.getElementById('download')?.addEventListener('click', () => {
    const exportData = {
      origin: pageOrigin,
      generated_at: new Date().toISOString(),
      global_cost_parameters: globalCostParams,
      product_custom_overrides: productOverrides,
      products: products.map((p) => ({
        ...p,
        pricing_parameters: getProductParams(p.row),
        pinned_parameters: overriddenFields(productOverrides[String(p.row)]),
        calculated_selling_price: computeSellingPrice(p.manufactured_price, p.row),
      })),
    }
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `product_pricing_data_${pageOrigin}.json`
    anchor.click()
    URL.revokeObjectURL(url)
  })
})
