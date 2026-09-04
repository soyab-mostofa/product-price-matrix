# Project: Product Price Intelligence & Marketplace Benchmark Matrix

Price benchmark dataset, automated multi-marketplace discovery pipeline, and interactive dashboard for personal care and beauty SKUs across major Bangladeshi D2C brand flagships and third-party e-commerce channels.

The catalog is split into two books by **Sourcing Origin**, each on its own route:

| Book | Route | SKUs | MRP source |
| --- | --- | --- | --- |
| **Local** — made in Bangladesh, bought from the manufacturer | `/` | 407 | Workbook benchmark (always) |
| **Imported** — brought in, bought from an importer | `/imported` | 189 | Live listings (official → third-party avg → reference) |

No single view shows the combined total; the origin switch carries both counts.

- **Live Production URL**: https://product-price-matrix.pages.dev
- **Repository**: https://github.com/soyab-mostofa/product-price-matrix

---

## 1. Technology Stack & Architecture

- **Runtime**: Python 3.12+ (uv / pip), Node.js (Bun 1.3+)
- **Database & Storage**: Cloudflare D1 (Serverless SQLite at the edge, DB name: `product-price-matrix-db`, UUID: `78a79d0b-20b4-4b3f-b0bf-d2d0e97c9990`)
- **Serverless API**: Hono Cloudflare Pages Worker (`src/index.tsx`) with routes for `/api/auth`, `/api/engine`, `/api/overrides`, and `/api/products`
- **Data & Excel**: `openpyxl`, `pandas`
- **Scraping & Networking**: `primp` (TLS fingerprint impersonation for Cloudflare bypass), `BeautifulSoup4`, `ddgs`
- **Matching & Similarity**: `rapidfuzz`
- **Deployment & Hosting**: Cloudflare Pages (via `wrangler`), GitHub

### Core Artifacts
- `Roopelle.com Final Excel Sheet.xlsx` — **The commercial source of truth.** Five sheets: `Local product ` (372 rows: MRP, discount rate, final sourcing price), `local product Orgagenic` (35 rows: MRP, distributor price, distributor profit), and `imported Skincare` / `imported Haircare` / `imported Fregrance` (189 rows: cost + channel prices).
- `product_marketplace_price_comparison.xlsx` — Older working spreadsheet with the original Price Calculator formulas (`MFG = MRP − MRP×discount`; `Cost = MFG + Packaging 20 + Transport 40`). Superseded by the Roopelle sheet for pricing; kept for provenance.
- `verified_marketplace_research.json` — Comprehensive JSON dataset with candidate records, tokens, and multi-channel mappings. `excel_prices` mirrors the workbook and must never be overwritten by scraped values.
- `verified_match_audit.json` — Full audit log of accepted matches and rejected candidates with explicit reasons.
- `build_matrix.py` / `catalog_builder.py` — Pipeline that validates listings and regenerates canonical JSON, audit, and D1 seed artifacts (`seed.sql`).
- `scripts/restore_workbook_mrp.py` — One-shot repair that restores `excel_prices.market_average_price` from the workbook. Run if a scraper ever overwrites the benchmark again.
- `sku_matcher.py` — Strict brand, category, volume, bundle, concentration, and cosmetic shade validation engine.
- `src/` — Hono JSX application, API routes, browser client, and server domain modules.
- `public/static/app.css` — Authored browser stylesheet; `public/static/app.js` is generated and ignored.
- `dist/` — Generated production Worker bundle and static assets, deployed to Cloudflare Pages.
- `product_pricing_data.json` — Clean JSON data schema for frontend consumption.

---

## 2. Table Column Structure & Matrix Layout

The interactive matrix presents a frozen multi-column view with 5 sticky base columns on the left and dynamic marketplace channels on the right:

### Pinned Sticky Base Columns (Left)
1. **`Product Name` (280px)**: Product title with the pack size beneath it, two-line clamp and full title tooltip (`left: 0px`). The size line is load-bearing — the catalog holds same-name SKUs that differ only by pack size (Nature Beauty Body Lotion 200/370ml; Orgagenic White Sandalwood 50/100g).
2. **`Brand` (115px)**: Brand or parent manufacturer name (`left: 280px`).
3. **`Source Cost` (115px)**: What we pay to acquire one unit, in BDT — the discounted manufacturer price for a Local SKU, the importer's quoted price for an Imported SKU (`left: 395px`, right-aligned, blue emphasis). Stored in the `manufactured_price` column for historical reasons; see `CONTEXT.md`.
4. **`MRP` (185px)**: The market reference price, paired with a markup chip relative to Source Cost (`left: 510px`, dual-metric cell). For a **Local SKU this is always the workbook benchmark** (`mrp_source_type = 'workbook'`); for an **Imported SKU** it resolves official → third-party average → reference.
5. **`Selling Price` (185px)**: Recommended selling price from the Pricing Engine, with its **Target Markup % chip** vs Source Cost, an optional purple `TUNED` pill when per-SKU parameters are active, and a red `ABOVE MARKET` flag when the recommendation exceeds the MRP (`left: 695px`, dual-metric cell, elevated shadow divider).

