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
        'row': item['row'],
        'product_name': item['product_name'],
        'brand_name': item['brand_name'],
        'size': item.get('size', ''),
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
    'generated_at': research.get('generated_at') or '2026-08-18T12:00:00Z',
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
<title>Price Intelligence Matrix</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #f8fafc;
  --surface: #ffffff;
  --surface-subtle: #f1f5f9;
  --surface-hover: #f8fafc;
  
  --text-main: #0f172a;
  --text-secondary: #475569;
  --text-muted: #64748b;
  --text-dim: #94a3b8;
  
  --border: #e2e8f0;
  --border-light: #f1f5f9;
  --border-strong: #cbd5e1;
  --border-dark: #0f172a;

  --brand-blue: #0284c7;
  --brand-blue-subtle: #e0f2fe;

  /* Impeccable Semantic Markup Tiers */
  --chip-neg-bg: #fee2e2;
  --chip-neg-text: #991b1b;
  --chip-neg-border: #fca5a5;

  --chip-zero-bg: #f1f5f9;
  --chip-zero-text: #475569;
  --chip-zero-border: #e2e8f0;

  --chip-tier1-bg: #e0f2fe;
  --chip-tier1-text: #0369a1;
  --chip-tier1-border: #bae6fd;

  --chip-tier2-bg: #fef3c7;
  --chip-tier2-text: #92400e;
  --chip-tier2-border: #fde68a;

  --chip-tier3-bg: #ffedd5;
  --chip-tier3-text: #9a3412;
  --chip-tier3-border: #fed7aa;

  --chip-tier4-bg: #fee2e2;
  --chip-tier4-text: #991b1b;
  --chip-tier4-border: #fca5a5;

  /* Market Discount Chip Colors (Green when selling below market average) */
  --chip-mkt-disc-bg: #ecfdf5;
  --chip-mkt-disc-text: #047857;
  --chip-mkt-disc-border: #a7f3d0;

  --chip-mkt-prem-bg: #fef2f2;
  --chip-mkt-prem-text: #b91c1c;
  --chip-mkt-prem-border: #fca5a5;

  --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1);
  --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.1);
  --shadow-pin: 4px 0 12px rgba(15, 23, 42, 0.06);

  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-display: 'Plus Jakarta Sans', var(--font-sans);
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--bg);
  color: var(--text-main);
  font-family: var(--font-sans);
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  letter-spacing: -0.012em;
  -webkit-font-smoothing: antialiased;
}

/* 1. Master Control Header */
header.app-header {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  height: 56px;
  padding: 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-shrink: 0;
  z-index: 50;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.brand-title {
  font-family: var(--font-display);
  font-size: 14px;
  font-weight: 800;
  color: var(--text-main);
  letter-spacing: -0.02em;
  display: flex;
  align-items: center;
  gap: 8px;
  text-transform: uppercase;
}

.brand-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #0ea5e9;
  box-shadow: 0 0 8px #0ea5e9;
}
.brand-dot.synced {
  background: #10b981;
  box-shadow: 0 0 8px #10b981;
}

.header-meta-pill {
  background: var(--surface-subtle);
  border: 1px solid var(--border);
  padding: 3px 9px;
  border-radius: 6px;
  font-size: 11.5px;
  color: var(--text-muted);
  font-weight: 500;
  white-space: nowrap;
}
.header-meta-pill strong {
  color: var(--text-main);
  font-weight: 700;
}

.header-center {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  max-width: 660px;
}

.search-field {
  position: relative;
  flex: 1.5;
}
.search-field svg {
  position: absolute;
  left: 11px;
  top: 50%;
  transform: translateY(-50%);
  width: 14px;
  height: 14px;
  color: var(--text-dim);
  pointer-events: none;
}
.search-field input {
  width: 100%;
  height: 34px;
  padding: 0 10px 0 34px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 7px;
  font-size: 12.5px;
  color: var(--text-main);
  font-family: inherit;
  outline: none;
  transition: all .15s ease;
}
.search-field input:focus {
  background: #ffffff;
  border-color: var(--border-dark);
  box-shadow: 0 0 0 1px var(--border-dark);
}

.select-field {
  position: relative;
  flex: 1;
}
.select-field select {
  width: 100%;
  height: 34px;
  padding: 0 24px 0 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 7px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-main);
  font-family: inherit;
  outline: none;
  cursor: pointer;
  appearance: none;
  -webkit-appearance: none;
  transition: all .15s ease;
}
.select-field select:focus {
  background: #ffffff;
  border-color: var(--border-dark);
}
.select-field::after {
  content: '';
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  width: 0;
  height: 0;
  border-left: 3.5px solid transparent;
  border-right: 3.5px solid transparent;
  border-top: 4.5px solid var(--text-muted);
  pointer-events: none;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* Premium Button Styles */
.btn-calc {
  height: 34px;
  padding: 0 13px;
  border-radius: 7px;
  border: 1px solid var(--text-main);
  background: var(--text-main);
  color: #ffffff;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  transition: all .15s ease;
  white-space: nowrap;
  box-shadow: var(--shadow-sm);
}
.btn-calc:hover {
  background: #1e293b;
  border-color: #1e293b;
  transform: translateY(-0.5px);
}
.btn-calc svg { width: 14px; height: 14px; }

.btn-toggle-view {
  height: 34px;
  padding: 0 12px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: all .15s ease;
  white-space: nowrap;
}
.btn-toggle-view:hover {
  background: var(--surface-subtle);
  color: var(--text-main);
  border-color: var(--border-strong);
}
.btn-toggle-view.active-mode {
  background: #eff6ff;
  color: #1d4ed8;
  border-color: #bfdbfe;
}
.btn-toggle-view svg { width: 14px; height: 14px; }

.btn-icon {
  width: 34px;
  height: 34px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all .15s ease;
}
.btn-icon:hover {
  background: var(--bg);
  color: var(--text-main);
  border-color: var(--border-strong);
}

/* 2. Grid Table Viewport */
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
  background: #f8fafc;
  color: var(--text-secondary);
  font-size: 10.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  border-right: 1px solid var(--border-light);
  white-space: nowrap;
  user-select: none;
  cursor: pointer;
  transition: background .12s ease;
}
thead th:hover {
  background: #f1f5f9;
}

