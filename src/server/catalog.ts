import type { CatalogPayload, DashboardMeta, MarketplaceListing, MrpSourceType, Product } from '../types'

const CHANNEL_ORDER = [
  'Official Store', 'Arogga', 'Shajgoj', 'OhSoGo', 'Daraz',
  'eMartWay', 'PandaMart', 'Rokomari', 'Chaldal',
] as const

interface ProductRow {
  row_id: number
  product_name: string
  brand_name: string
  size: string | null
  manufactured_price: number
  market_average_price: number
  canonical_name: string | null
  mrp_source_type: MrpSourceType
}

interface ListingRow {
  row_id: number
  channel_name: string
  price: number
  url: string | null
  matched_title: string | null
  seller: string | null
  confidence: number
  verified: number
}

export async function fetchCatalog(db: D1Database): Promise<CatalogPayload> {
  const [productsResult, listingsResult] = await db.batch([
    db.prepare(`SELECT row_id, product_name, brand_name, size, manufactured_price,
                       market_average_price, canonical_name, mrp_source_type
                  FROM products ORDER BY row_id ASC`),
    db.prepare(`SELECT row_id, channel_name, price, url, matched_title, seller, confidence, verified
                  FROM marketplace_listings WHERE available = 1`),
  ])

  const productRows = (productsResult?.results ?? []) as unknown as ProductRow[]
  const listingRows = (listingsResult?.results ?? []) as unknown as ListingRow[]

  const listingsByRow = new Map<number, Record<string, MarketplaceListing>>()
  const counts = new Map<string, number>()
  for (const raw of listingRows) {
    const sources = listingsByRow.get(raw.row_id) ?? {}
    sources[raw.channel_name] = {
      price: raw.price,
      url: raw.url,
      matched_title: raw.matched_title,
      seller: raw.seller,
      confidence: raw.confidence,
      available: true,
      verified: raw.verified === 1,
    }
    listingsByRow.set(raw.row_id, sources)
    counts.set(raw.channel_name, (counts.get(raw.channel_name) ?? 0) + 1)
  }

  const products = productRows.map<Product>((row) => ({
    row: row.row_id,
    product_name: row.product_name,
    brand_name: row.brand_name,
    size: row.size,
    manufactured_price: row.manufactured_price,
    market_average_price: row.market_average_price,
    canonical_name: row.canonical_name,
    mrp_source_type: row.mrp_source_type,
    sources: listingsByRow.get(row.row_id) ?? {},
  }))

  const discovered = [...counts.keys()]
  const channels = CHANNEL_ORDER.filter((channel) => counts.has(channel)) as string[]
  channels.push(...discovered.filter((channel) => !channels.includes(channel)).sort())

  return {
    success: true,
    product_count: products.length,
    listing_count: listingRows.length,
    source_columns: channels,
    source_listing_counts: Object.fromEntries(channels.map((channel) => [channel, counts.get(channel) ?? 0])),
    products,
  }
}

export async function fetchDashboardMeta(db: D1Database): Promise<DashboardMeta> {
  const [countsResult, brandsResult, channelsResult] = await db.batch([
    db.prepare(`SELECT (SELECT COUNT(*) FROM products) AS product_count,
                       (SELECT COUNT(*) FROM marketplace_listings WHERE available = 1) AS listing_count`),
    db.prepare('SELECT DISTINCT brand_name FROM products ORDER BY brand_name'),
    db.prepare(`SELECT channel_name, COUNT(*) AS listing_count
                  FROM marketplace_listings WHERE available = 1
                 GROUP BY channel_name`),
  ])
  const counts = countsResult?.results[0] as { product_count?: number; listing_count?: number } | undefined
  const channelCounts = new Map(
    ((channelsResult?.results ?? []) as Array<{ channel_name: string; listing_count: number }>).map((row) => [row.channel_name, row.listing_count]),
  )
  const discovered = [...channelCounts.keys()]
  const channels = CHANNEL_ORDER.filter((channel) => channelCounts.has(channel)) as string[]
  channels.push(...discovered.filter((channel) => !channels.includes(channel)).sort())
  return {
    productCount: Number(counts?.product_count ?? 0),
    listingCount: Number(counts?.listing_count ?? 0),
    brands: ((brandsResult?.results ?? []) as Array<{ brand_name: string }>).map((row) => row.brand_name),
    channels,
  }
}
