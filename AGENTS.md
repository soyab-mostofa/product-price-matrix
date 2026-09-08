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
- **Serverless API**: Hono Cloudflare Pages Worker (`src/index.tsx`) with routes for `/api/auth`, `/api/products`, `/api/engine`, `/api/overrides`, `/api/prices` (admin price edits + reverts), and `/api/export.xlsx` (admin-only workbook export)
- **Data & Excel**: `openpyxl`, `pandas`
- **Scraping & Networking**: `primp` (TLS fingerprint impersonation for Cloudflare bypass), `BeautifulSoup4`, `ddgs`
- **Matching & Similarity**: `rapidfuzz`
- **Deployment & Hosting**: Cloudflare Pages (via `wrangler`), GitHub

### Core Artifacts
- `Roopelle.com Final Excel Sheet.xlsx` — **The commercial source of truth.** Five sheets: `Local product ` (372 rows: MRP, discount rate, formula-driven Final Price), `local product Orgagenic` (35 rows: MRP, distributor price, distributor profit), and `imported Skincare` / `imported Haircare` / `imported Fregrance` (189 rows: cost + channel prices). `build_matrix.py` reads cached `data_only=True` values: Local `G = D − (D×E) + (D×F)` is imported as the static Source Cost scalar; Orgagenic `E` is the static Distributor Price. Columns E/F on the first local sheet, Orgagenic Category/Image Link, and imported Out of Stock are not stored in the public D1 product shape.
- `product_marketplace_price_comparison.xlsx` — Older working spreadsheet with the original Price Calculator formulas (`MFG = MRP − MRP×discount`; `Cost = MFG + Packaging 20 + Transport 40`). Superseded by the Roopelle sheet for pricing; kept for provenance.
- `verified_marketplace_research.json` — Comprehensive JSON dataset with candidate records, tokens, and multi-channel mappings. `excel_prices` mirrors the workbook and must never be overwritten by scraped values.
- `verified_match_audit.json` — Full audit log of accepted matches and rejected candidates with explicit reasons.
- `build_matrix.py` / `catalog_builder.py` — Pipeline that validates listings and regenerates canonical JSON, audit, and D1 seed artifacts (`seed.sql`).
- `scripts/restore_workbook_mrp.py` — One-shot repair that restores `excel_prices.market_average_price` from the workbook. Run if a scraper ever overwrites the benchmark again.
- `scripts/verify_workbook_parity.py` — **The reconciliation gate.** Asserts every SKU's immutable workbook baselines (`workbook_source_cost` / `workbook_mrp`) equal the workbook to the paisa, that no SKU/row_id/(SKU,channel) is duplicated, and that every product carries its sheet + Excel row. Reads the **local replica only**. Exits non-zero on any drift.
- `scripts/verify_live_workbook_parity.py` — The same parity question asked of **live production** over HTTPS, keyed on each SKU's recorded (sheet, row) provenance. The local gate cannot see an edit made against the deployed site, a partial deploy, or an unsynced remote D1 — production once held an edited Source Cost for ~7 hours with every local check passing. `--allow-edited` reports only *unexplained* drift.
- `scripts/audit_all_listings.py` — Checks every verified listing three ways: reachable (no 404), identical after redirects (the Arogga `pv_id` class of bug), and still accepted by `sku_matcher`. Writes `/tmp/listing_audit.json`.
- `scripts/verify_live_links.py` — The same reachability/identity check against the **live production API**, so a bad deploy or an unsynced remote D1 is caught, not just a bad local file.
- `scripts/purge_rejected_listings.py` — Deletes listings the hardened matcher now rejects; recovers a dropped candidate size from the live channel and re-validates before deleting.
- `scripts/fold_d1_listings_into_research.py` — Folds scraper-discovered listings from D1 back into `verified_marketplace_research.json`, re-validating each. **Run after any discovery pass**, or the next `build_matrix.py` silently undoes it.
- `scripts/verify_scrape_survived.py` — Parses a scraper log and confirms every reported match actually reached the research file, the local replica, **and** live production. A scraper's own "+N new listings" line is not evidence the data survived.
- `scripts/stamp_workbook_provenance.py` — Stamps each local SKU with its workbook sheet and Excel row.
- `sku_matcher.py` — Strict brand, category, volume, bundle, concentration, and cosmetic shade validation engine.
- `src/` — Hono JSX application, API routes, browser client, and server domain modules.
- `public/static/app.css` — Authored browser stylesheet; `public/static/app.js` is generated and ignored.
- `dist/` — Generated production Worker bundle and static assets, deployed to Cloudflare Pages.
- `product_pricing_data.json` — Clean JSON data schema for frontend consumption.

