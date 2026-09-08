import type {
  CatalogPayload,
  DashboardMeta,
  MarketplaceListing,
  MrpSourceType,
  Product,
  SourcingOrigin,
} from '../types'

const CHANNEL_ORDER = [
  'Official Store', 'Arogga', 'Shajgoj', 'OhSoGo', 'Daraz',
  'eMartWay', 'PandaMart', 'Rokomari', 'Chaldal',
  'Klassy Missy', 'Skincarebd', 'themallbd', 'Skinplus',
] as const

/** Known channels first, then anything discovery has since turned up. */
function orderChannels(discovered: Iterable<string>): string[] {
  const found = new Set(discovered)
  const ordered = CHANNEL_ORDER.filter((channel) => found.has(channel)) as string[]
  ordered.push(...[...found].filter((channel) => !ordered.includes(channel)).sort())
  return ordered
}

interface ProductRow {
  row_id: number
  product_name: string
  brand_name: string
  size: string | null
  manufactured_price: number
  market_average_price: number
  canonical_name: string | null
  mrp_source_type: MrpSourceType
  sourcing_origin: SourcingOrigin
  category: string | null
  source_sheet: string | null
  source_row: number | null
  source_cost_edited_at: string | null
  mrp_edited_at: string | null
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

export async function fetchCatalog(db: D1Database, origin: SourcingOrigin = 'local'): Promise<CatalogPayload> {
  const [productsResult, listingsResult] = await db.batch([
    // Prices come straight off `products` — the journal is an audit log, not a
    // resolution layer. The only thing joined here is WHEN each price field was
    // last edited, which is what the UI's edited affordance keys off.
    //
    // Resolved PER FIELD, not per product. A single timestamp for the whole row
    // made an MRP-only edit mark the untouched Source Cost as edited too, and
    // offered to "revert" a figure that already equalled its workbook value.
    db.prepare(`SELECT product.row_id, product.product_name, product.brand_name,
                       product.size, product.manufactured_price,
                       product.market_average_price, product.canonical_name,
                       product.mrp_source_type, product.sourcing_origin, product.category,
                       product.source_sheet, product.source_row,
                       (SELECT edit.edited_at FROM price_edits edit
                         WHERE edit.product_row_id = product.row_id
                           AND edit.field = 'source_cost'
                           AND edit.id = (SELECT MAX(latest.id) FROM price_edits latest
                                           WHERE latest.product_row_id = product.row_id
                                             AND latest.field = 'source_cost')
                           AND (edit.workbook_value IS NULL OR edit.new_value != edit.workbook_value)
                       ) AS source_cost_edited_at,
                       (SELECT edit.edited_at FROM price_edits edit
                         WHERE edit.product_row_id = product.row_id
                           AND edit.field = 'mrp'
                           AND edit.id = (SELECT MAX(latest.id) FROM price_edits latest
                                           WHERE latest.product_row_id = product.row_id
                                             AND latest.field = 'mrp')
                           AND (edit.workbook_value IS NULL OR edit.new_value != edit.workbook_value)
                       ) AS mrp_edited_at
                  FROM products product WHERE product.sourcing_origin = ?
                 ORDER BY product.row_id ASC`).bind(origin),
    db.prepare(`SELECT listing.row_id, listing.channel_name, listing.price, listing.url,
                       listing.matched_title, listing.seller, listing.confidence, listing.verified
                  FROM marketplace_listings listing
                  JOIN products product ON product.row_id = listing.row_id
                 WHERE listing.available = 1 AND product.sourcing_origin = ?`).bind(origin),
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
    sourcing_origin: row.sourcing_origin ?? origin,
    category: row.category ?? null,
    source_sheet: row.source_sheet ?? null,
    source_row: row.source_row ?? null,
    source_cost_edited_at: row.source_cost_edited_at ?? null,
    mrp_edited_at: row.mrp_edited_at ?? null,
    sources: listingsByRow.get(row.row_id) ?? {},
  }))

  const channels = orderChannels(counts.keys())

  return {
    success: true,
    origin,
    product_count: products.length,
    listing_count: listingRows.length,
    source_columns: channels,
    source_listing_counts: Object.fromEntries(channels.map((channel) => [channel, counts.get(channel) ?? 0])),
    categories: [...new Set(products.map((p) => p.category).filter((c): c is string => !!c))].sort(),
    products,
  }
}

export async function fetchDashboardMeta(db: D1Database, origin: SourcingOrigin = 'local'): Promise<DashboardMeta> {
  const [countsResult, brandsResult, channelsResult, originsResult, categoriesResult] = await db.batch([
    db.prepare(`SELECT (SELECT COUNT(*) FROM products WHERE sourcing_origin = ?1) AS product_count,
                       (SELECT COUNT(*) FROM marketplace_listings listing
                          JOIN products product ON product.row_id = listing.row_id
                         WHERE listing.available = 1 AND product.sourcing_origin = ?1) AS listing_count`).bind(origin),
    db.prepare('SELECT DISTINCT brand_name FROM products WHERE sourcing_origin = ? ORDER BY brand_name').bind(origin),
    db.prepare(`SELECT listing.channel_name, COUNT(*) AS listing_count
                  FROM marketplace_listings listing
                  JOIN products product ON product.row_id = listing.row_id
                 WHERE listing.available = 1 AND product.sourcing_origin = ?
                 GROUP BY listing.channel_name`).bind(origin),
    // Both sides at once: the origin switch shows the size of the book it isn't on.
    db.prepare('SELECT sourcing_origin, COUNT(*) AS product_count FROM products GROUP BY sourcing_origin'),
    db.prepare(`SELECT DISTINCT category FROM products
                 WHERE sourcing_origin = ? AND category IS NOT NULL ORDER BY category`).bind(origin),
  ])

  const counts = countsResult?.results[0] as { product_count?: number; listing_count?: number } | undefined
  const channelCounts = (channelsResult?.results ?? []) as Array<{ channel_name: string }>
  const originRows = (originsResult?.results ?? []) as Array<{ sourcing_origin: SourcingOrigin; product_count: number }>

  const originCounts: Record<SourcingOrigin, number> = { local: 0, imported: 0 }
  for (const row of originRows) {
    if (row.sourcing_origin === 'local' || row.sourcing_origin === 'imported') {
      originCounts[row.sourcing_origin] = Number(row.product_count ?? 0)
    }
  }

  return {
    origin,
    productCount: Number(counts?.product_count ?? 0),
    listingCount: Number(counts?.listing_count ?? 0),
    originCounts,
    brands: ((brandsResult?.results ?? []) as Array<{ brand_name: string }>).map((row) => row.brand_name),
    channels: orderChannels(channelCounts.map((row) => row.channel_name)),
    categories: ((categoriesResult?.results ?? []) as Array<{ category: string }>).map((row) => row.category),
  }
}
