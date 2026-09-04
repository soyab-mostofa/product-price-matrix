export type DiscountType = 'pct' | 'amt'
export type MrpSourceType = 'official' | 'third_party_avg' | 'reference' | 'workbook'

/** How a SKU reaches us: made here and bought from the maker, or brought in via an importer. */
export type SourcingOrigin = 'local' | 'imported'

export const SOURCING_ORIGINS = ['local', 'imported'] as const satisfies readonly SourcingOrigin[]

export function isSourcingOrigin(value: unknown): value is SourcingOrigin {
  return value === 'local' || value === 'imported'
}

export interface PricingParams {
  packaging: number
  transport: number
  delivery: number
  cac: number
  targetMarginPct: number
  discountType: DiscountType
  discountVal: number
}

/**
 * A sparse per-product tune. Every field is optional and an absent field means
 * "inherit whatever the global engine currently says", so raising a global cost
 * still reaches tuned SKUs for the knobs they never pinned.
 *
 * discountType/discountVal move as a pair: an amount is meaningless under a
 * percentage mode, so a tune either pins both or neither.
 */
export interface PricingOverride {
  // `| undefined` is explicit because exactOptionalPropertyTypes is on and
  // validated payloads carry undefined values for fields left un-pinned.
  packaging?: number | undefined
  transport?: number | undefined
  delivery?: number | undefined
  cac?: number | undefined
  targetMarginPct?: number | undefined
  discountType?: DiscountType | undefined
  discountVal?: number | undefined
}

/** Tunable keys, in the order the UI presents them. */
export const PRICING_FIELDS = [
  'packaging',
  'transport',
  'delivery',
  'cac',
  'targetMarginPct',
  'discountType',
  'discountVal',
] as const satisfies readonly (keyof PricingParams)[]

export type PricingField = (typeof PRICING_FIELDS)[number]

/** An override as stored, plus the audit stamp the UI surfaces on the Tuned pill. */
export interface StoredPricingOverride extends PricingOverride {
  updatedAt?: string | null
}

export interface MarketplaceListing {
  price: number
  /** Null while the price is known but its product page is not. */
  url: string | null
  matched_title: string | null
  size?: string | null
  seller: string | null
  confidence: number
  available: true
  /** Confirmed against a live product page, rather than seeded from a workbook. */
  verified: boolean
}

export interface Product {
  row: number
  product_name: string
  brand_name: string
  size: string | null
  manufactured_price: number
  market_average_price: number
  canonical_name: string | null
  mrp_source_type: MrpSourceType
  sourcing_origin: SourcingOrigin
  /** Skincare / Haircare / Fragrance for imported SKUs; local SKUs have none. */
  category: string | null
  sources: Record<string, MarketplaceListing>
}

export interface CatalogPayload {
  success: true
  origin: SourcingOrigin
  product_count: number
  listing_count: number
  source_columns: string[]
  source_listing_counts: Record<string, number>
  categories: string[]
  products: Product[]
}

export interface DashboardMeta {
  origin: SourcingOrigin
  productCount: number
  listingCount: number
  /** Per-origin SKU totals, so the origin switch can show both sides at once. */
  originCounts: Record<SourcingOrigin, number>
  brands: string[]
  channels: string[]
  categories: string[]
}

export interface EnvBindings {
  DB: D1Database
  ADMIN_PASSWORD?: string
  SESSION_SECRET?: string
}

export type AppEnv = { Bindings: EnvBindings }