### Dynamic Marketplace Columns (Right)
- Channel order (`CHANNEL_ORDER` in `catalog_builder.py` and `src/server/catalog.ts`): *Official Store, Arogga, Shajgoj, OhSoGo, Daraz, eMartWay, PandaMart, Rokomari, Chaldal, Klassy Missy, Skincarebd, themallbd, Skinplus*. Unknown channels discovered later sort alphabetically after these.
- Each cell contains:
  - **Active Selling Price (BDT)**
  - **Semantic Markup % Chip** (relative to Source Cost)
  - **`↗` Deep Link Button** opening the live verified product page in a new tab, or a `◌` marker when the price is recorded but no product page is confirmed.
- **Dynamic Auto-Hiding**: Filtering by brand collapses marketplace columns with 0 listings in the active view, keeping any column with $\ge 1$ listing visible.

---

## 3. Calculation Logic & Pricing Engine

### A. Sourcing & Channel Markup Percentage
For any channel price $P$ and Source Cost $C$:
$$\text{Markup \%} = \frac{P - C}{C} \times 100$$

### B. Pricing Engine Unit Economics Model
The model computes the recommended selling price from variable overheads, target margins, and promotional discounts:

1. **Total Base Cost**:
   $$\text{Overhead} = \text{Packaging} + \text{Transport} + \text{Delivery} + \text{CAC}$$
   $$\text{Total Base Cost} = C + \text{Overhead}$$

2. **List Price with Gross Margin**:
   $$\text{List Price} = \frac{\text{Total Base Cost}}{1 - \frac{\text{Target Margin \%}}{100}}$$

3. **Final Selling Price**:
   - **Percentage Discount Mode (`pct`)**:
     $$\text{Selling Price} = \text{List Price} \times \left(1 - \frac{\text{Discount \%}}{100}\right)$$
   - **Amount Discount Mode (`amt`)**:
     $$\text{Selling Price} = \max\left(0, \text{List Price} - \text{Discount BDT}\right)$$

> **Overhead is charged per unit.** Delivery and CAC are order-level costs, so
> loading their full value onto every unit prices cheap SKUs out of their own
> market: the cost basis is a trade discount off MRP (17–40%), leaving a headroom
> proportional to price — as little as ৳12 on the cheapest SKUs. Shipping ৳145/unit
> (packaging 45 + delivery 60 + CAC 40) put 243 of 407 SKUs above market. If you
> reintroduce delivery or CAC, amortise them across expected units per order.

### C. Global vs. Per-Product Override Persistence
Both are persisted **in Cloudflare D1 only** — there is no `localStorage` anywhere in the codebase.

- **Global Defaults**: Managed via the top navbar `Pricing Engine` modal, stored in D1 `global_pricing_params` (single row, `id = 1`).
  - Shipped default: Packaging = ৳45, Transport = ৳0, Delivery = ৳0, CAC = ৳40, Margin = 0%, Discount = 0% (pct) — **৳85/unit**, defined once in `src/shared/pricing.ts` (`PRICING_DEFAULTS`) and mirrored in `schema.sql` and `catalog_builder.py`.
- **Per-Product Custom Overrides**: Configurable in each product's detail modal under the *Custom Pricing Engine* tab, stored in D1 `product_pricing_overrides` keyed by immutable `product_row_id`.
  - Overrides are **sparse**: a `NULL` column means "inherit the current global value", so raising a global cost still reaches tuned SKUs for knobs they never pinned. A field equal to the current global value is stripped on save (`sparsifyOverride`); an override pinning nothing is deleted rather than stored.
  - `discount_type` and `discount_val` pin as a pair or not at all.

### D. Access Control
- **Reads are public**: `GET /`, `/imported`, `/api/products`, `/api/engine`, `/api/auth`.
- **Writes require an admin session**: `POST /api/engine` and every `/api/overrides` route are behind `requireAdmin`, which enforces a valid HMAC session cookie **and** a same-origin `X-Price-Matrix-Admin: 1` header. Failed logins are rate-limited via `admin_login_attempts` (5 attempts / 15 min).
- Requires `ADMIN_PASSWORD` and `SESSION_SECRET` bindings. Without them, mutations return `503` and the UI shows a read-only banner.

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