---

## 2. Table Column Structure & Matrix Layout

The interactive matrix presents a frozen multi-column view with 5 sticky base columns on the left and dynamic marketplace channels on the right:

Every column head carries a small-caps label over a **basis line** naming the unit and comparison basis (`BDT / unit`, `BDT · vs cost`, `BDT · engine output`), so a percentage never needs a tooltip to be legible. Widths are CSS custom properties (`--col-product` etc. in `app.css`), and each sticky column's `left` offset is derived from them rather than hard-coded.

### Pinned Sticky Base Columns (Left)
1. **`Product` (`--col-product`, 300px)**: Product title with the pack size beneath it in a ruled marker, two-line clamp and full title tooltip. The size line is load-bearing — the catalog holds same-name SKUs that differ only by pack size (Nature Beauty Body Lotion 200/370ml; Orgagenic White Sandalwood 50/100g). 22 local SKUs carry an empty size and correctly render no marker.
2. **`Brand` (`--col-brand`, 128px)**: Brand or parent manufacturer name.
3. **`Source Cost` (`--col-mfg`, 124px)**: What we pay to acquire one unit, in BDT — the discounted manufacturer price for a Local SKU, the importer's quoted price for an Imported SKU (right-aligned). Stored in the `manufactured_price` column for historical reasons; see `CONTEXT.md`.
4. **`MRP` (`--col-market`, 196px)**: The market reference price, paired with a markup chip relative to Source Cost (dual-metric cell). For a **Local SKU this is always the workbook benchmark** (`mrp_source_type = 'workbook'`); for an **Imported SKU** it resolves official → third-party average → reference.
5. **`Selling Price` (`--col-selling`, 210px)**: Recommended selling price from the Pricing Engine in assay green, with its **Target Markup % chip** vs Source Cost (which turns solid crimson with white text when the recommendation exceeds the MRP), and an optional violet `TUNED` pill when per-SKU parameters are active. Closed on its right by the **datum rule** — a 1px graphite border plus `--shadow-datum` — separating what we know from what the market is doing.

**Prices are rounded for display; chips are derived from the rounded price.** `calculateSellingPrice` returns a whole number, and every percentage is computed from that displayed value against the *unrounded* source cost. A SKU costing ৳93.6 displays `BDT 94` but its chips read against 93.6 — so hand-checking a chip against the displayed cost will look off by a point. This is deliberate: the chip always describes the number on screen.

### Dynamic Marketplace Columns (Right)
- Channel order (`CHANNEL_ORDER` in `catalog_builder.py` and `src/server/catalog.ts`): *Official Store, Arogga, Shajgoj, OhSoGo, Daraz, eMartWay, PandaMart, Rokomari, Chaldal, Klassy Missy, Skincarebd, themallbd, Skinplus*. Unknown channels discovered later sort alphabetically after these.
- Each cell contains:
  - **Active Selling Price (BDT)**
  - **Semantic Markup % Chip** (relative to Source Cost)
  - **Drawn external-link icon** opening the live verified product page in a new tab, or a dashed-circle marker when the price is recorded but no product page is confirmed. No unicode glyph stands in for an icon anywhere in the UI; the set lives in `src/components/icons.tsx` (JSX) and `src/client/icons.ts` (innerHTML strings), one stroke weight throughout.
