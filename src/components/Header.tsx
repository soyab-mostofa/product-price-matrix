import type { DashboardMeta } from '../types'

const SearchIcon = () => (
  <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line>
  </svg>
)

export function Header({ meta }: { meta: DashboardMeta }) {
  return (
    <header class="app-header">
      <div class="header-left">
        <div class="brand-title"><span class="brand-dot" id="liveSyncDot" title="Loading authoritative D1 data"></span>Price Matrix</div>
        <div class="divider-v"></div>
        <div class="header-meta-pill"><strong id="productTotal">{meta.productCount}</strong> SKUs · <strong id="listingTotal">{meta.listingCount}</strong> Active Listings</div>
      </div>

      <div class="header-center">
        <div class="search-field">
          <label class="sr-only" for="search">Search products or brands</label>
          <SearchIcon />
          <input id="search" type="search" placeholder="Search product or brand..." autocomplete="off" />
        </div>
        <div class="select-field">
          <label class="sr-only" for="brandFilter">Filter by brand</label>
          <select id="brandFilter"><option value="">All Brands</option>{meta.brands.map((brand) => <option value={brand}>{brand}</option>)}</select>
        </div>
        <div class="select-field">
          <label class="sr-only" for="sourceFilter">Filter by marketplace</label>
          <select id="sourceFilter"><option value="">All Channels</option>{meta.channels.map((channel) => <option value={channel}>{channel}</option>)}</select>
        </div>
        <div class="select-field" id="categoryField" hidden={meta.categories.length === 0}>
          <label class="sr-only" for="categoryFilter">Filter by category</label>
          <select id="categoryFilter">
            <option value="">All Categories</option>
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

      <div class="header-right">
        <button class="btn-toggle-view" id="toggleSellingChipModeBtn" type="button" aria-pressed="false" aria-label="Show market discount percentage" title="Toggle selling-price comparison metric">
          <span id="sellingChipBtnLabel">View Market Discount %</span>
          <span class="selling-chip-btn-short" aria-hidden="true">Compare</span>
        </button>
        <button class="btn-admin" id="adminLoginBtn" type="button" hidden>Admin Login</button>
        <button class="btn-calc" id="openEngineBtn" type="button">Pricing Engine</button>
        <button class="btn-icon" id="download" type="button" aria-label="Export dataset as JSON" title="Export Dataset (JSON)">⇩</button>
      </div>
    </header>
  )
}
