# Product Price Intelligence & Marketplace Benchmark Matrix

Real-time price benchmark dataset, automated multi-marketplace discovery pipeline, and interactive dashboard for 372 personal care and beauty SKUs across major Bangladeshi D2C brand flagships and third-party e-commerce channels.

Live Dashboard: **[https://product-price-matrix.pages.dev](https://product-price-matrix.pages.dev)**

---

## Overview

- **372 Products Tracked** across 15 brands (*Guerniss, BioCare, Skin Cafe, Neofarmers, Q Cosmetics, Nirvana, LILAC, Groome, Rajkonna, Lavino, Ombre, Panam, Bio-Screen, Hawaa, Enso Skin*).
- **749 Verified Active Listings** mapped to canonical product URLs.
- **13 Source Channels Covered**:
  - *Official Brand Stores*: Guerniss Official, Bio-Xin Official, Neofarmers Official, Skin Cafe Official, Nature Beauty Official
  - *Third-Party Marketplaces*: Arogga, Shajgoj, OhSoGo, Daraz Bangladesh, eMartWay, PandaMart (Foodpanda), Rokomari, Chaldal
- **Strict Brand & SKU Matching Gates**: Zero loose substitutions, strict unit/volume checks, cosmetic shade verification, combo rejection.
- **Discount & Selling Price Priority**: Captures active promotional customer checkout prices over list MRPs.

---

## Project Structure

```text
.
├── public/                                  # Static assets for web deployment
│   ├── index.html                           # Modern light dashboard application
│   └── product_pricing_data.json            # Clean structured JSON dataset
├── verified_marketplace_research.json       # Authoritative full research dataset
├── verified_match_audit.json                # Complete match/rejection audit trail
├── product_pricing_dashboard.html           # Standalone dashboard HTML
├── build_refined_matrix_ui.py               # Dashboard & JSON compilation script
└── README.md
```

---

## Data Schema (`product_pricing_data.json`)

```json
{
  "currency": "BDT",
  "currency_symbol": "৳",
  "product_count": 372,
  "brand_count": 15,
  "source_columns": ["Arogga", "Shajgoj", "OhSoGo", "Guerniss Official", "Daraz", "..."],
  "products": [
    {
      "product_name": "Almond Oil/ কাঠ বাদামের তেল",
      "brand_name": "Neofarmers",
      "manufactured_price": 292.5,
      "market_average_price": 390.0,
      "sources": {
        "Shajgoj": {
          "price": 351.0,
          "url": "https://shop.shajgoj.com/product/neofarmers-almond-oil",
          "matched_title": "Neofarmers Almond Oil 100ml",
          "available": true,
          "confidence": 100.0
        },
        "Neofarmers Official": {
          "price": 390.0,
          "url": "https://neofarmers.com.bd/product/almond-oil",
          "matched_title": "Almond Oil / কাঠ বাদামের তেল",
          "available": true,
          "confidence": 100.0
        }
      }
    }
  ]
}
```

---

## Features

1. **Frozen 4-Column Sticky Freeze**: Product Name, Brand, Manufactured Price, and Market Average stay locked during horizontal matrix scrolling.
2. **Visual Price Highlights**: Highest price (Red), Second highest price (Amber/Yellow), and Lowest price (Green).
3. **Dynamic Channel Auto-Hiding**: Filtering by brand automatically collapses marketplace columns with 0 listings for that selection.
4. **Direct Sourcing & Deep Inspection**: Click any row to view full metadata and direct links to live product listings.

---

## Deployment

Deployable to any static host (Cloudflare Pages, Vercel, Netlify, GitHub Pages):

```bash
# Cloudflare Pages Deploy
bunx wrangler pages deploy public --project-name product-price-matrix
```