- A channel with no listing for a SKU renders a quiet dash on a recessed ground rather than an empty full-weight cell.
- **Dynamic Auto-Hiding**: Filtering by brand collapses marketplace columns with 0 listings in the active view, keeping any column with $\ge 1$ listing visible.

---

## 3. Calculation Logic & Pricing Engine

### A. Sourcing & Channel Markup Percentage
For any channel price $P$ and Source Cost $C$:
$$\text{Markup \%} = \frac{P - C}{C} \times 100$$

### B. Pricing Engine Unit Economics Model
The model computes the recommended selling price from variable overheads, target margins, and promotional discounts:

1. **Total Base Cost**:
   CAC resolves by mode — flat BDT under `cacType: 'amt'`, or a share of the SKU's own sourcing price under `'pct'`:
   $$\text{CAC} = \begin{cases} \text{cac} & \text{cacType} = \texttt{amt} \\ C \times \frac{\text{cac}}{100} & \text{cacType} = \texttt{pct} \end{cases}$$
   $$\text{Overhead} = \text{Packaging} + \text{Transport} + \text{Delivery} + \text{CAC}$$
   $$\text{Total Base Cost} = C + \text{Overhead}$$

   Under `pct`, overhead is a **function of the SKU**, not of the engine parameters alone. Every surface that shows an overhead figure must go through `totalOverhead()` / `resolveCac()` in `src/shared/pricing.ts`; a locally re-summed constant drifts away from the price printed beside it.

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
  - Shipped default: Packaging = ৳45, Transport = ৳0, Delivery = ৳0, CAC = **5% of the sourcing price** (`cacType: 'pct'`), Margin = 0%, Discount = 0% (pct), defined once in `src/shared/pricing.ts` (`PRICING_DEFAULTS`) and mirrored in `schema.sql` and `catalog_builder.py`. CAC is a percentage rather than a flat figure because a flat ৳40 exceeded the entire trade-discount headroom on the cheapest SKUs; 5% stays proportional across the whole catalog. Overhead is therefore a function of the SKU, not of the engine parameters alone — always read it through `totalOverhead()` / `resolveCac()`.
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
   - **The recompute must be origin-scoped.** A discovery pass recomputes `market_average_price` from listings — correct for imported SKUs, corrupting for local ones. Every `UPDATE products ... mrp_source_type` in a scraper ends `WHERE row_id = ?1 AND sourcing_origin = 'imported'`. An unguarded one silently rewrote 71 local benchmarks, each *below* the workbook because it had been replaced by a promotional price. `tests/test_mrp_recompute_guard.py` pins the filter in the SQL text.

5. **Workbook Traceability**:
   - Every product carries `source_sheet` and `source_row` — the sheet it was read from and the **1-based Excel row** (headers are row 1, data starts at row 2), so a figure on screen can be typed into Excel's Name Box and land on its cell.
   - Reconcile with `uv run --with openpyxl --with rapidfuzz python3 scripts/verify_workbook_parity.py`. It must print `PASS — 0 problem(s)` before any deploy that touches pricing.
   - Workbook lookups key on **(name, size)**, never name alone: the catalog holds same-name SKUs differing only by pack size (Nature Beauty Healthy Glowing Body Lotion 200/370ml; Orgagenic White Sandalwood 50/100g), and a name-only key silently compares a SKU against its sibling's price.

