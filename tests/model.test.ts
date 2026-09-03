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
  packaging: 20,
  transport: 0,
  delivery: 60,
  cac: 0,
  targetMarginPct: 0,
  discountType: 'pct',
  discountVal: 0,
}

const product = (row: number, name: string, brand: string, mfg: number, mrp: number, sources: Product['sources'] = {}): Product => ({
  row,
  product_name: name,
  brand_name: brand,
  size: null,
  manufactured_price: mfg,
  market_average_price: mrp,
  canonical_name: name,
  mrp_source_type: sources['Official Store'] ? 'official' : Object.keys(sources).length ? 'third_party_avg' : 'reference',
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
    expect(calculateSellingPrice(1000, defaults)).toBe(1080)
    expect(calculateSellingPrice(1000, { ...defaults, targetMarginPct: 25 })).toBe(1440)
    expect(calculateSellingPrice(1000, { ...defaults, targetMarginPct: 25, discountVal: 10 })).toBe(1296)
    expect(calculateSellingPrice(1000, { ...defaults, targetMarginPct: 25, discountType: 'amt', discountVal: 200 })).toBe(1240)
  })

  test('client and server calculations are identical across the canonical dataset', async () => {
    const catalog = await Bun.file('product_pricing_data.json').json() as { products: Product[] }
    const parameterSets: PricingParams[] = [
      defaults,
      { packaging: 20, transport: 40, delivery: 60, cac: 80, targetMarginPct: 25, discountType: 'pct', discountVal: 10 },
      { packaging: 12.5, transport: 7.5, delivery: 40, cac: 30, targetMarginPct: 37.5, discountType: 'amt', discountVal: 55 },
    ]

    for (const item of catalog.products) {
      for (const params of parameterSets) {
        expect(calculateSellingPrice(item.manufactured_price, params)).toBe(calculateServerSellingPrice(item.manufactured_price, params))
      }
    }
  })

  test('canonical MRP is official price or exact active third-party average', async () => {
    const catalog = await Bun.file('product_pricing_data.json').json() as { products: Product[] }
    for (const item of catalog.products) {
      const official = item.sources['Official Store']
      if (official) {
        expect(item.market_average_price).toBeCloseTo(official.price, 6)
        expect(item.mrp_source_type).toBe('official')
        continue
      }
      const prices = Object.values(item.sources).map((source) => source.price)
      if (prices.length > 0) {
        const average = prices.reduce((total, price) => total + price, 0) / prices.length
        expect(item.market_average_price).toBeCloseTo(average, 3)
        expect(item.mrp_source_type).toBe('third_party_avg')
      } else {
        expect(item.mrp_source_type).toBe('reference')
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

  test('clickable pinned headers toggle in both directions', () => {
    expect(nextPinnedSort('product', 'product')).toBe('productDesc')
    expect(nextPinnedSort('productDesc', 'product')).toBe('product')
    expect(nextPinnedSort('brand', 'mfg')).toBe('mfgAsc')
    expect(nextPinnedSort('mfgAsc', 'mfg')).toBe('mfgDesc')
  })
})
