# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

E-commerce founders, pricing operators, and commercial category managers at Roopelle evaluating competitive marketplace benchmarks and setting profitable selling prices for personal care and beauty SKUs in Bangladesh.

## Product Purpose

Provide an authoritative price intelligence matrix and dynamic unit-economics pricing engine across 596+ beauty & personal care SKUs (407 Local, 189 Imported) mapped against major Bangladeshi e-commerce channels (Official Stores, Arogga, Shajgoj, OhSoGo, Daraz, eMartWay, PandaMart, Chaldal, etc.). It ensures pricing viability, reveals competitor spreads, and prevents pricing products above market.

## Positioning

Unlike generic scrapers or static spreadsheets, the matrix enforces commercial truth: Local SKUs anchor strictly to immutable manufacturer trade benchmarks (where live promotions never distort cost basis), while Imported SKUs derive consensus benchmarks from verified channel listings. The built-in unit-economics engine flags above-market recommendations in real-time and supports sparse per-SKU margin tuning.

## Operating Context

Desktop operational dashboard viewed during pricing reviews, margin audits, and competitive re-pricing sessions. Users navigate high-density comparative tables with frozen base columns (Product Name, Brand, Source Cost, MRP, Recommended Selling Price) and dynamic marketplace columns, toggling between markup % and market discount %, filtering across brands and channels, and tuning unit costs in focused modals.

## Capabilities and Constraints

- **Dual-Book Architecture**: Distinct routes for Local (`/`) and Imported (`/imported`) sourcing books with separate catalog metadata and category hierarchies.
- **Strict Benchmark Parity**: Local MRP benchmark is immutable from `Roopelle.com Final Excel Sheet.xlsx`; scraped channel prices populate comparison columns but never overwrite the reference.
- **Unit Economics Engine**: Calculates List Price = `(Source Cost + Packaging + Transport + Delivery + CAC) / (1 - Target Margin %)`, applying percentage or amount promotional discounts.
- **Sparse Per-SKU Overrides**: D1-backed sparse overrides where `NULL` cleanly inherits global engine settings.
- **Admin Access Control**: Public read-only exploration; HMAC session cookie and same-origin CSRF header required for mutating global or per-product economics.
- **Data Integrity**: Schema-faithful rendering with verified deep links; missing channels or unverified listings are never fabricated or masked with placeholder images.

## Brand Commitments

- Clean, high-density editorial operational aesthetic.
- Precise typography hierarchy with clear data readability over decorative chrome.
- Rich semantic color tokens for markup tiers and above-market danger states.
- 0px sharp or subtle disciplined geometry (avoiding playful pill-bloat or generic SaaS templates).

## Evidence on Hand

- `Roopelle.com Final Excel Sheet.xlsx` (commercial source of truth for 372 local, 35 Orgagenic, and 189 imported SKUs).
- `verified_marketplace_research.json` & `verified_match_audit.json` (canonical product listings and audit logs).
- Cloudflare D1 database with active schemas for `products`, `marketplace_listings`, `global_pricing_params`, and `product_pricing_overrides`.

## Product Principles

1. **Commercial Truth Over Scraped Noise**: Benchmark arithmetic must never drift due to live competitor flash sales.
2. **Scanability at Scale**: Operators must parse 500+ SKUs quickly; high-contrast numbers, structured columns, and semantic chips guide the eye to actionable margin deltas.
3. **No Decorative Deception**: Never invent missing photos, dummy ratings, or unverified links; absence of data is expressed honestly through typography and tabular layout.
4. **Immediate Risk Visibility**: Unsellable or above-market recommendations must surface immediately with unambiguous danger cues before prices reach production channels.
