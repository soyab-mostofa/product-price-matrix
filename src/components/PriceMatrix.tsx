const SortHeader = ({ className, sort, children, title }: { className: string; sort: string; children: string; title: string }) => (
  <th class={className} aria-sort="none">
    <button type="button" class="sort-button" data-sort={sort} title={title}>{children} ↕</button>
  </th>
)

export function PriceMatrix() {
  return (
    <main class="table-viewport" aria-busy="true" id="matrixViewport">
      <div id="syncError" class="sync-error" role="alert" hidden></div>
      <div id="aboveMarketBanner" class="above-market-banner" role="status" aria-live="polite" hidden></div>
      <table>
        <thead><tr id="headerRow">
          <SortHeader className="col-product" sort="product" title="Sort by product title">Product Name</SortHeader>
          <SortHeader className="col-brand" sort="brand" title="Sort by brand">Brand</SortHeader>
          <SortHeader className="col-mfg" sort="mfg" title="Sort by the price we pay to acquire one unit">Source Cost</SortHeader>
          <SortHeader className="col-market" sort="market" title="Sort by official MRP or third-party benchmark">MRP</SortHeader>
          <SortHeader className="col-selling-price" sort="selling" title="Sort by configured selling price">Selling Price</SortHeader>
        </tr></thead>
        <tbody id="body"><tr><td colspan={5} class="empty-state">Loading live catalog…</td></tr></tbody>
      </table>
      <div id="empty" class="empty-state" hidden>No products match the selected criteria.</div>
    </main>
  )
}