th.source-col-head {
  min-width: 200px;
  text-align: left;
}
.source-head-wrap {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.badge-channel {
  font-size: 9px;
  padding: 2px 5px;
  border-radius: 4px;
  font-weight: 600;
  text-transform: uppercase;
}
.badge-channel.official { background: #e0f2fe; color: #0369a1; }
.badge-channel.market { background: #f1f5f9; color: #64748b; }

/* 3. Sticky Columns (5 Base Columns) */
.col-product {
  position: sticky;
  left: 0;
  z-index: 20;
  width: 280px;
  min-width: 280px;
  max-width: 280px;
  background: #ffffff;
}
.col-brand {
  position: sticky;
  left: 280px;
  z-index: 20;
  width: 115px;
  min-width: 115px;
  max-width: 115px;
  background: #ffffff;
}
.col-mfg {
  position: sticky;
  left: 395px;
  z-index: 20;
  width: 115px;
  min-width: 115px;
  max-width: 115px;
  background: #ffffff;
  text-align: right;
}
.col-market {
  position: sticky;
  left: 510px;
  z-index: 20;
  width: 185px;
  min-width: 185px;
  max-width: 185px;
  background: #ffffff;
}
.col-selling-price {
  position: sticky;
  left: 695px;
  z-index: 20;
  width: 185px;
  min-width: 185px;
  max-width: 185px;
  background: #ffffff;
  border-right: 2px solid #cbd5e1 !important;
  box-shadow: var(--shadow-pin);
}

thead th.col-product, thead th.col-brand, thead th.col-mfg, thead th.col-market, thead th.col-selling-price {
  z-index: 35;
  background: #f1f5f9;
}

/* Rows & Cells */
tbody tr {
  cursor: pointer;
  transition: background-color 0.08s ease;
}
tbody tr:hover td {
  background-color: var(--surface-hover) !important;
}

td {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-light);
  border-right: 1px solid var(--border-light);
  vertical-align: middle;
  height: 52px;
  background: #ffffff;
}

tbody tr:hover td.col-product,
tbody tr:hover td.col-brand,
tbody tr:hover td.col-mfg,
tbody tr:hover td.col-market,
tbody tr:hover td.col-selling-price {
  background-color: #f1f5f9 !important;
}

.item-name {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-main);
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
  max-width: 100px;
  display: block;
}

.num-price {
  font-size: 13.5px;
  font-weight: 600;
  color: #334155;
}
.num-price.mfg {
  color: #0284c7;
  font-weight: 700;
}
.num-price.selling {
  color: #0f172a;
  font-weight: 700;
}
.num-price.custom-tuned {
  color: #7c3aed;
  font-weight: 700;
}

/* Dual Metric Layout for Market Avg & Selling Price */
.dual-metric-cell {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 7px;
  width: 100%;
}

.custom-tune-tag {
  font-size: 9px;
  font-weight: 700;
  padding: 1px 4px;
  background: #ede9fe;
  color: #6d28d9;
  border-radius: 4px;
  text-transform: uppercase;
}

/* Source Cells & Cards */
.source-data-cell {
  padding: 5px 8px;
  min-width: 200px;
  background: #ffffff;
}
.price-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 6px;
  border-radius: 6px;
  background: transparent;
}
.price-left-group {
  display: flex;
  align-items: center;
  gap: 7px;
}
.price-val {
  font-size: 13.5px;
  font-weight: 600;
  color: #18181b;
}

/* Markup Chips with Clear Semantics */
.markup-chip {
  font-size: 10.5px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 5px;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  letter-spacing: -0.01em;
  border: 1px solid transparent;
  white-space: nowrap;
}

.markup-chip.neg {
  background: var(--chip-neg-bg);
  border-color: var(--chip-neg-border);
  color: var(--chip-neg-text);
}
.markup-chip.zero {
  background: var(--chip-zero-bg);
  border-color: var(--chip-zero-border);
  color: var(--chip-zero-text);
}
.markup-chip.t1 {
  background: var(--chip-tier1-bg);
  border-color: var(--chip-tier1-border);
  color: var(--chip-tier1-text);
}
.markup-chip.t2 {
  background: var(--chip-tier2-bg);
  border-color: var(--chip-tier2-border);
  color: var(--chip-tier2-text);
}
.markup-chip.t3 {
  background: var(--chip-tier3-bg);
  border-color: var(--chip-tier3-border);
  color: var(--chip-tier3-text);
}
.markup-chip.t4 {
  background: var(--chip-tier4-bg);
  border-color: var(--chip-tier4-border);
  color: var(--chip-tier4-text);
}

/* Market Discount Mode Chips */
.markup-chip.mkt-disc {
  background: var(--chip-mkt-disc-bg);
  border-color: var(--chip-mkt-disc-border);
  color: var(--chip-mkt-disc-text);
}
.markup-chip.mkt-prem {
  background: var(--chip-mkt-prem-bg);
  border-color: var(--chip-mkt-prem-border);
  color: var(--chip-mkt-prem-text);
}

.btn-open-link {
  color: var(--text-dim);
  text-decoration: none;
  font-size: 11px;
  padding: 2px 5px;
  border-radius: 4px;
  border: 1px solid transparent;
  transition: all .12s;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.price-card:hover .btn-open-link {
  color: var(--text-main);
  background: #f1f5f9;
  border-color: var(--border);
}

.cell-dash {
  color: #cbd5e1;
  font-size: 13px;
  text-align: center;
  display: block;
}

/* 4. Impeccable Modals & Dialogs */
dialog {
  margin: auto;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: #ffffff;
  color: var(--text-main);
  width: min(640px, calc(100% - 32px));
  box-shadow: var(--shadow-lg);
  outline: none;
}
dialog::backdrop {
  background: rgba(15, 23, 42, 0.35);
  backdrop-filter: blur(3px);
}
.modal-header {
  padding: 16px 22px;
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #f8fafc;
}
.modal-heading-group {
  display: flex;
  flex-direction: column;
}
.modal-kicker {
  font-size: 10.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--brand-blue);
}
.modal-title {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 700;
  color: var(--text-main);
  margin-top: 2px;
}
.modal-btn-close {
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  width: 28px;
  height: 28px;
  border-radius: 6px;
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all .12s ease;
}
.modal-btn-close:hover { background: #f1f5f9; color: var(--text-main); }
.modal-body {
  padding: 22px;
  display: grid;
  gap: 18px;
  max-height: 75vh;
  overflow-y: auto;
}

/* Pricing Engine Form Controls */
.engine-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.engine-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.engine-field label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-main);
}
.engine-field span.hint {
  font-size: 11px;
  color: var(--text-muted);
}
.engine-input {
  height: 38px;
  padding: 0 12px;
  border: 1px solid var(--border-strong);
  border-radius: 7px;
  font-size: 13px;
  font-family: inherit;
  outline: none;
  background: #ffffff;
  color: var(--text-main);
  transition: all .12s ease;
}
.engine-input:focus {
  border-color: var(--border-dark);
  box-shadow: 0 0 0 1px var(--border-dark);
}

