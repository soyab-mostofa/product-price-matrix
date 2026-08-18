from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

ROOT = Path('/home/soyab/Downloads/product_pricing_visualization')
RESEARCH_PATH = ROOT / 'verified_marketplace_research.json'
JSON_PATH = ROOT / 'product_pricing_data.json'
HTML_PATH = ROOT / 'product_pricing_dashboard.html'
PUBLIC_DIR = ROOT / 'public'
PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

research = json.loads(RESEARCH_PATH.read_text(encoding='utf-8'))

products = []
for item in research['products']:
    products.append({
        'product_name': item['product_name'],
        'brand_name': item['brand_name'],
        'manufactured_price': item['excel_prices'].get('manufactured_price'),
        'market_average_price': item['excel_prices'].get('market_average_price'),
        'sources': item.get('sources', {}),
    })

output = {
    'currency': research['currency'],
    'currency_symbol': research['currency_symbol'],
    'source_excel': research['source_excel'],
    'internal_price_basis': research['internal_price_basis'],
    'matching_policy': research['matching_policy'],
    'generated_at': datetime.now(timezone.utc).isoformat(),
    'product_count': len(products),
    'brand_count': len({p['brand_name'] for p in products}),
    'source_columns': research['source_columns'],
    'source_listing_counts': research['source_listing_counts'],
    'coverage_counts': research['coverage_counts'],
    'products': products,
}

JSON_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
(PUBLIC_DIR / 'product_pricing_data.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
embedded = json.dumps(output, ensure_ascii=False, separators=(',', ':')).replace('</script>', '<\\/script>')

html = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Price Intelligence</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #fafafa;
  --surface: #ffffff;
  --text: #09090b;
  --text-secondary: #71717a;
  --text-tertiary: #a1a1aa;
  
  --border: #e4e4e7;
  --border-subtle: #f4f4f5;
  --border-active: #18181b;
  
  /* Refined Linear-style price accents */
  --price-high-bg: #fef2f2;
  --price-high-text: #dc2626;
  --price-high-dot: #ef4444;
  
  --price-second-bg: #fffbeb;
  --price-second-text: #d97706;
  --price-second-dot: #f59e0b;
  
  --price-low-bg: #f0fdf4;
  --price-low-text: #16a34a;
  --price-low-dot: #22c55e;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  letter-spacing: -0.011em;
  -webkit-font-smoothing: antialiased;
}

/* Linear/Vercel-style Top Navigation Bar */
header.navbar {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  height: 52px;
  padding: 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-shrink: 0;
  z-index: 50;
}

.nav-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.app-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  display: flex;
  align-items: center;
  gap: 8px;
}

.app-title svg {
  color: #18181b;
}

.divider-v {
  width: 1px;
  height: 16px;
  background: var(--border);
}

.meta-count {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}
.meta-count strong {
  color: var(--text);
  font-weight: 600;
}

/* Search & Filters */
.nav-center {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  max-width: 680px;
}

.search-input-wrap {
  position: relative;
  flex: 1.5;
}
.search-input-wrap svg {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  width: 14px;
  height: 14px;
  color: var(--text-tertiary);
  pointer-events: none;
}
.search-input {
  width: 100%;
  height: 32px;
  padding: 0 10px 0 30px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 12.5px;
  color: var(--text);
  font-family: inherit;
  outline: none;
  transition: all .15s ease;
}
.search-input:focus {
  background: #ffffff;
  border-color: var(--border-active);
  box-shadow: 0 0 0 1px var(--border-active);
}

.filter-select-wrap {
  position: relative;
  flex: 1;
}
.filter-select {
  width: 100%;
  height: 32px;
  padding: 0 24px 0 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text);
  font-family: inherit;
  outline: none;
  cursor: pointer;
  appearance: none;
  -webkit-appearance: none;
  transition: all .15s ease;
}
.filter-select:focus {
  background: #ffffff;
  border-color: var(--border-active);
}
.filter-select-wrap::after {
  content: '';
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  width: 0;
  height: 0;
  border-left: 3.5px solid transparent;
  border-right: 3.5px solid transparent;
  border-top: 4.5px solid var(--text-secondary);
  pointer-events: none;
}

