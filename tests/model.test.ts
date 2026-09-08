import { describe, expect, test } from 'bun:test'
import type { PricingParams, Product } from '../src/types'
import {
  calculateMarketDiscount,
  calculateMarkup,
  calculateSellingPrice,
  filterProducts,
  nextPinnedSort,
  sortProducts,
  type SortValue,
} from '../src/client/model'
import { calculateSellingPrice as calculateServerSellingPrice } from '../src/server/pricing'

const defaults: PricingParams = {
  packaging: 45,
  transport: 0,
  delivery: 0,
  cac: 40,
  cacType: 'amt' as const,
  targetMarginPct: 0,
  discountType: 'pct',
  discountVal: 0,
}

const product = (row: number, name: string, brand: string, mfg: number, mrp: number, sources: Product['sources'] = {}): Product => ({
  row,
  product_name: name,
  brand_name: brand,
  size: null,
  source_sheet: null,
  source_row: null,
  source_cost_edited_at: null,
  mrp_edited_at: null,
  manufactured_price: mfg,
  market_average_price: mrp,
  canonical_name: name,
  mrp_source_type: sources['Official Store'] ? 'official' : Object.keys(sources).length ? 'third_party_avg' : 'reference',
  sourcing_origin: 'local',
  category: null,
  sources,
})

const listing = (price: number) => ({
  price,
  url: 'https://example.com',
  matched_title: null,
  seller: null,
  confidence: 100,
  available: true as const,
  verified: true,
})

describe('pricing arithmetic', () => {
  test('matches sourcing markup and benchmark discount formulas', () => {
    expect(calculateMarkup(390, 292.5)).toBeCloseTo(33.3333333333, 8)
    expect(calculateMarkup(120, 93.75)).toBeCloseTo(28, 8)
    expect(calculateMarketDiscount(350, 500)).toBeCloseTo(30, 8)
    expect(calculateMarketDiscount(600, 500)).toBeCloseTo(-20, 8)
  })

  test('treats a zero selling price as a valid full discount', () => {
    expect(calculateMarkup(0, 500)).toBe(-100)
    expect(calculateMarketDiscount(0, 500)).toBe(100)
    expect(calculateSellingPrice(500, { ...defaults, discountVal: 100 })).toBe(0)
  })

  test('supports true gross margin and both discount modes', () => {
    expect(calculateSellingPrice(1000, defaults)).toBe(1085)
    expect(calculateSellingPrice(1000, { ...defaults, targetMarginPct: 25 })).toBe(1447)
    expect(calculateSellingPrice(1000, { ...defaults, targetMarginPct: 25, discountVal: 10 })).toBe(1302)
    expect(calculateSellingPrice(1000, { ...defaults, targetMarginPct: 25, discountType: 'amt', discountVal: 200 })).toBe(1247)
  })

  test('client and server calculations are identical across the canonical dataset', async () => {
    const catalog = await Bun.file('product_pricing_data.json').json() as { products: Product[] }
    const parameterSets: PricingParams[] = [
      defaults,
      { packaging: 45, transport: 40, delivery: 60, cac: 80, cacType: 'amt' as const, targetMarginPct: 25, discountType: 'pct', discountVal: 10 },
      { packaging: 12.5, transport: 7.5, delivery: 40, cac: 30, cacType: 'amt' as const, targetMarginPct: 37.5, discountType: 'amt', discountVal: 55 },
    ]

    for (const item of catalog.products) {
      for (const params of parameterSets) {
        expect(calculateSellingPrice(item.manufactured_price, params)).toBe(calculateServerSellingPrice(item.manufactured_price, params))
      }
    }
  })

  test('a local SKU MRP follows the canonical workbook/manual value, never a scraped listing', async () => {
    // The research artifact carries the workbook benchmark unless an admin has
    // deliberately folded a manual MRP into it. Scraped brand-store prices stay
    // live listings and never overwrite either canonical value.
    const canonical = await Bun.file('verified_marketplace_research.json').json() as {
      products: Array<{
        row: number
        mrp_source_type?: Product['mrp_source_type']
        excel_prices?: { market_average_price?: number }
      }>
    }
    const benchmarks = new Map(
      canonical.products.map((item) => [item.row, {
        value: item.excel_prices?.market_average_price,
        source: item.mrp_source_type === 'manual' ? 'manual' as const : 'workbook' as const,
      }]),
    )

    const catalog = await Bun.file('product_pricing_data.json').json() as { products: Product[] }
    expect(catalog.products.length).toBeGreaterThan(0)

    for (const item of catalog.products) {
      const benchmark = benchmarks.get(item.row)
      if (!benchmark || benchmark.value === undefined) {
        throw new Error(`Missing canonical MRP for row ${item.row}`)
      }
      expect(benchmark.value).toBeGreaterThan(0)
      expect(item.market_average_price).toBeCloseTo(benchmark.value, 6)
      expect(item.mrp_source_type).toBe(benchmark.source)
    }
  })

  test('scraped listings keep their prices and deep links alongside the workbook MRP', async () => {
    const catalog = await Bun.file('product_pricing_data.json').json() as { products: Product[] }
    const withListings = catalog.products.filter((item) => Object.keys(item.sources).length > 0)
    expect(withListings.length).toBeGreaterThan(0)

    for (const item of withListings) {
      for (const listing of Object.values(item.sources)) {
        expect(listing.price).toBeGreaterThan(0)
        // A verified listing still carries the live product page.
        if (listing.verified) expect(listing.url).toBeTruthy()
      }
    }
  })
})