.engine-preview-card {
  background: #f8fafc;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px;
  display: grid;
  gap: 10px;
}
.engine-preview-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12.5px;
  color: var(--text-secondary);
}
.engine-preview-row strong {
  color: var(--text-main);
  font-size: 13px;
}
.engine-preview-row.total-highlight {
  border-top: 1px solid var(--border);
  padding-top: 10px;
  margin-top: 4px;
  font-size: 14px;
  font-weight: 700;
  color: var(--text-main);
}
.engine-preview-row.total-highlight strong {
  font-size: 16px;
  color: var(--brand-blue);
}

/* Discount Type Toggle Pill */
.discount-type-group {
  display: flex;
  background: var(--surface-subtle);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 2px;
  gap: 2px;
}
.discount-type-btn {
  flex: 1;
  height: 28px;
  border: none;
  background: transparent;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-secondary);
  border-radius: 4px;
  cursor: pointer;
  transition: all .12s ease;
}
.discount-type-btn.active {
  background: #ffffff;
  color: var(--text-main);
  box-shadow: var(--shadow-sm);
}

/* Detail Drawer Styles */
.detail-stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  background: #f8fafc;
  padding: 14px;
  border-radius: 10px;
  border: 1px solid var(--border);
}
.detail-stat-box span {
  display: block;
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 600;
  text-transform: uppercase;
}
.detail-stat-box strong {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-main);
  margin-top: 2px;
  display: block;
}
.detail-sources-list {
  display: grid;
  gap: 8px;
}
.detail-source-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 11px 14px;
  background: #ffffff;
  border: 1px solid var(--border);
  border-radius: 8px;
}
.detail-source-row a {
  color: var(--brand-blue);
  text-decoration: none;
  font-size: 12px;
  font-weight: 600;
}
.detail-source-row a:hover { text-decoration: underline; }

.tab-nav {
  display: flex;
  gap: 8px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 12px;
}
.tab-btn {
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 12.5px;
  font-weight: 600;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}
.tab-btn.active {
  background: var(--surface-subtle);
  color: var(--text-main);
  border-color: var(--border);
}

.empty-state {
  padding: 80px 20px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13.5px;
}
</style>
</head>
<body>

<!-- 1. Top Navbar -->
<header class="app-header">
  <div class="header-left">
    <div class="brand-title">
      <span class="brand-dot" id="liveSyncDot" title="Connected to Cloudflare D1 Edge Database"></span>
      Price Matrix
    </div>
    <div class="divider-v"></div>
    <div class="header-meta-pill"><strong id="productTotal">0</strong> SKUs · <strong id="listingTotal">0</strong> Listings</div>
  </div>

  <div class="header-center">
    <div class="search-field">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
      <input id="search" type="search" placeholder="Search product or brand..." autofocus>
    </div>
    
    <div class="select-field">
      <select id="brandFilter"><option value="">All Brands</option></select>
    </div>
    
    <div class="select-field">
      <select id="sourceFilter"><option value="">All Channels</option></select>
    </div>
    
    <div class="select-field">
      <select id="sort">
        <option value="product">Product A–Z</option>
        <option value="productDesc">Product Z–A</option>
        <option value="brand">Brand A–Z</option>
        <option value="sellingAsc">Selling: Low → High</option>
        <option value="sellingDesc">Selling: High → Low</option>
        <option value="mfgAsc">MFG: Low → High</option>
        <option value="mfgDesc">MFG: High → Low</option>
        <option value="marketAsc">Market Avg: Low → High</option>
        <option value="marketDesc">Market Avg: High → Low</option>
        <option value="coverage">Most Channels</option>
        <option value="spread">Largest Spread</option>
      </select>
    </div>
  </div>

  <div class="header-right">
    <button class="btn-toggle-view" id="toggleSellingChipModeBtn" onclick="toggleSellingChipMode()">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 3h5v5M4 20L21 3M21 16v5h-5M15 15l6 6M4 4l5 5"/></svg>
      <span id="sellingChipBtnLabel">View Market Discount %</span>
    </button>
    <button class="btn-calc" id="openEngineBtn">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
      Pricing Engine
    </button>
    <button class="btn-icon" id="download" title="Export Dataset (JSON)">
      <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"></path></svg>
    </button>
  </div>
</header>

<!-- 2. Grid Table Viewport -->
<main class="table-viewport">
  <table>
    <thead>
      <tr id="headerRow">
        <th class="col-product" data-sort="product" title="Product Title and SKU details. Click to toggle sort.">Product Name ↕</th>
        <th class="col-brand" data-sort="brand" title="Brand / Manufacturer Name. Click to toggle sort.">Brand ↕</th>
        <th class="col-mfg" data-sort="mfg" title="Manufacturing / Sourcing Purchase Price (Internal Reference). Click to toggle sort.">MFG Price ↕</th>
        <th class="col-market" data-sort="market" title="Market Average Selling Price across all channels, with the Average Markup % chip vs MFG Price. Click to toggle sort.">Market Avg ↕</th>
        <th class="col-selling-price" id="sellingPriceColHeader" data-sort="selling" title="Configured Selling Price. Toggle view mode to switch chip between Markup vs MFG % and Discount vs Market Avg %. Click to toggle sort.">Selling Price ↕</th>
      </tr>
    </thead>
    <tbody id="body"></tbody>
  </table>
  <div id="empty" class="empty-state" hidden>No products match the selected criteria.</div>
</main>