.nav-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.legend-group {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 11.5px;
  color: var(--text-secondary);
  font-weight: 500;
}
.legend-tag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.indicator {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.indicator.high { background: var(--price-high-dot); }
.indicator.second { background: var(--price-second-dot); }
.indicator.low { background: var(--price-low-dot); }

.icon-btn {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all .15s ease;
}
.icon-btn:hover {
  background: var(--bg);
  color: var(--text);
  border-color: #d4d4d8;
}

/* Grid & Table */
.table-viewport {
  flex: 1;
  overflow: auto;
  position: relative;
  background: var(--surface);
}

table {
  border-collapse: separate;
  border-spacing: 0;
  width: max-content;
}

thead th {
  position: sticky;
  top: 0;
  z-index: 30;
  background: #fafafa;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  border-right: 1px solid var(--border-subtle);
  white-space: nowrap;
  user-select: none;
}

th.source-column-header {
  min-width: 175px;
  text-align: left;
}
.source-header-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.channel-type-badge {
  font-size: 9.5px;
  padding: 2px 5px;
  border-radius: 4px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}
.channel-type-badge.brand { background: #f4f4f5; color: #52525b; }
.channel-type-badge.market { background: #f4f4f5; color: #71717a; }

/* Sticky 4 Base Columns */
.col-product {
  position: sticky;
  left: 0;
  z-index: 20;
  width: 320px;
  min-width: 320px;
  max-width: 320px;
  background: #ffffff;
}
.col-brand {
  position: sticky;
  left: 320px;
  z-index: 20;
  width: 130px;
  min-width: 130px;
  max-width: 130px;
  background: #ffffff;
}
.col-mfg {
  position: sticky;
  left: 450px;
  z-index: 20;
  width: 135px;
  min-width: 135px;
  max-width: 135px;
  background: #ffffff;
  text-align: right;
}
.col-market {
  position: sticky;
  left: 585px;
  z-index: 20;
  width: 135px;
  min-width: 135px;
  max-width: 135px;
  background: #ffffff;
  text-align: right;
  border-right: 1px solid #d4d4d8 !important;
  box-shadow: 4px 0 8px rgba(0, 0, 0, 0.03);
}

thead th.col-product, thead th.col-brand, thead th.col-mfg, thead th.col-market {
  z-index: 35;
  background: #f4f4f5;
}

/* Rows & Cells */
tbody tr {
  cursor: pointer;
  transition: background-color 0.08s ease;
}
tbody tr:hover td {
  background-color: #f8fafc !important;
}

td {
  padding: 8px 14px;
  border-bottom: 1px solid var(--border-subtle);
  border-right: 1px solid var(--border-subtle);
  vertical-align: middle;
  height: 50px;
}

tbody tr:hover td.col-product,
tbody tr:hover td.col-brand,
tbody tr:hover td.col-mfg,
tbody tr:hover td.col-market {
  background-color: #f1f5f9 !important;
}

.item-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.brand-label {
  font-size: 11.5px;
  font-weight: 500;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 110px;
  display: block;
}

.price-text {
  font-size: 14.5px;
  font-weight: 600;
  color: #27272a;
  letter-spacing: -0.02em;
}
.price-text.mfg {
  color: #0284c7;
  font-weight: 700;
}

/* Marketplace Source Cells */
.source-data-cell {
  padding: 5px 8px;
  min-width: 175px;
}
.price-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 6px;
  background: transparent;
  transition: all .1s ease;
}
.price-card-val {
  font-size: 14.5px;
  font-weight: 600;
  color: #3f3f46;
  letter-spacing: -0.02em;
}

.open-link-btn {
  color: var(--text-tertiary);
  text-decoration: none;
  font-size: 11px;
  padding: 2px 4px;
  border-radius: 4px;
  transition: all .12s;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  opacity: 0.7;
}
.price-card:hover .open-link-btn {
  opacity: 1;
  color: var(--text);
}

/* Aesthetic Highlights */
.price-card.is-high {
  background: var(--price-high-bg);
}
.price-card.is-high .price-card-val {
  color: var(--price-high-text);
  font-weight: 700;
}

.price-card.is-second {
  background: var(--price-second-bg);
}
.price-card.is-second .price-card-val {
  color: var(--price-second-text);
  font-weight: 700;
}

.price-card.is-low {
  background: var(--price-low-bg);
}
.price-card.is-low .price-card-val {
  color: var(--price-low-text);
  font-weight: 700;
}

.empty-cell-dash {
  color: #d4d4d8;
  font-size: 13px;
  text-align: center;
  display: block;
}

/* Drawer / Dialog */
dialog {
  margin: auto;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: #ffffff;
  color: var(--text);
  width: min(600px, calc(100% - 32px));
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.08);
  outline: none;
}
dialog::backdrop {
  background: rgba(0, 0, 0, 0.25);
  backdrop-filter: blur(2px);
}
.drawer-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  background: #fafafa;
}
.drawer-brand {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--text-secondary);
}
.drawer-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  margin-top: 2px;
}
.drawer-close {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  font-size: 18px;
  cursor: pointer;
  padding: 4px;
}
.drawer-close:hover { color: var(--text); }
.drawer-body {
  padding: 20px;
  display: grid;
  gap: 16px;
  max-height: 70vh;
  overflow-y: auto;
}
.stats-summary-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  background: #fafafa;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid var(--border);
}
.stat-item span {
  display: block;
  font-size: 11px;
  color: var(--text-secondary);
  font-weight: 500;
}
.stat-item strong {
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
  margin-top: 2px;
  display: block;
}
.source-items-list {
  display: grid;
  gap: 6px;
}
.source-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  background: #ffffff;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.source-row a {
  color: #0284c7;
  text-decoration: none;
  font-size: 12px;
  font-weight: 500;
}
.source-row a:hover { text-decoration: underline; }

