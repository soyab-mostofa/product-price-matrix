# Project: Product Price Intelligence & Marketplace Benchmark Matrix

Real-time price benchmark dataset, automated multi-marketplace discovery pipeline, and interactive dashboard for 372 personal care and beauty SKUs across major Bangladeshi D2C brand flagships and third-party e-commerce channels.

- **Live Production URL**: https://product-price-matrix.pages.dev
- **Repository**: https://github.com/soyab-mostofa/product-price-matrix

---

## 1. Technology Stack & Architecture

- **Runtime**: Python 3.12+ (uv / pip), Node.js (Bun 1.3+)
- **Data & Excel**: `openpyxl`, `pandas`
- **Scraping & Networking**: `primp` (TLS fingerprint impersonation for Cloudflare bypass), `BeautifulSoup4`, `ddgs`
- **Matching & Similarity**: `rapidfuzz`
- **Deployment & Hosting**: Cloudflare Pages (via `wrangler`), GitHub

### Core Artifacts
- `product_marketplace_price_comparison.xlsx` — Canonical source spreadsheet containing formulas and populated Marketplace 1 & 2 listings.
- `verified_marketplace_research.json` — Comprehensive JSON dataset with candidate records, tokens, and multi-channel mappings.
- `verified_match_audit.json` — Full audit log of accepted matches and rejected candidates with explicit reasons.
- `build_matrix.py` — Pipeline script that compiles datasets, calculates markups, evaluates unit economics, and generates static build assets.
- `sku_matcher.py` — Strict brand, category, volume, and cosmetic shade validation engine.
- `public/` — Production build directory (`index.html` & `product_pricing_data.json`) deployed to Cloudflare Pages.
- `product_pricing_dashboard.html` — Standalone HTML dashboard.
- `product_pricing_data.json` — Clean JSON data schema for frontend consumption.

---

## 2. Table Column Structure & Matrix Layout

The interactive matrix presents a frozen multi-column view with 5 sticky base columns on the left and dynamic marketplace channels on the right:

### Pinned Sticky Base Columns (Left)
1. **`Product Name` (280px)**: Product title and SKU details with two-line clamp and full title tooltip (`left: 0px`).
2. **`Brand` (115px)**: Brand or parent manufacturer name (`left: 280px`).
3. **`MFG Price` (115px)**: Sourcing/manufacturing purchase price in BDT (`left: 395px`, right-aligned, blue emphasis).
4. **`Market Avg` (185px)**: Arithmetic mean of all active external listings for that SKU, paired with the **Average Markup % chip** relative to the MFG price (`left: 510px`, dual-metric cell).
5. **`Selling Price` (185px)**: Recommended selling price calculated by the Pricing Engine, accompanied by its **Target Markup % chip** vs MFG price and an optional purple `TUNED` pill when custom per-SKU parameters are active (`left: 695px`, dual-metric cell, elevated shadow divider).

### Dynamic Marketplace Columns (Right)
- Channels: *Arogga, Shajgoj, OhSoGo, Guerniss Official, Bio-Xin Official, Daraz, PandaMart, Neofarmers Official, Skin Cafe Official, Rokomari, Chaldal, Nature Beauty Official, eMartWay*.
- Each cell contains:
  - **Active Selling Price (BDT)**
  - **Semantic Markup % Chip** (relative to MFG Price)
  - **`↗` Deep Link Button** opening the live verified external product page in a new tab.
- **Dynamic Auto-Hiding**: Filtering by brand automatically collapses marketplace columns with 0 listings in the active view, while keeping any column with $\ge 1$ listing visible.

---

## 3. Calculation Logic & Pricing Engine

### A. Sourcing & Channel Markup Percentage
For any channel price $P$ and Manufacturing purchase price $P_{\text{MFG}}$:
$$\text{Markup \%} = \frac{P - P_{\text{MFG}}}{P_{\text{MFG}}} \times 100$$

### B. Pricing Engine Unit Economics Model
The model computes the recommended selling price from variable overheads, target margins, and promotional discounts:

1. **Total Base Cost**:
   $$\text{Overhead} = \text{Packaging} + \text{Transport} + \text{Delivery} + \text{CAC}$$
   $$\text{Total Base Cost} = P_{\text{MFG}} + \text{Overhead}$$

