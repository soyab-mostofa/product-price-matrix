# Spec: Sourcing origin — split the catalog into Local and Imported SKUs

## Problem Statement

The catalog shows 407 SKUs on a single page, and every one of them is a Local SKU — manufactured in Bangladesh, sourced direct from the manufacturer at a discounted manufacturer price. There is now a second, entirely separate book of business: 189 Imported SKUs sourced from importers, whose cost basis is the importer's quoted price with no manufacturer discount to apply.

Today there is nowhere to put them. Nothing in the schema records how a SKU is sourced, so the two books would land in one undifferentiated list where a CeraVe cleanser bought from an importer sits beside a Guerniss lipstick bought from its manufacturer, with no way to tell them apart, filter between them, or compare their margins as separate businesses. The imported set also arrives without the marketplace price research the local set already has: only 56 of 189 rows carry any competitor prices at all.

## Solution

Sourcing Origin becomes a first-class axis of the catalog. Every product is either `local` or `imported`, the 407 existing SKUs are all `local`, and the dashboard splits into two bookmarkable pages — `/` for Local SKUs and `/imported` for Imported SKUs — joined by a floating segmented pill at the bottom of the screen that shows a live count per side and switches between them.

The 189 Imported SKUs are seeded from the source workbook, with brand and size derived from the product name (neither exists as its own column) and category taken from the tab the row came from. The competitor prices already present in the workbook are seeded as unverified listings, and the discovery pipeline then scrapes the imported catalog to fill the 133 rows that have no prices and attach verified deep links to those that do.

The Pricing Engine does not change. It reads one Source Cost per SKU and applies identical overhead, margin, and discount arithmetic to both books.

## User Stories

1. As a pricing analyst, I want the catalog split into Local and Imported pages, so that I can reason about two different sourcing businesses without them contaminating each other's numbers.
2. As a pricing analyst, I want to switch between Local and Imported with a single click on a floating pill, so that comparing the two books costs me no navigation effort.
3. As a pricing analyst, I want each page to have its own URL, so that I can bookmark the imported book and share a link to it with a colleague.
4. As a pricing analyst, I want the floating pill to show how many SKUs are on each side, so that I know the size of each book without leaving the page I'm on.
5. As a pricing analyst, I want the other page's data prefetched in the background, so that switching feels instant even though each page loads only its own SKUs.
6. As a pricing analyst, I want every one of the 407 existing SKUs to be marked as Local automatically, so that the split requires no manual reclassification.
7. As a pricing analyst, I want the 189 Imported SKUs loaded from the source workbook, so that the imported book is populated without manual data entry.
8. As a pricing analyst, I want each Imported SKU's brand derived from its product name, so that the brand filter works on the imported page even though the workbook has no brand column.
9. As a pricing analyst, I want brand spellings canonicalised, so that `L'Oreal` and `LOreal` are one entry in the brand filter rather than two.
10. As a pricing analyst, I want the misspelling `Beauty Of Jiseon` corrected to `Beauty of Joseon`, so that a source typo does not become a phantom brand.
11. As a pricing analyst, I want `Nature Beauty` mapped under its parent `Q Cosmetics`, so that the established parent/sub-brand hierarchy is respected on both books.
12. As a pricing analyst, I want each Imported SKU's size parsed from its product name, so that volume equivalence can be enforced when matching listings.
13. As a pricing analyst, I want sizes written with a Unicode capital-I (`330mI`, `100mI`) parsed correctly as millilitres, so that six SKUs are not silently left without a size.
14. As a pricing analyst, I want each Imported SKU to carry its category (Skincare, Haircare, Fragrance), so that I can narrow the imported book by product type.
15. As a pricing analyst, I want a category filter in the header, so that I can view only Haircare across whichever book I am reading.
16. As a pricing analyst, I want the competitor prices already in the workbook seeded as listings, so that the research already done is not thrown away.
17. As a pricing analyst, I want a workbook-sourced price to be visibly marked unverified, so that I never mistake an unlinked number for a confirmed live listing.
18. As a pricing analyst, I want an unverified listing to have no deep-link button, so that the UI does not offer a link that does not exist.
19. As a pricing analyst, I want scraping to upgrade an unverified listing to verified when it finds the live product page, so that seeded prices converge on confirmed ones over time.
20. As a pricing analyst, I want the four new channels (Klassy Missy, Skincarebd, themallbd, Skinplus) to appear as marketplace columns, so that the imported book's competitive set is visible.
21. As a pricing analyst, I want channels with no listings in the current view hidden, so that the imported page is not padded with empty local-only columns.
22. As a pricing analyst, I want the discovery pipeline run against the 133 Imported SKUs that have no prices, so that the imported book reaches the same coverage as the local one.
23. As a pricing analyst, I want the same strict brand, category, volume, bundle, and shade matching rules applied to imported SKUs, so that match quality does not degrade on the new book.
24. As a pricing analyst, I want MRP derived by the identical rule on both pages, so that the two books' numbers stay comparable.
25. As a pricing analyst, I want to see which basis produced each MRP, so that I can tell an Official Store price from a third-party average.
26. As a pricing analyst, I want the Pricing Engine to treat both books identically, so that a change to global delivery cost reaches every SKU regardless of origin.
27. As a pricing analyst, I want per-SKU tunes to work on imported SKUs exactly as they do on local ones, so that I do not have to learn a second mechanism.
28. As a pricing analyst, I want a seeding report listing any imported product whose name and size match an existing local SKU, so that I can review genuine overlaps by hand.
29. As a pricing analyst, I want an overlapping product kept as two rows rather than merged, so that the same product sourced two ways can be compared on cost and margin.
30. As a pricing analyst, I want the JSON export to reflect the page I am on, so that an export of the imported book contains only imported SKUs.
31. As a pricing analyst, I want search, brand filter, and every sort to work identically on both pages, so that the imported page is not a second-class view.
32. As a maintainer, I want the origin backfill to be irreversible-safe and verified by a test against a real database, so that a migration cannot silently mislabel the existing catalog.
33. As a maintainer, I want a SKU whose brand cannot be determined flagged rather than guessed, so that a bad brand never enters the catalog silently.