3. **Internal Pricing Parity — the workbook wins**:
   - `Roopelle.com Final Excel Sheet.xlsx` is the commercial source of truth. Keep `excel_prices.manufactured_price` and `excel_prices.market_average_price` 100% faithful to it, with no drift.
   - **A Local SKU's MRP is always the workbook benchmark** (`mrp_source_type = 'workbook'`). Never let a scraped price — including the brand's own Official Store — overwrite it. The workbook's cost basis is a trade discount off exactly that number (40% / 30% / 25%, giving cost/MRP ratios of 0.60 / 0.70 / 0.75), so substituting a live price breaks the arithmetic. Brand stores run promotions: 82 of 179 official prices disagreed with the workbook, and 6 sat *below* our sourcing cost, making healthy margins read as losses.
   - Scraped listings are still first-class: they keep their prices, verification state, and deep links, and render in their own channel columns. They are compared *against* the benchmark, never merged *into* it.
   - Imported SKUs are the exception — an importer's quoted cost carries no workbook retail benchmark, so their MRP still resolves official → third-party average → reference.
   - Exclude internal raw cost rollups from public user-facing tables.

4. **Data Repair**:
   - If a scraper ever overwrites the benchmark again, run `uv run --with openpyxl python3 scripts/restore_workbook_mrp.py` then rebuild. The `tests/model.test.ts` suite asserts every local MRP equals its workbook value, so a regression fails CI.

---

## 5. UI/UX Design System & Conventions

- **Typography**: `Plus Jakarta Sans` for titles/headings and `Inter` for all UI elements, numerical prices, headers, and modals. Monospace fonts are prohibited.
- **Markup Percentage Chip Hierarchy** (all relative to Source Cost):
  - `Below Source Cost (Discount)`: Soft red pill (`#fee2e2` bg, `#991b1b` text) with down arrow `↓-XX%`.
  - `At Par (0%)`: Neutral gray pill (`#f1f5f9` bg, `#475569` text) `0%`.
  - `+1% to +15%`: Soft blue pill (`#e0f2fe` bg, `#0369a1` text) `↑+XX%`.
  - `+15% to +35%`: Soft amber pill (`#fef3c7` bg, `#92400e` text) `↑+XX%`.
  - `+35% to +60%`: Warm orange pill (`#ffedd5` bg, `#9a3412` text) `↑+XX%`.
  - `>+60% Extreme`: Soft red pill (`#fee2e2` bg, `#991b1b` text) `↑+XX%`.
- **Above-Market Warning**: When a recommended Selling Price exceeds the MRP, the price turns red and gains an `ABOVE MARKET` flag; a catalog-level amber banner reports how many of the shown SKUs are affected. Never render an unsellable recommendation as if it were valid.
- **Top Navigation Bar (56px)**:
  - Brand header with active indicator dot.
  - SKU & listing count metadata pill.
  - Search input (debounced ~140ms — a repaint rebuilds every visible cell).
  - Brand filter dropdown.
  - Channel filter dropdown.
  - Category filter dropdown (imported book only; hidden when the active book has no categories).
  - Multi-criteria sort dropdown (Product A-Z/Z-A, Brand A-Z/Z-A, Selling Price, Source Cost, MRP, Most Channels, Largest Spread, Channel-specific sorts).
  - Markup/market-discount chip toggle.
  - `Admin Login` button (hidden when auth is not configured; becomes `Log out` when signed in).
  - `Pricing Engine` action button.
  - Icon-only JSON dataset export button.
- **Origin Switch**: A floating pill switching between the Local and Imported books. It navigates real routes (`/` and `/imported`) rather than filtering in place, so each book stays bookmarkable, and carries both SKU counts.
- **Destructive Actions**: Irreversible catalog-wide actions live in a labelled danger zone with a type-`RESET`-to-confirm prompt that states how many tunes will be lost. Never an unlabelled icon button beside a save action.
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
# Rebuild datasets and UI artifacts from verified_marketplace_research.json
uv run --with openpyxl --with rapidfuzz python3 build_matrix.py

# Restore workbook MRP benchmarks if a scraper overwrote them
uv run --with openpyxl python3 scripts/restore_workbook_mrp.py

# Apply pending migrations to the local D1 replicas
bun run db:local:migrate
```

### Verification (run before claiming work is done)
```bash
bun run typecheck   # tsc --noEmit
bun run test        # 50 Bun unit tests + 56 Python tests
bun run build       # client bundle + Worker bundle
bun run dev         # local dev server on :5173
```

### Deployment Commands
```bash
# Build production bundle and artifacts
bun run build

# Deploy to Cloudflare Pages production
bunx wrangler pages deploy dist --project-name product-price-matrix --commit-dirty=true
```

Admin auth requires two secrets on the Pages project:
```bash
bunx wrangler pages secret put ADMIN_PASSWORD --project-name product-price-matrix
bunx wrangler pages secret put SESSION_SECRET --project-name product-price-matrix
```

---

## 7. Permissions & Safety
- **Allowed without prompting**: File edits, running `build_matrix.py`, scraping via `primp`/`ddgs`, deployment to Cloudflare Pages.
- **Require approval**: Direct force-push to remote branches, destructive file removal outside temporary directories.

---

## Agent skills

### Issue tracker

Issues and specs live as GitHub issues in `soyab-mostofa/product-price-matrix`, managed with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, each label string equal to its name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