2. **List Price with Margin**:
   $$\text{List Price} = \text{Total Base Cost} \times \left(1 + \frac{\text{Target Margin \%}}{100}\right)$$

3. **Final Selling Price**:
   - **Percentage Discount Mode (`pct`)**:
     $$\text{Selling Price} = \text{List Price} \times \left(1 - \frac{\text{Discount \%}}{100}\right)$$
   - **Amount Discount Mode (`amt`)**:
     $$\text{Selling Price} = \max\left(0, \text{List Price} - \text{Discount BDT}\right)$$

### C. Global vs. Per-Product Override Persistence
- **Global Defaults**: Managed via the top navbar `Pricing Engine` modal (`localStorage` key: `price_matrix_global_params`).
  - Default: Packaging = ৳20, Transport = ৳40, Delivery = ৳60, CAC = ৳80, Margin = 25%, Discount = 10% (pct).
- **Per-Product Custom Overrides**: Configurable inside each product's detail modal under the *Custom Pricing Engine* tab (`localStorage` key: `price_matrix_custom_overrides`). Overrides take immediate precedence for that SKU and persist across browser reloads.

---

## 4. Business Rules & SKU Matching Standards

1. **Strict Brand & SKU Integrity**:
   - Never substitute brands or allow loose keyword matches.
   - Respect parent/sub-brand hierarchy (*Nature Beauty*, *Quinsia*, *Qolore* under *Q Cosmetics*; *Bio-Screen* under *Bio-Xin*).
   - Enforce exact product category disambiguation (Serums ≠ Toners, Conditioners ≠ Shampoos, Cleansers ≠ Moisturizers).
   - Reject multi-item combos, bundles, and BOGO promotions unless the target SKU is explicitly a combo.
   - Enforce volume/weight equivalence (`ml`, `gm`, `g`).
   - Require exact cosmetic shade matching (*03, 05, Natural 07, Ivory Pink, NC 10, NC 20*).

2. **Discounted / Selling Price Priority**:
   - Always extract the active customer checkout price (discounted selling price) over the list price or MSRP whenever promotions are active.

3. **Internal Pricing Parity**:
   - Keep internal Excel pricing columns (`MFG price`, `Mkt (Avg) Price`) 100% faithful to workbook calculations without drift.
   - Exclude internal raw cost rollups from public user-facing tables.

---

## 5. UI/UX Design System & Conventions

- **Typography**: `Plus Jakarta Sans` for titles/headings and `Inter` for all UI elements, numerical prices, headers, and modals. Monospace fonts are prohibited.
- **Markup Percentage Chip Hierarchy**:
  - `Below MFG (Discount)`: Soft red pill (`#fee2e2` bg, `#991b1b` text) with down arrow `↓-XX%`.
  - `At Par (0%)`: Neutral gray pill (`#f1f5f9` bg, `#475569` text) `0%`.
  - `+1% to +15%`: Soft blue pill (`#e0f2fe` bg, `#0369a1` text) `↑+XX%`.
  - `+15% to +35%`: Soft amber pill (`#fef3c7` bg, `#92400e` text) `↑+XX%`.
  - `+35% to +60%`: Warm orange pill (`#ffedd5` bg, `#9a3412` text) `↑+XX%`.
  - `>+60% Extreme`: Soft red pill (`#fee2e2` bg, `#991b1b` text) `↑+XX%`.
- **Top Navigation Bar (56px)**:
  - Brand header with active indicator dot.
  - SKU & listing count metadata pill.
  - Search input with auto-filtering.
  - Brand filter dropdown.
  - Channel filter dropdown.
  - Multi-criteria sort dropdown (Product A-Z/Z-A, Brand A-Z, Selling Price, MFG Price, Market Avg, Most Channels, Largest Spread, Channel-specific sorts).
  - `Pricing Engine` action button.
  - Icon-only JSON dataset export button.
- **Interactive Header Controls**:
  - All table headers display descriptive tooltips on hover explaining column contents and unit logic.
  - Clicking any column header triggers interactive multi-state sorting.

---

## 6. Development Setup & Commands

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

---

## 7. Permissions & Safety
- **Allowed without prompting**: File edits, running `build_matrix.py`, scraping via `primp`/`ddgs`, deployment to Cloudflare Pages.
- **Require approval**: Direct force-push to remote branches, destructive file removal outside temporary directories.