## Implementation Decisions

**Sourcing Origin is a column, not a table.** `products` gains `sourcing_origin` (`local` | `imported`), `NOT NULL`, backfilled to `local` for all 407 existing rows. Recorded in ADR-0001 — the two books share every column, index, and foreign-key relationship, so a second table would duplicate the schema to express one flag.

**One shared Source Cost.** The Pricing Engine remains origin-agnostic, reading a single cost column. The physical column keeps its historical name `manufactured_price`; the domain calls it Source Cost. For an Imported SKU it holds the importer's quoted price — the workbook's `Price` column. No duty, freight, or landed-cost knobs are added; the confirmed rule is that the importer's quoted price *is* the cost basis.

**Origin filtering happens in the database.** `fetchCatalog` and `fetchDashboardMeta` take an origin argument and filter in SQL, so each page's payload carries only its own SKUs. The client prefetches the opposite origin in the background after first paint so the pill switches instantly without inflating the initial payload.

**Two routes, one component.** `/` and `/imported` both render the existing matrix component with a different dataset. The floating pill is a navigation control, not a filter — it carries per-origin counts supplied by the dashboard meta query.

**Category is a product column.** `category` (nullable text) holds `Skincare`, `Haircare`, or `Fragrance`, taken from the source tab. Local SKUs have no category and will be null. A category filter joins the existing header controls, and is hidden or inert when the active view has no categorised rows.

**Listings gain a verification state.** `marketplace_listings.url` becomes nullable and a `verified` flag distinguishes a listing with a confirmed live product page from one seeded out of the workbook. The existing `CHECK` is relaxed to permit a null URL while still requiring any present URL to be `http`/`https`. An unverified listing renders its price without a deep-link button. Scraping upgrades a listing in place when it finds the live page.

**Brand derivation is a curated longest-match.** A brand table maps product names to canonical brands, matching multi-word brands before single tokens so `The Ordinary`, `Beauty of Joseon`, `Head & Shoulders`, and `Hugo Boss` resolve correctly. Canonicalisation collapses known spelling variants (`L'Oreal`/`LOreal` → `L'Oréal`; four spellings → `Head & Shoulders`; `Herbal Essence` → `Herbal Essences`; `Ponds` → `Pond's`; `Johnson` → `Johnson's`; `STIVES` → `St. Ives`), corrects the source typo `Beauty Of Jiseon` → `Beauty of Joseon`, and maps the sub-brand `Nature Beauty` to its parent `Q Cosmetics` per the established hierarchy. 188 of 189 SKUs resolve; a SKU that cannot be resolved is reported, never guessed.