<!-- 3. Global Pricing Engine Modal -->
<dialog id="engineModal">
  <div class="modal-header">
    <div class="modal-heading-group">
      <span class="modal-kicker">Global Unit Economics</span>
      <h2 class="modal-title">Pricing Engine</h2>
    </div>
    <button class="modal-btn-close" id="closeEngineModal" aria-label="Close">✕</button>
  </div>
  <div class="modal-body">
    <div class="engine-grid">
      <div class="engine-field">
        <label for="inputPackaging">Packaging (BDT)</label>
        <input type="number" id="inputPackaging" class="engine-input" value="20" min="0" step="1">
        <span class="hint">Per-unit box/wrap cost</span>
      </div>
      <div class="engine-field">
        <label for="inputTransport">Transport (BDT)</label>
        <input type="number" id="inputTransport" class="engine-input" value="0" min="0" step="1">
        <span class="hint">Inbound freight allocation</span>
      </div>
      <div class="engine-field">
        <label for="inputDelivery">Delivery / Courier (BDT)</label>
        <input type="number" id="inputDelivery" class="engine-input" value="60" min="0" step="1">
        <span class="hint">Last-mile fulfillment cost</span>
      </div>
      <div class="engine-field">
        <label for="inputCAC">CAC / Marketing (BDT)</label>
        <input type="number" id="inputCAC" class="engine-input" value="0" min="0" step="1">
        <span class="hint">Acquisition cost per order</span>
      </div>
      <div class="engine-field">
        <label for="inputMarginPct">Target Margin (%)</label>
        <input type="number" id="inputMarginPct" class="engine-input" value="0" min="0" step="1">
        <span class="hint">Gross target markup</span>
      </div>
      <div class="engine-field">
        <label>Discount Type & Value</label>
        <div class="discount-type-group">
          <button type="button" class="discount-type-btn active" id="btnTypePct" onclick="setDiscountType('pct')">Percentage (%)</button>
          <button type="button" class="discount-type-btn" id="btnTypeAmt" onclick="setDiscountType('amt')">Amount (BDT)</button>
        </div>
        <input type="number" id="inputDiscountVal" class="engine-input" value="0" min="0" step="1" style="margin-top:4px;">
        <span class="hint" id="discountHint">Promotional discount percentage</span>
      </div>
    </div>

    <div class="engine-preview-card">
      <div class="engine-preview-row">
        <span>Total Variable Overhead (Pack + Trans + Deliv + CAC):</span>
        <strong id="summaryOverhead">৳200.00</strong>
      </div>
      <div class="engine-preview-row">
        <span>Calculation Logic:</span>
        <span id="formulaDescription">(MFG + Overhead) × (1 + Margin%) - Discount</span>
      </div>
      <div class="engine-preview-row total-highlight">
        <span>Model Benchmark (at ৳1,000 MFG):</span>
        <strong id="summarySample">৳1,350.00</strong>
      </div>
    </div>

    <div style="display:flex;gap:10px;">
      <button class="btn-calc" id="applyEngineBtn" style="flex:1;justify-content:center;height:40px;font-size:13px;">
        Apply to All Products
      </button>
      <button type="button" class="btn-icon" id="resetCustomOverridesBtn" title="Reset all per-product custom overrides" style="width:40px;height:40px;color:#ef4444;" onclick="resetAllCustomOverrides()">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
      </button>
    </div>
  </div>
</dialog>

<!-- 4. Product Detail & Per-Product Tuning Modal -->
<dialog id="dialog">
  <div class="modal-header">
    <div class="modal-heading-group">
      <span class="modal-kicker" id="dialogBrand"></span>
      <h2 class="modal-title" id="dialogName"></h2>
    </div>
    <button class="modal-btn-close" id="close" aria-label="Close">✕</button>
  </div>
  <div class="modal-body">
    <div class="tab-nav">
      <button class="tab-btn active" id="tabOverviewBtn" onclick="switchDetailTab('overview')">Market Overview</button>
      <button class="tab-btn" id="tabTuneBtn" onclick="switchDetailTab('tune')">Custom Pricing Engine</button>
    </div>

    <div id="tabOverviewContent" style="display:grid;gap:16px;"></div>

    <div id="tabTuneContent" style="display:none;grid-gap:16px;">
      <div style="font-size:12.5px;color:var(--text-secondary);line-height:1.4;">
        Customize unit costs and margins specifically for this product. Changes here override the global engine settings and persist across sessions via Cloudflare D1.
      </div>
      
      <div class="engine-grid">
        <div class="engine-field">
          <label for="prodInputPackaging">Packaging (BDT)</label>
          <input type="number" id="prodInputPackaging" class="engine-input" min="0" step="1">
        </div>
        <div class="engine-field">
          <label for="prodInputTransport">Transport (BDT)</label>
          <input type="number" id="prodInputTransport" class="engine-input" min="0" step="1">
        </div>
        <div class="engine-field">
          <label for="prodInputDelivery">Delivery (BDT)</label>
          <input type="number" id="prodInputDelivery" class="engine-input" min="0" step="1">
        </div>
        <div class="engine-field">
          <label for="prodInputCAC">CAC / Marketing (BDT)</label>
          <input type="number" id="prodInputCAC" class="engine-input" min="0" step="1">
        </div>
        <div class="engine-field">
          <label for="prodInputMarginPct">Target Margin (%)</label>
          <input type="number" id="prodInputMarginPct" class="engine-input" min="0" step="1">
        </div>
        <div class="engine-field">
          <label>Discount Type & Value</label>
          <div class="discount-type-group">
            <button type="button" class="discount-type-btn" id="prodBtnTypePct" onclick="setProdDiscountType('pct')">Percentage (%)</button>
            <button type="button" class="discount-type-btn" id="prodBtnTypeAmt" onclick="setProdDiscountType('amt')">Amount (BDT)</button>
          </div>
          <input type="number" id="prodInputDiscountVal" class="engine-input" min="0" step="1" style="margin-top:4px;">
        </div>
      </div>

      <div class="engine-preview-card">
        <div class="engine-preview-row">
          <span>This Product's Selling Price:</span>
          <strong id="prodSummarySelling" style="font-size:16px;color:var(--brand-blue);">—</strong>
        </div>
      </div>

      <div style="display:flex;gap:10px;">
        <button class="btn-calc" style="flex:1;justify-content:center;height:38px;font-size:13px;" onclick="saveProductCustomEngine()">
          Save Custom Product Settings
        </button>
        <button type="button" class="btn-calc" style="background:#f1f5f9;color:#0f172a;border-color:#e2e8f0;height:38px;font-size:12.5px;" onclick="clearProductCustomEngine()">
          Reset to Global Defaults
        </button>
      </div>
    </div>
  </div>
</dialog>

