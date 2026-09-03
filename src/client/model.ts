import type { Product } from '../types'

// The pricing formula and override-merge rules live in one dependency-free
// module shared by the worker and the browser bundle; re-exported here so
// existing client imports keep working without a second, drifting implementation.
export {
  calculateSellingPrice,
  isEmptyOverride,
  overriddenFields,
  resolvePricingParams,
  sparsifyOverride,
} from '../shared/pricing'

export type SortValue =
  | 'product' | 'productDesc'
  | 'brand' | 'brandDesc'
  | 'sellingAsc' | 'sellingDesc'
  | 'mfgAsc' | 'mfgDesc'
  | 'marketAsc' | 'marketDesc'
  | 'coverage' | 'spread'
  | `srcAsc:${string}` | `srcDesc:${string}`

export interface ProductFilters {
  query: string
  brand: string
  source: string
  category?: string
}

export function calculateMarkup(price: number | null, manufacturedPrice: number | null): number | null {
  if (!Number.isFinite(price) || !Number.isFinite(manufacturedPrice) || price === null || manufacturedPrice === null || price < 0 || manufacturedPrice <= 0) {
    return null
  }
  return ((price - manufacturedPrice) / manufacturedPrice) * 100
}

export function calculateMarketDiscount(sellingPrice: number | null, benchmarkPrice: number | null): number | null {
  if (!Number.isFinite(sellingPrice) || !Number.isFinite(benchmarkPrice) || sellingPrice === null || benchmarkPrice === null || sellingPrice < 0 || benchmarkPrice <= 0) {
    return null
  }
  return ((benchmarkPrice - sellingPrice) / benchmarkPrice) * 100
}

export function filterProducts(products: readonly Product[], filters: ProductFilters): Product[] {
  const query = filters.query.trim().toLocaleLowerCase()
  return products.filter((product) =>
    (!query || product.product_name.toLocaleLowerCase().includes(query) || product.brand_name.toLocaleLowerCase().includes(query)) &&
    (!filters.brand || product.brand_name === filters.brand) &&
    (!filters.category || product.category === filters.category) &&
    (!filters.source || product.sources[filters.source] !== undefined)
  )
}

function channelSpread(product: Product, sources: readonly string[]): number {
  const prices = sources
    .map((source) => product.sources[source]?.price)
    .filter((price): price is number => Number.isFinite(price))
  return prices.length > 1 ? Math.max(...prices) - Math.min(...prices) : 0
}

function compareOptionalNumbers(left: number | undefined, right: number | undefined, direction: 'asc' | 'desc'): number {
  const leftMissing = !Number.isFinite(left)
  const rightMissing = !Number.isFinite(right)
  if (leftMissing && rightMissing) return 0
  if (leftMissing) return 1
  if (rightMissing) return -1
  return direction === 'asc' ? left! - right! : right! - left!
}

export function sortProducts(
  products: readonly Product[],
  sort: SortValue,
  sellingPriceFor: (product: Product) => number | null,
  sources: readonly string[],
): Product[] {
  const list = [...products]
  const byName = (a: Product, b: Product) => a.product_name.localeCompare(b.product_name)

  if (sort === 'product') return list.sort(byName)
  if (sort === 'productDesc') return list.sort((a, b) => byName(b, a))
  if (sort === 'brand') return list.sort((a, b) => a.brand_name.localeCompare(b.brand_name) || byName(a, b))
  if (sort === 'brandDesc') return list.sort((a, b) => b.brand_name.localeCompare(a.brand_name) || byName(b, a))
  if (sort === 'sellingAsc') return list.sort((a, b) => compareOptionalNumbers(sellingPriceFor(a) ?? undefined, sellingPriceFor(b) ?? undefined, 'asc'))
  if (sort === 'sellingDesc') return list.sort((a, b) => compareOptionalNumbers(sellingPriceFor(a) ?? undefined, sellingPriceFor(b) ?? undefined, 'desc'))
  if (sort === 'mfgAsc') return list.sort((a, b) => a.manufactured_price - b.manufactured_price)
  if (sort === 'mfgDesc') return list.sort((a, b) => b.manufactured_price - a.manufactured_price)
  if (sort === 'marketAsc') return list.sort((a, b) => a.market_average_price - b.market_average_price)
  if (sort === 'marketDesc') return list.sort((a, b) => b.market_average_price - a.market_average_price)
  if (sort === 'coverage') return list.sort((a, b) => Object.keys(b.sources).length - Object.keys(a.sources).length || byName(a, b))
  if (sort === 'spread') return list.sort((a, b) => channelSpread(b, sources) - channelSpread(a, sources) || byName(a, b))

  const separator = sort.indexOf(':')
  const direction = sort.startsWith('srcAsc:') ? 'asc' : 'desc'
  const source = separator >= 0 ? sort.slice(separator + 1) : ''
  return list.sort((a, b) =>
    compareOptionalNumbers(a.sources[source]?.price, b.sources[source]?.price, direction) || byName(a, b)
  )
}

export const PINNED_SORT_VALUES = {
  product: ['product', 'productDesc'],
  brand: ['brand', 'brandDesc'],
  mfg: ['mfgAsc', 'mfgDesc'],
  market: ['marketAsc', 'marketDesc'],
  selling: ['sellingAsc', 'sellingDesc'],
} as const satisfies Record<string, readonly [SortValue, SortValue]>

export function nextPinnedSort(current: string, key: keyof typeof PINNED_SORT_VALUES): SortValue {
  const [ascending, descending] = PINNED_SORT_VALUES[key]
  return current === ascending ? descending : ascending
}