6. **Never coerce a number out of a JSON body**:
   - Numeric fields read from a **JSON request body** use `z.number()`. Only **query-string** fields use `z.coerce.number()` (`productRowIdParamSchema`), because a query value is text by definition.
   - `z.coerce.number()` on a body accepts anything `Number()` swallows: `null` and `[]` become `0`, `true` becomes `1`, `"12"` becomes `12` — and the endpoint answers `200` as though the edit were intended. A fabricated **0 is the damaging case**: it is a legal price that satisfies every CHECK constraint, so it reaches `products`, journals a real edit, and leaves the SKU unpriceable (`calculateSellingPrice` returns `null` at cost ≤ 0 and every markup chip blanks).
   - Pinned by `tests/pricing.test.ts` ("a JSON body must carry real numbers") and `tests/prices.test.ts` ("a non-numeric price is rejected, never coerced into a figure"), which also assert the write never lands and the journal stays empty.

---

## 5. UI/UX Design System & Conventions

The visual world is a **certificate-of-analysis assay sheet**: a price recommendation is a measured result, the MRP is its specification limit, and channel listings are replicate measurements. `DESIGN.md` is the authority — tokens in machine-readable frontmatter, then the prose. Read it before any UI change rather than re-deriving the rules from neighbouring code. `.impeccable/surfaces/` holds the direction contract.

**Non-negotiables** (the design detector enforces the first three):
- **0px radius everywhere.** Buttons, inputs, chips, dialogs, banners, markers. No exceptions.
- **Every colour and type step is a documented token.** A literal hex or an off-ramp `font-size` is a finding — add the token to both `app.css` and `DESIGN.md`, or use an existing one.
- **No coloured side-border above 1px**, and no unicode glyph standing in for an icon. The icon set lives in `src/components/icons.tsx` (JSX) and `src/client/icons.ts` (innerHTML strings), one stroke weight throughout.
- **Tabular lining figures** (`tabular-nums lining-nums`) on every number, including inside inputs and chips.
- **`--ink-4` is for marks, not text** — it sits below 4.5:1. Basis lines and other small copy use `--ink-35` or darker. Measure contrast; do not eyeball it.

- **Typography**: `Plus Jakarta Sans` for the wordmark and dialog titles, `Inter` for everything else. Monospace is prohibited — Inter's tabular figures do the alignment work.
- **Markup chip ramp** — an ordered scale where both ends alarm, not six unrelated tags. All relative to Source Cost:

  | Band | Background | Text | Reads as |
  | --- | --- | --- | --- |
  | Below cost | `#fbedec` | `#8f1d1d` | Loss |
  | At par (0%) | `#f1f1ee` | `#4a4f56` | Neutral |
  | +1 to +15% | `#eef4f1` | `#2c5f4d` | Thin |
  | +15 to +35% | `#e2f0e8` | `#14614a` | Healthy |
  | +35 to +60% | `#f6eedb` | `#78530f` | Rich |
  | Above +60% | `#f6e4da` | `#8a3b14` | Extreme |

- **Above-Market Warning**: when a recommended Selling Price exceeds the MRP, its chip turns solid crimson (`#b32020`) with white text — a *failed measurement* that overrides the ramp entirely, not a seventh tier. A catalog-level banner reports how many of the shown SKUs are affected. Never render an unsellable recommendation as if it were valid.
- **Two-tier ruled header (46px per tier)**:
  - *Register tier*: brand wordmark with sync lamp, SKU/listing count pill, the two sourcing books as docked tabs, the out-of-spec filter, `Admin Login` (hidden when auth is unconfigured; becomes `Log out`), icon-only JSON export, and the `Pricing engine` action.
  - *Instrument tier*: search (debounced ~140ms — a repaint rebuilds every visible cell), brand filter, channel filter, category filter (imported book only; hidden when the active book has no categories), multi-criteria sort (Product A-Z/Z-A, Brand A-Z/Z-A, Selling Price, Source Cost, MRP, Most Channels, Largest Spread, channel-specific sorts), and the markup/market-discount compare cord.
  - Each control owns its left rule, so no boundary is drawn twice.