<script id="data" type="application/json">__DATA__</script>
<script>
// Initial bootstrap dataset
const initialData = JSON.parse(document.getElementById('data').textContent);
let products = initialData.products;
const sources = initialData.source_columns;
const money = new Intl.NumberFormat('en-BD', { style: 'currency', currency: 'BDT', minimumFractionDigits: 0, maximumFractionDigits: 0 });
const esc = v => String(v ?? '').replace(/[&<>'"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));

// Global Cost Parameters (Persistent with Cloudflare D1 + localStorage fallback)
const STORAGE_KEY_GLOBAL = 'price_matrix_global_params';
const STORAGE_KEY_OVERRIDES = 'price_matrix_custom_overrides';
const STORAGE_KEY_CHIP_MODE = 'price_matrix_selling_chip_mode';

let sellingChipMode = 'markup';
try {
  const savedMode = localStorage.getItem(STORAGE_KEY_CHIP_MODE);
  if (savedMode === 'markup' || savedMode === 'discount') sellingChipMode = savedMode;
} catch (e) {}

function updateSellingChipToggleUI() {
  const btn = document.getElementById('toggleSellingChipModeBtn');
  const label = document.getElementById('sellingChipBtnLabel');
  if (sellingChipMode === 'discount') {
    btn.classList.add('active-mode');
    label.textContent = 'View Product Markup %';
  } else {
    btn.classList.remove('active-mode');
    label.textContent = 'View Market Discount %';
  }
}

function toggleSellingChipMode() {
  sellingChipMode = (sellingChipMode === 'markup') ? 'discount' : 'markup';
  try { localStorage.setItem(STORAGE_KEY_CHIP_MODE, sellingChipMode); } catch (e) {}
  updateSellingChipToggleUI();
  render();
}

const defaultGlobalParams = {
  packaging: 20,
  transport: 0,
  delivery: 60,
  cac: 0,
  targetMarginPct: 0,
  discountType: 'pct',
  discountVal: 0
};

let globalCostParams = { ...defaultGlobalParams };
try {
  const saved = localStorage.getItem(STORAGE_KEY_GLOBAL);
  if (saved) globalCostParams = { ...globalCostParams, ...JSON.parse(saved) };
} catch (e) {}

let productOverrides = {};
try {
  const savedOverrides = localStorage.getItem(STORAGE_KEY_OVERRIDES);
  if (savedOverrides) productOverrides = JSON.parse(savedOverrides);
} catch (e) {}

// Async Sync with Cloudflare D1 Backend (fetches live products, listings, and engine parameters)
async function syncFromD1() {
  try {
    // 1. Fetch live product data from D1
    const pRes = await fetch('/api/products');
    if (pRes.ok) {
      const pData = await pRes.json();
      if (pData.success && pData.products && pData.products.length > 0) {
        products = pData.products;
        document.getElementById('liveSyncDot').classList.add('synced');
      }
    }

    // 2. Fetch live global parameters & custom overrides from D1
    const eRes = await fetch('/api/engine');
    if (eRes.ok) {
      const eData = await eRes.json();
      if (eData.success) {
        if (eData.globalParams) {
          globalCostParams = { ...globalCostParams, ...eData.globalParams };
          try { localStorage.setItem(STORAGE_KEY_GLOBAL, JSON.stringify(globalCostParams)); } catch(e){}
        }
        if (eData.overrides) {
          productOverrides = { ...productOverrides, ...eData.overrides };
          try { localStorage.setItem(STORAGE_KEY_OVERRIDES, JSON.stringify(productOverrides)); } catch(e){}
        }
      }
    }
    render();
  } catch (err) {
    // Offline or static preview fallback
  }
}
syncFromD1();

async function saveGlobalParamsToStorage() {
  try { localStorage.setItem(STORAGE_KEY_GLOBAL, JSON.stringify(globalCostParams)); } catch (e) {}
  try {
    await fetch('/api/engine', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(globalCostParams)
    });
  } catch (e) {}
}

async function saveProductOverridesToStorage(productName) {
  try { localStorage.setItem(STORAGE_KEY_OVERRIDES, JSON.stringify(productOverrides)); } catch (e) {}
  if (productName && productOverrides[productName]) {
    try {
      await fetch('/api/overrides', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ productName, ...productOverrides[productName] })
      });
    } catch (e) {}
  }
}

async function removeProductOverrideFromD1(productName) {
  try {
    await fetch(`/api/overrides?productName=${encodeURIComponent(productName)}`, { method: 'DELETE' });
  } catch (e) {}
}

async function clearAllProductOverridesFromD1() {
  try {
    await fetch('/api/overrides?all=true', { method: 'DELETE' });
  } catch (e) {}
}

let activeProductDetail = null;

const search = document.getElementById('search');
const brandFilter = document.getElementById('brandFilter');
const sourceFilter = document.getElementById('sourceFilter');
const sort = document.getElementById('sort');
const body = document.getElementById('body');
const empty = document.getElementById('empty');
const headerRow = document.getElementById('headerRow');

document.getElementById('productTotal').textContent = initialData.product_count.toLocaleString();
const listingTotal = Object.values(initialData.source_listing_counts).reduce((a, b) => a + b, 0);
document.getElementById('listingTotal').textContent = listingTotal.toLocaleString();

[...new Set(products.map(p => p.brand_name))].sort().forEach(v => brandFilter.add(new Option(v, v)));
sources.forEach(v => sourceFilter.add(new Option(v, v)));

function getProductParams(productName) {
  if (productOverrides[productName]) {
    return { ...globalCostParams, ...productOverrides[productName], isCustom: true };
  }
  return { ...globalCostParams, isCustom: false };
}

function computeSellingPrice(mfgPrice, productName) {
  if (!mfgPrice || mfgPrice <= 0) return null;
  const p = productName ? getProductParams(productName) : globalCostParams;
  const overhead = Number(p.packaging || 0) + Number(p.transport || 0) + Number(p.delivery || 0) + Number(p.cac || 0);
  const totalBaseCost = mfgPrice + overhead;
  const listPriceWithMargin = totalBaseCost * (1 + Number(p.targetMarginPct || 0) / 100);
  
  let finalSelling = listPriceWithMargin;
  if (p.discountType === 'pct') {
    finalSelling = listPriceWithMargin * (1 - Number(p.discountVal || 0) / 100);
  } else {
    finalSelling = Math.max(0, listPriceWithMargin - Number(p.discountVal || 0));
  }
  return Math.round(finalSelling);
}

function setDiscountType(type) {
  globalCostParams.discountType = type;
  document.getElementById('btnTypePct').classList.toggle('active', type === 'pct');
  document.getElementById('btnTypeAmt').classList.toggle('active', type === 'amt');
  document.getElementById('discountHint').textContent = type === 'pct' ? 'Promotional discount percentage (%)' : 'Fixed promotional discount amount (BDT)';
  updateEngineSummary();
}

function updateEngineSummary() {
  const overhead = Number(globalCostParams.packaging) + Number(globalCostParams.transport) + Number(globalCostParams.delivery) + Number(globalCostParams.cac);
  document.getElementById('summaryOverhead').textContent = `৳${overhead.toFixed(2)}`;
  const sample = computeSellingPrice(1000);
  document.getElementById('summarySample').textContent = `৳${sample.toFixed(2)}`;
  document.getElementById('formulaDescription').textContent = globalCostParams.discountType === 'pct'
    ? `(MFG + Overhead) × (1 + Margin%) × (1 - ${globalCostParams.discountVal}%)`
    : `(MFG + Overhead) × (1 + Margin%) - ৳${globalCostParams.discountVal}`;
}

function getVisibleSources(list) {
  if (!list.length) return [];
  return sources.filter(s => list.some(p => p.sources[s]?.price !== undefined && p.sources[s]?.price !== null));
}

