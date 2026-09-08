const SortMark = () => (
  <svg class="sort-mark" aria-hidden="true" viewBox="0 0 9 11" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
    <path d="M4.5 1.4v8.2M2 3.9 4.5 1.4 7 3.9M2 7.1l2.5 2.5L7 7.1" />
  </svg>
)

/**
 * Column head: a small-caps label over the basis line that says what the
 * number underneath is measured against. Operators shouldn't have to hover a
 * tooltip to learn whether a percentage is off cost or off MRP.
 */
const SortHeader = (
  { className, sort, children, basis, title }:
  { className: string; sort: string; children: string; basis: string; title: string },
) => (
  <th class={className} aria-sort="none">
    <button type="button" class="sort-button" data-sort={sort} title={title}>
      <span class="head-label">{children}<SortMark /></span>
      <span class="head-basis">{basis}</span>
    </button>
  </th>
)

export function PriceMatrix() {
  return (
    <main class="table-viewport" aria-busy="true" id="matrixViewport">
      <div id="syncError" class="sync-error" role="alert" hidden></div>
      <div id="aboveMarketBanner" class="above-market-banner" role="status" aria-live="polite" hidden></div>
      <table>
        <thead><tr id="headerRow">
          <SortHeader className="col-row" sort="excelrow" basis="Sheet · row" title="Sort by the workbook row this figure was read from">Row</SortHeader>
          <SortHeader className="col-product" sort="product" basis="Title / pack size" title="Sort by product title">Product</SortHeader>
          <SortHeader className="col-brand" sort="brand" basis="Manufacturer" title="Sort by brand">Brand</SortHeader>
          <SortHeader className="col-mfg" sort="mfg" basis="BDT / unit" title="Sort by the price we pay to acquire one unit">Source cost</SortHeader>
          <SortHeader className="col-market" sort="market" basis="BDT · vs cost" title="Sort by official MRP or third-party benchmark">MRP</SortHeader>
          <SortHeader className="col-selling-price" sort="selling" basis="BDT · engine output" title="Sort by configured selling price">Selling price</SortHeader>
        </tr></thead>
        <tbody id="body"><tr><td colspan={6} class="empty-state">Loading live catalog…</td></tr></tbody>
      </table>
      <div id="empty" class="empty-state" hidden>No products match the selected criteria.</div>
    </main>
  )
}