.empty-state-view {
  padding: 60px 20px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}
</style>
</head>
<body>

<header class="navbar">
  <div class="nav-left">
    <div class="app-title">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
      Price Intelligence
    </div>
    <div class="divider-v"></div>
    <div class="meta-count"><strong id="productTotal">0</strong> products · <strong id="listingTotal">0</strong> listings</div>
  </div>

  <div class="nav-center">
    <div class="search-input-wrap">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
      <input id="search" class="search-input" type="search" placeholder="Search by product or brand..." autofocus>
    </div>
    
    <div class="filter-select-wrap">
      <select id="brandFilter" class="filter-select"><option value="">All Brands</option></select>
    </div>
    
    <div class="filter-select-wrap">
      <select id="sourceFilter" class="filter-select"><option value="">All Channels</option></select>
    </div>
    
    <div class="filter-select-wrap">
      <select id="sort" class="filter-select">
        <option value="product">Product A–Z</option>
        <option value="mfgAsc">MFG: Low to High</option>
        <option value="mfgDesc">MFG: High to Low</option>
        <option value="coverage">Most Channels</option>
        <option value="spread">Largest Spread</option>
      </select>
    </div>
  </div>

  <div class="nav-right">
    <div class="legend-group">
      <span class="legend-tag"><span class="indicator high"></span> High</span>
      <span class="legend-tag"><span class="indicator second"></span> 2nd</span>
      <span class="legend-tag"><span class="indicator low"></span> Low</span>
    </div>
    <button class="icon-btn" id="download" title="Export Dataset (JSON)">
      <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"></path></svg>
    </button>
  </div>
</header>

<main class="table-viewport">
  <table>
    <thead>
      <tr id="headerRow">
        <th class="col-product">Product Name</th>
        <th class="col-brand">Brand</th>
        <th class="col-mfg">MFG Price</th>
        <th class="col-market">Market Avg</th>
      </tr>
    </thead>
    <tbody id="body"></tbody>
  </table>
  <div id="empty" class="empty-state-view" hidden>No products found matching the current search criteria.</div>