function updateHeaders(activeSources) {
  headerRow.querySelectorAll('th.source-col-head').forEach(el => el.remove());
  
  activeSources.forEach(source => {
    const th = document.createElement('th');
    const official = /official/i.test(source);
    th.className = 'source-col-head';
    th.title = `${official ? 'Official Brand Flagship' : 'Third-Party E-Commerce Marketplace'} pricing for ${source}. Click to sort by this channel.`;
    th.dataset.source = source;
    th.innerHTML = `
      <div class="source-head-wrap">
        <span>${esc(source)}</span>
        <span class="badge-channel ${official ? 'official' : 'market'}">${official ? 'Official' : 'Mkt'}</span>
      </div>
    `;
    th.onclick = () => {
      if (sort.value === `srcAsc:${source}`) {
        sort.value = `srcDesc:${source}`;
      } else {
        if (![...sort.options].some(o => o.value === `srcAsc:${source}`)) {
          sort.add(new Option(`${source}: Low → High`, `srcAsc:${source}`));
          sort.add(new Option(`${source}: High → Low`, `srcDesc:${source}`));
        }
        sort.value = `srcAsc:${source}`;
      }
      render();
    };
    headerRow.appendChild(th);
  });
}

function calculateMarkup(sellingPrice, mfgPrice) {
  if (!mfgPrice || mfgPrice <= 0 || !sellingPrice) return null;
  return ((sellingPrice - mfgPrice) / mfgPrice) * 100;
}

function calculateMarketDiscount(sellingPrice, marketAvgPrice) {
  if (!marketAvgPrice || marketAvgPrice <= 0 || !sellingPrice) return null;
  return ((marketAvgPrice - sellingPrice) / marketAvgPrice) * 100;
}

function getMarkupChip(pct) {
  if (pct === null) return '';
  if (pct < -0.01) {
    return `<span class="markup-chip neg" title="${Math.abs(pct).toFixed(1)}% below MFG price">↓${pct.toFixed(0)}%</span>`;
  }
  if (Math.abs(pct) <= 0.01) {
    return `<span class="markup-chip zero" title="Equal to MFG price">0%</span>`;
  }
  if (pct <= 15) {
    return `<span class="markup-chip t1" title="+${pct.toFixed(1)}% markup over MFG">↑+${pct.toFixed(0)}%</span>`;
  }
  if (pct <= 35) {
    return `<span class="markup-chip t2" title="+${pct.toFixed(1)}% markup over MFG">↑+${pct.toFixed(0)}%</span>`;
  }
  if (pct <= 60) {
    return `<span class="markup-chip t3" title="+${pct.toFixed(1)}% markup over MFG">↑+${pct.toFixed(0)}%</span>`;
  }
  return `<span class="markup-chip t4" title="+${pct.toFixed(1)}% markup over MFG">↑+${pct.toFixed(0)}%</span>`;
}

function getMarketDiscountChip(discPct) {
  if (discPct === null) return '';
  if (discPct > 0.01) {
    return `<span class="markup-chip mkt-disc" title="${discPct.toFixed(1)}% discount off Market Average price">↓-${discPct.toFixed(0)}%</span>`;
  }
  if (Math.abs(discPct) <= 0.01) {
    return `<span class="markup-chip zero" title="Selling at Par with Market Average price">0%</span>`;
  }
  return `<span class="markup-chip mkt-prem" title="${Math.abs(discPct).toFixed(1)}% above Market Average price">↑+${Math.abs(discPct).toFixed(0)}%</span>`;
}

function sourceCell(p, source, activeSources) {
  const listing = p.sources[source];
  if (!listing) return '<td class="source-data-cell"><span class="cell-dash">—</span></td>';
  
  const price = Number(listing.price);
  const mfg = Number(p.manufactured_price);
  const markupPct = calculateMarkup(price, mfg);
  const markupChip = getMarkupChip(markupPct);
  
  return `
    <td class="source-data-cell" data-source="${esc(source)}">
      <div class="price-card">
        <div class="price-left-group">
          <span class="price-val">${esc(money.format(price))}</span>
          ${markupChip}
        </div>
        <a href="${esc(listing.url)}" class="btn-open-link" target="_blank" rel="noopener" title="Open listing" onclick="event.stopPropagation()">↗</a>
      </div>
    </td>
  `;
}

function spread(p) {
  const v = sources.map(s => p.sources[s]?.price).filter(v => v !== undefined && v !== null).map(Number);
  return v.length > 1 ? Math.max(...v) - Math.min(...v) : 0;
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
  if (sort.value === 'productDesc') list.sort((a, b) => b.product_name.localeCompare(a.product_name));
  if (sort.value === 'brand') list.sort((a, b) => a.brand_name.localeCompare(b.brand_name) || a.product_name.localeCompare(b.product_name));
  if (sort.value === 'sellingAsc') list.sort((a, b) => (computeSellingPrice(a.manufactured_price, a.product_name) || 0) - (computeSellingPrice(b.manufactured_price, b.product_name) || 0));
  if (sort.value === 'sellingDesc') list.sort((a, b) => (computeSellingPrice(b.manufactured_price, b.product_name) || 0) - (computeSellingPrice(a.manufactured_price, a.product_name) || 0));
  if (sort.value === 'mfgAsc') list.sort((a, b) => a.manufactured_price - b.manufactured_price);
  if (sort.value === 'mfgDesc') list.sort((a, b) => b.manufactured_price - a.manufactured_price);
  if (sort.value === 'marketAsc') list.sort((a, b) => a.market_average_price - b.market_average_price);
  if (sort.value === 'marketDesc') list.sort((a, b) => b.market_average_price - a.market_average_price);
  if (sort.value === 'coverage') list.sort((a, b) => Object.keys(b.sources).length - Object.keys(a.sources).length);
  if (sort.value === 'spread') list.sort((a, b) => spread(b) - spread(a));
  
  if (sort.value.startsWith('srcAsc:')) {
    const src = sort.value.split('srcAsc:')[1];
    list.sort((a, b) => (Number(a.sources[src]?.price) || 999999) - (Number(b.sources[src]?.price) || 999999));
  }
  if (sort.value.startsWith('srcDesc:')) {
    const src = sort.value.split('srcDesc:')[1];
    list.sort((a, b) => (Number(b.sources[src]?.price) || 0) - (Number(a.sources[src]?.price) || 0));
  }

  return list;
}

