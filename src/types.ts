export type DiscountType = 'pct' | 'amt'
export type MrpSourceType = 'official' | 'third_party_avg' | 'reference'

export interface PricingParams {
  packaging: number
  transport: number
  delivery: number
  cac: number
  targetMarginPct: number
  discountType: DiscountType
  discountVal: number
}

export interface MarketplaceListing {
  price: number
  url: string
  matched_title: string | null
  size?: string | null
  seller: string | null
  confidence: number
  available: true
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
  sources: Record<string, MarketplaceListing>
}

export interface CatalogPayload {
  success: true
  product_count: number
  listing_count: number
  source_columns: string[]
  source_listing_counts: Record<string, number>
  products: Product[]
}

export interface DashboardMeta {
  productCount: number
  listingCount: number
  brands: string[]
  channels: string[]
}

export interface EnvBindings {
  DB: D1Database
  ADMIN_PASSWORD?: string
  SESSION_SECRET?: string
}

export type AppEnv = { Bindings: EnvBindings }