describe('header filters and sorts', () => {
  const products = [
    product(1, 'Beta Serum', 'Brand B', 200, 260, { Arogga: listing(250) }),
    product(2, 'Alpha Oil', 'Brand A', 100, 180, { 'Official Store': listing(180) }),
    product(3, 'Gamma Wash', 'Brand A', 300, 350, { Arogga: listing(340), Daraz: listing(360) }),
    product(4, 'Delta Cream', 'Brand C', 150, 220),
  ]
  const selling = (item: Product) => calculateSellingPrice(item.manufactured_price, defaults)

  test('search, brand, and source filters combine correctly', () => {
    expect(filterProducts(products, { query: 'oil', brand: '', source: '' }).map((item) => item.row)).toEqual([2])
    expect(filterProducts(products, { query: '', brand: 'Brand A', source: '' }).map((item) => item.row)).toEqual([2, 3])
    expect(filterProducts(products, { query: '', brand: '', source: 'Arogga' }).map((item) => item.row)).toEqual([1, 3])
    expect(filterProducts(products, { query: 'gamma', brand: 'Brand A', source: 'Daraz' }).map((item) => item.row)).toEqual([3])
  })

  test('category narrows the view and combines with the other filters', () => {
    const catalogue = [
      product(10, 'CeraVe Cleanser', 'CeraVe', 800, 1100, { Shajgoj: listing(1100) }),
      product(11, 'Sunsilk Shampoo', 'Sunsilk', 200, 320, { Shajgoj: listing(320) }),
      product(12, 'CeraVe Cream', 'CeraVe', 900, 1400),
    ]
    catalogue[0]!.category = 'Skincare'
    catalogue[1]!.category = 'Haircare'
    catalogue[2]!.category = 'Skincare'

    expect(filterProducts(catalogue, { query: '', brand: '', source: '', category: 'Skincare' }).map((p) => p.row)).toEqual([10, 12])
    expect(filterProducts(catalogue, { query: '', brand: '', source: '', category: 'Haircare' }).map((p) => p.row)).toEqual([11])
    // Combines with brand and channel rather than replacing them.
    expect(filterProducts(catalogue, { query: '', brand: 'CeraVe', source: 'Shajgoj', category: 'Skincare' }).map((p) => p.row)).toEqual([10])
    // An absent category means "all", so local SKUs are never filtered out.
    expect(filterProducts(catalogue, { query: '', brand: '', source: '' })).toHaveLength(3)
  })

  test('every select sort is ordered correctly', () => {
    const cases: Array<[SortValue, number[]]> = [
      ['product', [2, 1, 4, 3]], ['productDesc', [3, 4, 1, 2]],
      ['brand', [2, 3, 1, 4]], ['brandDesc', [4, 1, 3, 2]],
      ['mfgAsc', [2, 4, 1, 3]], ['mfgDesc', [3, 1, 4, 2]],
      ['marketAsc', [2, 4, 1, 3]], ['marketDesc', [3, 1, 4, 2]],
      ['sellingAsc', [2, 4, 1, 3]], ['sellingDesc', [3, 1, 4, 2]],
      ['coverage', [3, 2, 1, 4]], ['spread', [3, 2, 1, 4]],
      ['srcAsc:Arogga', [1, 3, 2, 4]], ['srcDesc:Arogga', [3, 1, 2, 4]],
    ]
    for (const [sort, expectedRows] of cases) {
      expect(sortProducts(products, sort, selling, ['Official Store', 'Arogga', 'Daraz']).map((item) => item.row)).toEqual(expectedRows)
    }
  })

  // The fixture above is useless for discount ordering: every row is above
  // market, so its discount order collapses onto the selling-price order and a
  // test would pass against an implementation that just sorted by price. These
  // rows make the two disagree on purpose -- 21 and 22 share a selling price of
  // 185 yet sit at opposite ends of the discount order.
  const byMarket = [
    product(21, 'Zinc Serum', 'Brand A', 100, 500),
    product(22, 'Aloe Toner', 'Brand B', 100, 200),
    product(23, 'Mint Wash', 'Brand A', 300, 1000),
    product(24, 'Basil Balm', 'Brand B', 150, 0),
    product(25, 'Cocoa Cream', 'Brand A', 300, 200),
  ]

  test('market discount sorts by the gap to MRP, not by the selling price', () => {
    // selling = cost + 85, so: 21 -> 63%, 22 -> 7.5%, 23 -> 61.5%, 25 -> -92.5%.
    expect(sortProducts(byMarket, 'discountDesc', selling, []).map((item) => item.row))
      .toEqual([21, 23, 22, 25, 24])
    expect(sortProducts(byMarket, 'discountAsc', selling, []).map((item) => item.row))
      .toEqual([25, 22, 23, 21, 24])
  })

  test('a SKU with no MRP benchmark sinks to the bottom of both discount sorts', () => {
    // Row 24 has no benchmark to discount against. It is not "0% off" -- it is
    // unknown, so it must never head the ascending list.
    expect(sortProducts(byMarket, 'discountAsc', selling, []).at(-1)?.row).toBe(24)
    expect(sortProducts(byMarket, 'discountDesc', selling, []).at(-1)?.row).toBe(24)
  })

  test('the discount sort applies to the filtered view, not the whole catalog', () => {
    const view = filterProducts(byMarket, { query: '', brand: 'Brand A', source: '' })
    expect(sortProducts(view, 'discountDesc', selling, []).map((item) => item.row)).toEqual([21, 23, 25])
    expect(sortProducts(view, 'discountAsc', selling, []).map((item) => item.row)).toEqual([25, 23, 21])
  })

  test('clickable pinned headers toggle in both directions', () => {
    expect(nextPinnedSort('product', 'product')).toBe('productDesc')
    expect(nextPinnedSort('productDesc', 'product')).toBe('product')
    expect(nextPinnedSort('brand', 'mfg')).toBe('mfgAsc')
    expect(nextPinnedSort('mfgAsc', 'mfg')).toBe('mfgDesc')
  })
})
