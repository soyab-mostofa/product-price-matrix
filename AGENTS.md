# Project: Product Price Intelligence & Marketplace Benchmark Matrix

Real-time price benchmark dataset, automated multi-marketplace discovery pipeline, and interactive dashboard for 372 personal care and beauty SKUs across major Bangladeshi D2C brand flagships and third-party e-commerce channels.

- **Live Production URL**: https://product-price-matrix.pages.dev
- **Repository**: https://github.com/soyab-mostofa/product-price-matrix

## Technology Stack
- **Runtime**: Python 3.12+ (uv / pip), Node.js (Bun 1.3+)
- **Data & Excel**: openpyxl, pandas
- **Scraping & Networking**: primp (TLS fingerprint impersonation), BeautifulSoup4, ddgs
- **Matching & Similarity**: rapidfuzz
- **Deployment & Hosting**: Cloudflare Pages (via `wrangler`), GitHub

## Project Structure
- `product_marketplace_price_comparison.xlsx` — Canonical source spreadsheet containing formulas and populated Marketplace 1 & 2 listings
- `verified_marketplace_research.json` — Comprehensive JSON dataset with candidate records, tokens, and multi-channel mappings
- `verified_match_audit.json` — Full audit log of accepted matches and rejected candidates with explicit reasons
- `build_matrix.py` — Pipeline script that compiles datasets, calculates markups, and builds the UI
- `sku_matcher.py` — Strict brand, category, volume, and cosmetic shade validation engine
- `public/` — Production build directory (`index.html` & `product_pricing_data.json`) deployed to Cloudflare Pages
- `product_pricing_dashboard.html` — Standalone HTML dashboard
- `product_pricing_data.json` — Clean JSON data schema for frontend consumption

## Development Setup & Commands

### Prerequisites
- `uv` (Fast Python package runner)
- `bun` (JavaScript/TypeScript runtime & package manager)

### Build and Compilation Commands
```bash
# Rebuild datasets and UI artifacts
uv run --with openpyxl --with rapidfuzz python3 build_matrix.py

# Run scraping and gap fill
uv run --with primp --with beautifulsoup4 --with rapidfuzz --with ddgs python3 /tmp/fill_targeted_gaps.py
```

### Deployment Commands
```bash
# Deploy to Cloudflare Pages production
bunx wrangler pages deploy public --project-name product-price-matrix --commit-dirty=true
```

## Business Rules & SKU Matching Standards

1. **Strict Brand & SKU Integrity**:
   - Never substitute brands or allow loose keyword matches.
   - Respect parent/sub-brand hierarchy (*Nature Beauty*, *Quinsia*, *Qolore* under *Q Cosmetics*; *Bio-Screen* under *Bio-Xin*).
   - Enforce exact product category disambiguation (Serums ≠ Toners, Conditioners ≠ Shampoos, Cleansers ≠ Moisturizers).
   - Reject multi-item combos, bundles, and BOGO promotions unless the target SKU is explicitly a combo.
   - Enforce volume/weight equivalence (`ml`, `gm`, `g`).
   - Require exact cosmetic shade matching (*03, 05, Natural 07, Ivory Pink*).

2. **Discounted / Selling Price Priority**:
   - Always extract the active customer checkout price (discounted selling price) over the list price or MSRP whenever promotions are active.

3. **Internal Pricing Parity**:
   - Keep internal Excel pricing columns (`MFG price`, `Mkt (Avg) Price`) 100% faithful to workbook calculations without drift.
   - Never expose internal cost rollups (packaging, transport, product cost) in user-facing matrices.

## UI/UX Design System & Conventions

- **Font**: Inter across all UI elements, numerical prices, headers, and modals. Monospace fonts are prohibited.
- **Sticky Base Columns**:
  1. `Product Name` (310px)
  2. `Brand` (120px)
  3. `MFG Price` (120px)
  4. `Market Avg` (120px)
  5. `Avg Markup` (130px with divider border & shadow)
- **Dynamic Channel Column Auto-Hiding**:
  - Filtering by brand automatically collapses marketplace columns with 0 listings in the active view.
  - Any column with at least 1 listing remains visible.
- **Markup Percentage Chip Hierarchy**:
  - `Below MFG (Discount)`: Soft red pill (`#fef2f2` bg, `#b91c1c` text) with down arrow `↓-XX%`.
  - `At Par (0%)`: Neutral gray pill (`#f4f4f5` bg, `#52525b` text) `0%`.
  - `+1% to +15%`: Soft blue pill (`#eff6ff` bg, `#1d4ed8` text) `↑+XX%`.
  - `+15% to +35%`: Soft amber pill (`#fffbeb` bg, `#b45309` text) `↑+XX%`.
  - `+35% to +60%`: Warm orange pill (`#fff7ed` bg, `#c2410c` text) `↑+XX%`.
  - `>+60% Extreme`: Soft red pill (`#fef2f2` bg, `#b91c1c` text) `↑+XX%`.
- **Top Navigation Bar**:
  - Minimal 52px command bar with search input, brand filter, channel filter, sort dropdown, and icon-only JSON download action.

## Permissions & Safety
- **Allowed without prompting**: File edits, running `build_matrix.py`, scraping via `primp`/`ddgs`, deployment to Cloudflare Pages.
- **Require approval**: Direct force-push to remote branches, destructive file removal outside temporary directories.