**Size is parsed from the product name.** A unit pattern extracts `ml`/`gm`/`g`/`kg`/`l`/`ltr`, and must treat the Unicode capital-I variant (`330mI`, `100mI`) as millilitres — six SKUs in the source use it. `1LTR` normalises to a millilitre quantity.

**Seeding is not ingestion vocabulary.** Loading workbook rows is *seeding*; `imported` is reserved exclusively for Sourcing Origin, per `CONTEXT.md`.

**Overlaps are reported, not merged.** Seeding emits a report of imported rows whose name and size match an existing local SKU. Current data shows zero exact-name overlaps, but the report runs regardless so future seeds are safe.

## Testing Decisions

A good test here asserts external behaviour — what a caller of the worker or the migration observes — never the shape of an internal helper. Tests are written at the highest seam that can express the behaviour, and every seam used already exists in this repo.

**HTTP seam** (`tests/app.test.ts`, existing pattern: build a fake D1 and drive `app.fetch`) carries the bulk:
- `/` returns only local SKUs; `/imported` returns only imported SKUs.
- Per-origin counts are correct in the dashboard meta.
- A channel appearing only on imported SKUs surfaces in that page's columns and is absent from the local page.
- An unverified listing is serialised without a deep link; a verified one keeps its URL.
- The JSON export reflects the active origin.

**Python migration seam** (`tests/test_sparse_overrides_migration.py`, existing pattern: run the migration against a real SQLite database) covers migration `0004`:
- All 407 pre-existing rows backfill to `local`, and the column is `NOT NULL`.
- A fresh `schema.sql` database and a migrated database agree on the resulting shape — the existing test in this file already enforces that invariant and must keep passing.
- A listing may carry a null URL, but a non-null URL must still be `http`/`https`.

**Python seeding seam** (new file, same unittest conventions) covers workbook parsing as pure functions over fixture rows:
- Brand derivation resolves multi-word brands ahead of single tokens.
- Canonicalisation collapses each known spelling variant, fixes the `Jiseon` typo, and maps `Nature Beauty` to `Q Cosmetics`.
- Size parsing handles `ml`/`gm`/`g` and the Unicode capital-I variant, and normalises `1LTR`.
- The overlap report names a colliding local SKU and does not merge it.
- An unresolvable brand is reported rather than defaulted.

**Browser seam** (`tests/e2e/browser.spec.ts`, existing Playwright setup) gets a single test: the floating pill navigates between the two routes, each page shows its own SKU count, and prefetching the opposite origin does not disturb the rendered table.

No new client-model tests: origin selection is a server concern, and the existing model tests already cover filters and sorts that are unchanged by this work.

## Out of Scope

- Re-scraping the 407 Local SKUs. Their prices are from an earlier run and have drifted, but refreshing them is a separate effort with its own failure modes.
- Duty, freight, and landed-cost inputs to the Pricing Engine. The confirmed cost basis for an Imported SKU is the importer's quoted price alone.
- Renaming the `manufactured_price` column to `source_cost`. A wide mechanical migration, deferred deliberately; `CONTEXT.md` carries the naming correction in the meantime.
- Deploying to Cloudflare Pages. Remote D1 is missing migrations `0002` and `0003`, `ADMIN_PASSWORD` and `SESSION_SECRET` are unset on Pages, and remote listing counts diverge from local. Unblocking deployment is its own task.
- Merging local and imported representations of the same product. They are two rows by design.
- Seeding the workbook's two local tabs. The 407 local SKUs already exist; the local tabs are not re-imported.

## Further Notes

The source workbook is `Roopelle.com Final Excel Sheet.xlsx` at the repo root, with five tabs: three imported (Skincare 100, Haircare 65, Fragrance 24) and two local (372 and 35 rows) that broadly correspond to the existing catalog.

Only the Skincare tab carries competitor prices — 56 rows across six channels, of which Klassy Missy, Skincarebd, themallbd, and Skinplus are new to the system. The Haircare and Fragrance tabs have the channel columns present but entirely empty. The `Out of Stock` column is empty across all three tabs and is not modelled.

One SKU, `CENTELLA SUN STICK 20ML`, has no brand token in its name — *Centella asiatica* is an ingredient, and several Korean brands sell a product by that name. It is carried as an open question for the seeding ticket rather than guessed at.

One stray value, `1155S` in a Klassy Missy price cell, is non-numeric and must be handled by the seeding parser rather than crashing it.
