# Product Price Intelligence & Marketplace Benchmark Matrix

Live Cloudflare Pages dashboard for comparing manufacturing cost, official MRP, recommended selling price, and verified marketplace listings across Bangladesh beauty and personal-care SKUs.

**Production:** https://product-price-matrix.pages.dev

## Current dataset

- 407 products across 16 brands
- 717 active verified listings
- Unified `Official Store` channel plus Arogga, Shajgoj, OhSoGo, Daraz, eMartWay, PandaMart, and Rokomari
- Strict brand, product type, size, bundle, concentration, and shade matching gates

## Architecture

- **UI:** Hono JSX server rendering with a bundled TypeScript browser client
- **API:** Hono routes under `src/routes/`
- **Database:** Cloudflare D1
- **Build:** Bun, Vite, and `@hono/vite-build`
- **Data pipeline:** Python catalog builder and strict SKU matcher
- **Testing:** Bun unit/integration tests, Python `unittest`, and Playwright browser tests

```text
src/
├── components/       Hono JSX page components
├── client/           Browser state, rendering, filters, sorting, and pricing UI
├── routes/           Auth, products, pricing engine, and override APIs
├── server/           D1 catalog, authentication, and pricing request validation
├── shared/           Dependency-free pricing domain logic (worker + browser)
└── index.tsx         Hono application entry point

tests/                TypeScript, Python, and Playwright tests
scripts/              Local D1 migration/synchronization utilities
migrations/           D1 production migrations
public/static/         Browser CSS; app.js is generated during build
catalog_builder.py     Canonical data/audit/seed compiler
sku_matcher.py         Strict listing validation
product_pricing_data.json
verified_marketplace_research.json
verified_match_audit.json
schema.sql
seed.sql
```

## Pricing engine

The recommended selling price for a SKU is:

```text
list  = (MFG + packaging + transport + delivery + CAC) / (1 - margin%)
final = list × (1 - discount%)      # percentage mode
final = list − discountBDT          # amount mode
```

Parameters resolve in two layers, both persisted in Cloudflare D1 (there is no
`localStorage` state — a tune survives reloads, browsers, and devices):

1. **Global defaults** — `global_pricing_params`, edited in the navbar *Pricing Engine* modal.
2. **Per-product tunes** — `product_pricing_overrides`, edited in a product's *Custom Pricing Engine* tab.

A tune is **sparse**: it pins only the fields you actually change, and every
other field keeps following the global engine. Leave an input blank to inherit
(the placeholder shows the live global value); fill it to pin it. Rows carrying
a pinned field show a purple `Tuned` pill whose tooltip names what is pinned.

So a SKU tuned to a 30% margin still absorbs a later global delivery increase,
while its margin stays put. Rules enforced in the schema, the worker, and tests:

- `discount_type` and `discount_val` pin as a pair or not at all.
- A tune that pins nothing is deleted, never stored as an all-`NULL` row.
- A field submitted equal to the current global value is stripped before the
  write, so it cannot silently freeze against future global changes.

`src/shared/pricing.ts` holds the merge and formula logic used verbatim by both
the worker and the browser bundle; `src/server/pricing.ts` adds the zod request
schemas and is never imported by the client, keeping zod out of `app.js`.

## Development

Prerequisites: Bun 1.3+, `uv`, and Python 3.12+.

```bash
bun install
bun run dev
```

The local app uses Wrangler/Miniflare D1 state and binds to Vite's local URL.

## Data rebuild

```bash
uv run --with openpyxl --with rapidfuzz python3 build_matrix.py
bun run db:local:sync
```

`build_matrix.py` validates active listings and regenerates the canonical JSON, audit log, and D1 seed. The web application itself is compiled from `src/`; legacy generated standalone HTML is no longer part of the build.

## Verification

```bash
bun run test
bun run typecheck
bun run build
bun run test:browser
```

The Playwright command starts and stops its own application server on port 4173.

## Production preview and deploy

```bash
bun run build
bun run preview
bun run deploy
```

Required production secrets for admin mutations:

- `ADMIN_PASSWORD`
- `SESSION_SECRET`

Public catalog and pricing reads remain unauthenticated. Global pricing and per-product override mutations require a signed same-origin admin session.