function render() {
  const list = filtered();
  const activeSources = getVisibleSources(list);
  
  updateHeaders(activeSources);
  updateSellingChipToggleUI();
  
  body.innerHTML = list.map(p => {
    const prices = Object.values(p.sources).map(x => Number(x.price)).filter(v => !isNaN(v) && v > 0);
    const mfg = Number(p.manufactured_price);
    const mktAvg = Number(p.market_average_price);
    let avgMarkupChip = '';
    
    if (prices.length > 0 && mfg > 0) {
      const sumPrices = prices.reduce((a, b) => a + b, 0);
      const avgPrice = sumPrices / prices.length;
      const avgMarkupPct = calculateMarkup(avgPrice, mfg);
      avgMarkupChip = getMarkupChip(avgMarkupPct);
    }

    const marketAvgDisplay = `
      <div class="dual-metric-cell">
        <span class="num-price">${esc(money.format(mktAvg))}</span>
        ${avgMarkupChip}
      </div>
    `;

    const hasOverride = !!productOverrides[p.product_name];
    const calculatedSelling = computeSellingPrice(mfg, p.product_name);
    let sellingDisplay = '<span class="cell-dash">—</span>';
    
    if (calculatedSelling && mfg > 0) {
      let activeChipHtml = '';
      if (sellingChipMode === 'discount' && mktAvg > 0) {
        const mktDiscPct = calculateMarketDiscount(calculatedSelling, mktAvg);
        activeChipHtml = getMarketDiscountChip(mktDiscPct);
      } else {
        const sellingMarkupPct = calculateMarkup(calculatedSelling, mfg);
        activeChipHtml = getMarkupChip(sellingMarkupPct);
      }

      sellingDisplay = `
        <div class="dual-metric-cell">
          ${hasOverride ? '<span class="custom-tune-tag" title="Custom per-product pricing engine override active">Tuned</span>' : ''}
          <span class="num-price ${hasOverride ? 'custom-tuned' : 'selling'}">${esc(money.format(calculatedSelling))}</span>
          ${activeChipHtml}
        </div>
      `;
    }

    return `
      <tr tabindex="0" data-index="${products.indexOf(p)}">
        <td class="col-product"><div class="item-name" title="${esc(p.product_name)}">${esc(p.product_name)}</div></td>
        <td class="col-brand"><span class="brand-label">${esc(p.brand_name)}</span></td>
        <td class="col-mfg"><span class="num-price mfg">${esc(money.format(p.manufactured_price))}</span></td>
        <td class="col-market">${marketAvgDisplay}</td>
        <td class="col-selling-price">${sellingDisplay}</td>
        ${activeSources.map(s => sourceCell(p, s, activeSources)).join('')}
      </tr>
    `;
  }).join('');
  
  empty.hidden = list.length > 0;
}

// Click header to sort
headerRow.querySelectorAll('th[data-sort]').forEach(th => {
  th.onclick = () => {
    const s = th.dataset.sort;
    if (s === 'product') sort.value = (sort.value === 'product') ? 'productDesc' : 'product';
    else if (s === 'brand') sort.value = 'brand';
    else if (s === 'mfg') sort.value = (sort.value === 'mfgAsc') ? 'mfgDesc' : 'mfgAsc';
    else if (s === 'market') sort.value = (sort.value === 'marketAsc') ? 'marketDesc' : 'marketAsc';
    else if (s === 'selling') sort.value = (sort.value === 'sellingAsc') ? 'sellingDesc' : 'sellingAsc';
    render();
  };
});

function switchDetailTab(tab) {
  document.getElementById('tabOverviewBtn').classList.toggle('active', tab === 'overview');
  document.getElementById('tabTuneBtn').classList.toggle('active', tab === 'tune');
  document.getElementById('tabOverviewContent').style.display = tab === 'overview' ? 'grid' : 'none';
  document.getElementById('tabTuneContent').style.display = tab === 'tune' ? 'grid' : 'none';
}

function openDetail(p) {
  activeProductDetail = p;
  document.getElementById('dialogBrand').textContent = p.brand_name;
  document.getElementById('dialogName').textContent = p.product_name;
  
  const mfg = Number(p.manufactured_price);
  const mktAvg = Number(p.market_average_price);
  const calculatedSelling = computeSellingPrice(mfg, p.product_name);
  const params = getProductParams(p.product_name);
  const overhead = Number(params.packaging) + Number(params.transport) + Number(params.delivery) + Number(params.cac);
  const sellingMarkupPct = calculatedSelling && mfg > 0 ? calculateMarkup(calculatedSelling, mfg) : null;
  const marketDiscPct = calculatedSelling && mktAvg > 0 ? calculateMarketDiscount(calculatedSelling, mktAvg) : null;
  
  const prices = Object.values(p.sources).map(x => Number(x.price)).filter(v => !isNaN(v) && v > 0);
  let avgMarketMarkupChip = '';
  if (prices.length > 0 && mfg > 0) {
    const avgPrice = prices.reduce((a, b) => a + b, 0) / prices.length;
    avgMarketMarkupChip = getMarkupChip(calculateMarkup(avgPrice, mfg));
  }

  let out = `
    <div class="detail-stats-grid">
      <div class="detail-stat-box"><span>Purchasing (MFG Price)</span><strong>${esc(money.format(mfg))}</strong></div>
      <div class="detail-stat-box">
        <span>Market Average</span>
        <strong style="display:flex;align-items:center;gap:6px;">
          ${esc(money.format(mktAvg))}
          ${avgMarketMarkupChip}
        </strong>
      </div>
      <div class="detail-stat-box">
        <span>Variable Overhead ${params.isCustom ? '(Custom)' : ''}</span>
        <strong>${esc(money.format(overhead))}</strong>
      </div>
      <div class="detail-stat-box">
        <span>Selling Price ${params.isCustom ? '(Custom)' : ''}</span>
        <strong style="color:var(--brand-blue);display:flex;align-items:center;flex-wrap:wrap;gap:6px;">
          ${calculatedSelling ? esc(money.format(calculatedSelling)) : '—'}
          ${getMarkupChip(sellingMarkupPct)}
          ${marketDiscPct !== null ? getMarketDiscountChip(marketDiscPct) : ''}
        </strong>
      </div>
    </div>
    <div class="detail-sources-list">
  `;
  
  const matchedSources = sources.filter(s => p.sources[s]);
  if (!matchedSources.length) {
    out += '<div style="color:var(--text-muted);padding:10px 0;font-size:12px;">No external verified listings found.</div>';
  } else {
    matchedSources.forEach(s => {
      const x = p.sources[s];
      const markupPct = calculateMarkup(Number(x.price), mfg);
      const markupChip = getMarkupChip(markupPct);
      out += `
        <div class="detail-source-row">
          <div>
            <div style="font-weight:600;font-size:13px;color:var(--text-main);">${esc(s)}</div>
            <div style="font-size:11.5px;color:var(--text-muted);margin-top:2px;">${esc(x.matched_title || '')}</div>
          </div>
          <div style="text-align:right;">
            <div style="font-weight:700;font-size:15px;color:var(--brand-blue);display:flex;align-items:center;justify-content:flex-end;gap:6px;">${esc(money.format(x.price))} ${markupChip}</div>
            <a href="${esc(x.url)}" target="_blank" rel="noopener">Open link ↗</a>
          </div>
        </div>
      `;
    });
  }
  out += '</div>';
  
  document.getElementById('tabOverviewContent').innerHTML = out;

  // Populate per-product tune inputs
  document.getElementById('prodInputPackaging').value = params.packaging;
  document.getElementById('prodInputTransport').value = params.transport;
  document.getElementById('prodInputDelivery').value = params.delivery;
  document.getElementById('prodInputCAC').value = params.cac;
  document.getElementById('prodInputMarginPct').value = params.targetMarginPct;
  document.getElementById('prodInputDiscountVal').value = params.discountVal;
  setProdDiscountType(params.discountType || 'pct', false);
  updateProdTuneSummary();

  switchDetailTab('overview');
  document.getElementById('dialog').showModal();
}