</main>

<dialog id="dialog">
  <div class="drawer-header">
    <div>
      <div class="drawer-brand" id="dialogBrand"></div>
      <div class="drawer-title" id="dialogName"></div>
    </div>
    <button class="drawer-close" id="close" aria-label="Close">✕</button>
  </div>
  <div class="drawer-body" id="detail"></div>
</dialog>

<script id="data" type="application/json">__DATA__</script>
<script>
const data = JSON.parse(document.getElementById('data').textContent);
const products = data.products;
const sources = data.source_columns;
const money = new Intl.NumberFormat('en-BD', { style: 'currency', currency: 'BDT', minimumFractionDigits: 0, maximumFractionDigits: 2 });
const esc = v => String(v ?? '').replace(/[&<>'"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));

const search = document.getElementById('search');
const brandFilter = document.getElementById('brandFilter');
const sourceFilter = document.getElementById('sourceFilter');
const sort = document.getElementById('sort');
const body = document.getElementById('body');
const empty = document.getElementById('empty');
const headerRow = document.getElementById('headerRow');

document.getElementById('productTotal').textContent = data.product_count.toLocaleString();
const listingTotal = Object.values(data.source_listing_counts).reduce((a, b) => a + b, 0);
document.getElementById('listingTotal').textContent = listingTotal.toLocaleString();

[...new Set(products.map(p => p.brand_name))].sort().forEach(v => brandFilter.add(new Option(v, v)));
sources.forEach(v => sourceFilter.add(new Option(v, v)));

function getVisibleSources(list) {
  if (!list.length) return [];
  return sources.filter(s => list.some(p => p.sources[s]?.price !== undefined && p.sources[s]?.price !== null));
}

function updateHeaders(activeSources) {
  headerRow.querySelectorAll('th.source-column-header').forEach(el => el.remove());
  
  activeSources.forEach(source => {
    const th = document.createElement('th');
    const official = /official/i.test(source);
    th.className = 'source-column-header';
    th.innerHTML = `
      <div class="source-header-content">
        <span>${esc(source)}</span>
        <span class="channel-type-badge ${official ? 'brand' : 'market'}">${official ? 'Official' : 'Mkt'}</span>
      </div>
    `;
    headerRow.appendChild(th);
  });
}

function externalValues(p, activeSources) {
  const sList = activeSources || sources;
  return sList.map(s => p.sources[s]?.price).filter(v => v !== undefined && v !== null).map(Number);
}

function spread(p) {
  const v = sources.map(s => p.sources[s]?.price).filter(v => v !== undefined && v !== null).map(Number);
  return v.length > 1 ? Math.max(...v) - Math.min(...v) : 0;
}

function sourceCell(p, source, activeSources) {
  const listing = p.sources[source];
  if (!listing) return '<td class="source-data-cell"><span class="empty-cell-dash">—</span></td>';
  
  const vals = externalValues(p, activeSources), price = Number(listing.price);
  const sortedUniqueDesc = [...new Set(vals)].sort((a, b) => b - a);
  let rankClass = '';
  
  if (sortedUniqueDesc.length > 1) {
    if (price === sortedUniqueDesc[0]) rankClass = 'is-high';
    else if (price === sortedUniqueDesc[1]) rankClass = 'is-second';
    else if (price === sortedUniqueDesc[sortedUniqueDesc.length - 1]) rankClass = 'is-low';
  }
  
  return `
    <td class="source-data-cell" data-source="${esc(source)}">
      <div class="price-card ${rankClass}">
        <span class="price-card-val">${esc(money.format(price))}</span>
        <a href="${esc(listing.url)}" class="open-link-btn" target="_blank" rel="noopener" title="Open listing" onclick="event.stopPropagation()">↗</a>
      </div>
    </td>
  `;
}

function filtered() {
  const q = search.value.trim().toLowerCase();
  const brand = brandFilter.value;
  const source = sourceFilter.value;
  
  const list = products.filter(p => 
    (!q || p.product_name.toLowerCase().includes(q) || p.brand_name.toLowerCase().includes(q)) &&
    (!brand || p.brand_name === brand) &&
    (!source || p.sources[source])
  );
  
  if (sort.value === 'product') list.sort((a, b) => a.product_name.localeCompare(b.product_name));
  if (sort.value === 'mfgAsc') list.sort((a, b) => a.manufactured_price - b.manufactured_price);
  if (sort.value === 'mfgDesc') list.sort((a, b) => b.manufactured_price - a.manufactured_price);
  if (sort.value === 'coverage') list.sort((a, b) => Object.keys(b.sources).length - Object.keys(a.sources).length);
  if (sort.value === 'spread') list.sort((a, b) => spread(b) - spread(a));
  return list;
}

function render() {
  const list = filtered();
  const activeSources = getVisibleSources(list);
  
  updateHeaders(activeSources);
  
  body.innerHTML = list.map(p => `
    <tr tabindex="0" data-index="${products.indexOf(p)}">
      <td class="col-product"><div class="item-name" title="${esc(p.product_name)}">${esc(p.product_name)}</div></td>
      <td class="col-brand"><span class="brand-label">${esc(p.brand_name)}</span></td>
      <td class="col-mfg"><span class="price-text mfg">${esc(money.format(p.manufactured_price))}</span></td>
      <td class="col-market"><span class="price-text">${esc(money.format(p.market_average_price))}</span></td>
      ${activeSources.map(s => sourceCell(p, s, activeSources)).join('')}
    </tr>
  `).join('');
  
  empty.hidden = list.length > 0;
}

function openDetail(p) {
  document.getElementById('dialogBrand').textContent = p.brand_name;
  document.getElementById('dialogName').textContent = p.product_name;
  
  let out = `
    <div class="stats-summary-grid">
      <div class="stat-item"><span>Manufactured Price</span><strong>${esc(money.format(p.manufactured_price))}</strong></div>
      <div class="stat-item"><span>Market Average</span><strong>${esc(money.format(p.market_average_price))}</strong></div>
    </div>
    <div class="source-items-list">
  `;
  
  const matchedSources = sources.filter(s => p.sources[s]);
  if (!matchedSources.length) {
    out += '<div style="color:var(--text-secondary);padding:10px 0;font-size:12px;">No external verified listings found.</div>';
  } else {
    matchedSources.forEach(s => {
      const x = p.sources[s];
      out += `
        <div class="source-row">
          <div>
            <div style="font-weight:600;font-size:13px;color:var(--text);">${esc(s)}</div>
            <div style="font-size:11.5px;color:var(--text-secondary);margin-top:2px;">${esc(x.matched_title || '')}</div>
          </div>
          <div style="text-align:right;">
            <div style="font-weight:700;font-size:15px;color:#0284c7;">${esc(money.format(x.price))}</div>
            <a href="${esc(x.url)}" target="_blank" rel="noopener">Open link ↗</a>
          </div>
        </div>
      `;
    });
  }
  out += '</div>';
  
  document.getElementById('detail').innerHTML = out;
  document.getElementById('dialog').showModal();
}

body.addEventListener('click', e => {
  const row = e.target.closest('tr[data-index]');
  if (row && !e.target.closest('a')) openDetail(products[+row.dataset.index]);
});

document.getElementById('close').onclick = () => document.getElementById('dialog').close();
document.getElementById('dialog').addEventListener('click', e => {
  if (e.target.id === 'dialog') e.target.close();
});

[search, brandFilter, sourceFilter, sort].forEach(x => x.addEventListener('input', render));

document.getElementById('download').onclick = () => {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'product_pricing_data.json';
  a.click();
  URL.revokeObjectURL(url);
};

render();
</script>
</body>
</html>'''.replace('__DATA__', embedded)

HTML_PATH.write_text(html, encoding='utf-8')
(PUBLIC_DIR / 'index.html').write_text(html, encoding='utf-8')
print(json.dumps({'status': 'ok', 'html': str(HTML_PATH), 'public_html': str(PUBLIC_DIR / 'index.html')}))
