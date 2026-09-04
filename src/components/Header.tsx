import type { DashboardMeta } from '../types'
import { CompareIcon, DownloadIcon, LockIcon, SearchIcon, SlidersIcon } from './icons'
import { OriginSwitch } from './OriginSwitch'

/**
 * Two ruled tiers.
 *
 * Register (top): who this is, how much is on the sheet, which book is open,
 * how many specimens are out of spec, and the write actions.
 * Instrument (bottom): the controls that decide what the sheet shows and how
 * its measurements are read.
 */
export function Header({ meta }: { meta: DashboardMeta }) {
  return (
    <header class="app-header">
      <div class="header-register">
        <div class="header-left">
          <div class="brand-title">
            <span class="brand-dot" id="liveSyncDot" title="Loading authoritative D1 data"></span>
            Price Matrix
          </div>
          <div class="divider-v"></div>
          <div class="header-meta-pill">
            <strong id="productTotal">{meta.productCount}</strong> SKUs
            <span class="meta-sep" aria-hidden="true">/</span>
            <strong id="listingTotal">{meta.listingCount}</strong> listings
          </div>
        </div>

        <div class="header-right">
          <OriginSwitch meta={meta} />

          <button
            class="spec-flag"
            id="aboveMarketFilterBtn"
            type="button"
            aria-pressed="false"
            aria-label="Show only SKUs priced above their market reference"
            title="Show only SKUs priced above their market reference"
            hidden
          >
            <span class="spec-flag-mark" aria-hidden="true"></span>
            <span aria-hidden="true">
              <span class="spec-flag-verb" id="aboveMarketVerb">Show</span>{' '}
              <span class="spec-flag-count" id="aboveMarketCount">0</span>{' '}
              above market
            </span>
          </button>

          <button class="btn-register" id="adminLoginBtn" type="button" hidden>
            <LockIcon />
            <span>Admin login</span>
          </button>
          <button
            class="btn-register"
            id="download"
            type="button"
            aria-label="Export dataset as JSON"
            title="Export dataset (JSON)"
          >
            <DownloadIcon />
            <span>Export</span>
          </button>
          <button class="btn-register is-primary" id="openEngineBtn" type="button">
            <SlidersIcon />
            <span>Pricing engine</span>
          </button>
        </div>
      </div>

      <div class="header-instrument">
        <div class="header-center">
          <div class="search-field">
            <label class="sr-only" for="search">Search products or brands</label>
            <SearchIcon />
            <input id="search" type="search" placeholder="Search product or brand…" autocomplete="off" />
          </div>
          <div class="select-field">
            <label class="sr-only" for="brandFilter">Filter by brand</label>
            <select id="brandFilter"><option value="">All brands</option>{meta.brands.map((brand) => <option value={brand}>{brand}</option>)}</select>
          </div>
          <div class="select-field">
            <label class="sr-only" for="sourceFilter">Filter by marketplace</label>
            <select id="sourceFilter"><option value="">All channels</option>{meta.channels.map((channel) => <option value={channel}>{channel}</option>)}</select>
          </div>
          <div class="select-field" id="categoryField" hidden={meta.categories.length === 0}>
            <label class="sr-only" for="categoryFilter">Filter by category</label>
            <select id="categoryFilter">
              <option value="">All categories</option>
              {meta.categories.map((category) => <option value={category}>{category}</option>)}
            </select>
          </div>
          <div class="select-field">
            <label class="sr-only" for="sort">Sort products</label>
            <select id="sort">
              <option value="product">Product A–Z</option><option value="productDesc">Product Z–A</option>
              <option value="brand">Brand A–Z</option><option value="brandDesc">Brand Z–A</option>
              <option value="sellingAsc">Selling: Low → High</option><option value="sellingDesc">Selling: High → Low</option>
              <option value="mfgAsc">Source Cost: Low → High</option><option value="mfgDesc">Source Cost: High → Low</option>
              <option value="marketAsc">MRP: Low → High</option><option value="marketDesc">MRP: High → Low</option>
              <option value="coverage">Most Channels</option><option value="spread">Largest Spread</option>
            </select>
          </div>
        </div>

        <button
          class="btn-toggle-view"
          id="toggleSellingChipModeBtn"
          type="button"
          aria-pressed="false"
          aria-label="Show market discount percentage"
          title="Switch every chip between markup over source cost and discount off MRP"
        >
          <CompareIcon />
          <span id="sellingChipBtnLabel">Read as market discount</span>
        </button>
      </div>
    </header>
  )
}
