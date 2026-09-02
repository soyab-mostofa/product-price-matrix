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
├── server/           D1 catalog, authentication, and pricing domain logic
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