let currentProdDiscountType = 'pct';
function setProdDiscountType(type, triggerSummary = true) {
  currentProdDiscountType = type;
  document.getElementById('prodBtnTypePct').classList.toggle('active', type === 'pct');
  document.getElementById('prodBtnTypeAmt').classList.toggle('active', type === 'amt');
  if (triggerSummary) updateProdTuneSummary();
}

function updateProdTuneSummary() {
  if (!activeProductDetail) return;
  const mfg = Number(activeProductDetail.manufactured_price);
  const pkg = Number(document.getElementById('prodInputPackaging').value) || 0;
  const tr = Number(document.getElementById('prodInputTransport').value) || 0;
  const del = Number(document.getElementById('prodInputDelivery').value) || 0;
  const cac = Number(document.getElementById('prodInputCAC').value) || 0;
  const margin = Number(document.getElementById('prodInputMarginPct').value) || 0;
  const discVal = Number(document.getElementById('prodInputDiscountVal').value) || 0;

  const totalBase = mfg + pkg + tr + del + cac;
  const listPrice = totalBase * (1 + margin / 100);
  let finalVal = listPrice;
  if (currentProdDiscountType === 'pct') {
    finalVal = listPrice * (1 - discVal / 100);
  } else {
    finalVal = Math.max(0, listPrice - discVal);
  }
  document.getElementById('prodSummarySelling').textContent = esc(money.format(finalVal));
}

['prodInputPackaging', 'prodInputTransport', 'prodInputDelivery', 'prodInputCAC', 'prodInputMarginPct', 'prodInputDiscountVal'].forEach(id => {
  document.getElementById(id).addEventListener('input', updateProdTuneSummary);
});

async function saveProductCustomEngine() {
  if (!activeProductDetail) return;
  const name = activeProductDetail.product_name;
  productOverrides[name] = {
    packaging: Number(document.getElementById('prodInputPackaging').value) || 0,
    transport: Number(document.getElementById('prodInputTransport').value) || 0,
    delivery: Number(document.getElementById('prodInputDelivery').value) || 0,
    cac: Number(document.getElementById('prodInputCAC').value) || 0,
    targetMarginPct: Number(document.getElementById('prodInputMarginPct').value) || 0,
    discountType: currentProdDiscountType,
    discountVal: Number(document.getElementById('prodInputDiscountVal').value) || 0
  };
  await saveProductOverridesToStorage(name);
  document.getElementById('dialog').close();
  render();
}

async function clearProductCustomEngine() {
  if (!activeProductDetail) return;
  const name = activeProductDetail.product_name;
  delete productOverrides[name];
  await saveProductOverridesToStorage();
  await removeProductOverrideFromD1(name);
  document.getElementById('dialog').close();
  render();
}

async function resetAllCustomOverrides() {
  if (confirm('Reset all custom per-product overrides back to global Pricing Engine defaults?')) {
    productOverrides = {};
    await saveProductOverridesToStorage();
    await clearAllProductOverridesFromD1();
    render();
  }
}

body.addEventListener('click', e => {
  const row = e.target.closest('tr[data-index]');
  if (row && !e.target.closest('a')) openDetail(products[+row.dataset.index]);
});

document.getElementById('close').onclick = () => document.getElementById('dialog').close();
document.getElementById('dialog').addEventListener('click', e => {
  if (e.target.id === 'dialog') e.target.close();
});

// Pricing Engine Modal Listeners
const engineModal = document.getElementById('engineModal');
document.getElementById('openEngineBtn').onclick = () => {
  document.getElementById('inputPackaging').value = globalCostParams.packaging;
  document.getElementById('inputTransport').value = globalCostParams.transport;
  document.getElementById('inputDelivery').value = globalCostParams.delivery;
  document.getElementById('inputCAC').value = globalCostParams.cac;
  document.getElementById('inputMarginPct').value = globalCostParams.targetMarginPct;
  document.getElementById('inputDiscountVal').value = globalCostParams.discountVal;
  setDiscountType(globalCostParams.discountType || 'pct');
  updateEngineSummary();
  engineModal.showModal();
};

document.getElementById('closeEngineModal').onclick = () => engineModal.close();
engineModal.addEventListener('click', e => { if (e.target.id === 'engineModal') engineModal.close(); });

['inputPackaging', 'inputTransport', 'inputDelivery', 'inputCAC', 'inputMarginPct', 'inputDiscountVal'].forEach(id => {
  document.getElementById(id).addEventListener('input', () => {
    globalCostParams.packaging = Number(document.getElementById('inputPackaging').value) || 0;
    globalCostParams.transport = Number(document.getElementById('inputTransport').value) || 0;
    globalCostParams.delivery = Number(document.getElementById('inputDelivery').value) || 0;
    globalCostParams.cac = Number(document.getElementById('inputCAC').value) || 0;
    globalCostParams.targetMarginPct = Number(document.getElementById('inputMarginPct').value) || 0;
    globalCostParams.discountVal = Number(document.getElementById('inputDiscountVal').value) || 0;
    updateEngineSummary();
  });
});

document.getElementById('applyEngineBtn').onclick = async () => {
  await saveGlobalParamsToStorage();
  engineModal.close();
  render();
};

[search, brandFilter, sourceFilter, sort].forEach(x => x.addEventListener('input', render));

document.getElementById('download').onclick = () => {
  const exportData = {
    ...initialData,
    global_cost_parameters: globalCostParams,
    product_custom_overrides: productOverrides,
    products: products.map(p => ({
      ...p,
      pricing_parameters: getProductParams(p.product_name),
      calculated_selling_price: computeSellingPrice(p.manufactured_price, p.product_name)
    }))
  };
  const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
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