- **Origin switch**: the two books dock into the header rule as tabs, the active one carrying a 2px assay-green underline. They navigate real routes (`/` and `/imported`) rather than filtering in place, so each book stays bookmarkable, and each carries its own SKU count.
- **The out-of-spec flag is a button, not a readout.** It names its action (`Show 51 above market` → `Showing`) and filters the sheet. It counts across the whole book, never the current view: filtering to one brand must not make a catalog-wide pricing failure look like it went away.
- **Inline counts need accessible names.** A numeral abutting its label announces as `"Local407"`. Wrap the count in `aria-hidden` and put the real sentence in `aria-label`, keeping it in sync when the count changes.
- **Destructive Actions**: irreversible catalog-wide actions live in a labelled danger zone with a type-`RESET`-to-confirm prompt that states how many tunes will be lost. Never an unlabelled icon button beside a save action.
- **Interactive Header Controls**: every column head carries a descriptive tooltip explaining its contents and unit logic; clicking any head triggers multi-state sorting with `aria-sort` reflecting the state.

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

# Fold scraper-discovered listings back into the research file
# (run after any discovery pass, BEFORE build_matrix.py)
uv run --with rapidfuzz python3 scripts/fold_d1_listings_into_research.py

# Apply pending migrations to the local D1 replicas
bun run db:local:migrate
```

### Data Integrity Checks
```bash
# Workbook parity + duplicates + row traceability — must print PASS
uv run --with openpyxl --with rapidfuzz python3 scripts/verify_workbook_parity.py

# Every verified listing: reachable, same product after redirects, still matches
uv run --with rapidfuzz python3 scripts/audit_all_listings.py

# Delete listings the hardened matcher rejects; recover dropped sizes first
uv run --with rapidfuzz --with openpyxl python3 scripts/purge_rejected_listings.py

# The same link check against LIVE production
uv run python3 scripts/verify_live_links.py

# Workbook parity against LIVE production — catches drift the local gate cannot
# see (an edit made against the deployed site, a partial deploy, an unsynced
# remote D1). verify_workbook_parity.py only ever reads the local replica.
uv run --with openpyxl --with rapidfuzz python3 scripts/verify_live_workbook_parity.py
```

### Discovery Pipeline Order (non-negotiable)
Scrapers write into the D1 replicas, but `seed.sql` **deletes every local
listing** before re-inserting from `verified_marketplace_research.json`. Sync
before folding and the run is silently reverted — this destroyed 80 freshly
verified listings once, with every command reporting success.

```bash
# 1. discover
uv run --with rapidfuzz --with openpyxl python3 scripts/scrape_missing.py --origin all
# 2. fold into the canonical artifact — BEFORE any sync
uv run --with rapidfuzz python3 scripts/fold_d1_listings_into_research.py
# 3. rebuild seed.sql from the now-complete research file
uv run --with openpyxl --with rapidfuzz python3 build_matrix.py
# 4. only now sync the replicas
bun run db:local:sync
# 5. prove the findings survived to production
uv run python3 scripts/verify_scrape_survived.py
```

`db:local:sync` refuses to run when the replica holds verified local listings
the seed does not carry, naming them and exiting non-zero (`--force` discards
them deliberately). `tests/test_sync_guard.py` pins that behaviour.

### Verification (run before claiming work is done)
```bash
bun run typecheck   # tsc --noEmit
bun run test        # 115 Bun unit tests + 134 Python tests
bun run build       # client bundle + Worker bundle
bun run dev         # local dev server on :5173
bun run test:audit  # 6 browser audits against a running dev server
```

The audits in `tests/audit/` drive a real browser and recompute what was
painted from the raw API, so a rendering bug fails there even when the unit
tests pass. `actions.mjs` is the only one that writes: it drives login, the
global engine, per-SKU tunes and both reset controls, then restores the global
params and every pre-existing override it found. It needs the admin password
(from `.dev.vars`, or `AUDIT_ADMIN_PASSWORD`) and skips cleanly without one.

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
