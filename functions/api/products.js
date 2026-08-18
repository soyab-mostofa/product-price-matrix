export async function onRequestGet(context) {
  const { env } = context;
  try {
    const productsRes = await env.DB.prepare(
      "SELECT row_id, product_name, brand_name, size, manufactured_price, market_average_price, canonical_name FROM products ORDER BY row_id ASC"
    ).all();

    const listingsRes = await env.DB.prepare(
      "SELECT row_id, channel_name, price, url, matched_title, size, seller, confidence, available FROM marketplace_listings"
    ).all();

    // Group listings by product row_id
    const listingsByRow = {};
    for (const l of listingsRes.results || []) {
      if (!listingsByRow[l.row_id]) listingsByRow[l.row_id] = {};
      listingsByRow[l.row_id][l.channel_name] = {
        price: l.price,
        url: l.url,
        matched_title: l.matched_title,
        size: l.size,
        seller: l.seller,
        confidence: l.confidence,
        available: Boolean(l.available)
      };
    }

    const products = (productsRes.results || []).map(p => ({
      row: p.row_id,
      product_name: p.product_name,
      brand_name: p.brand_name,
      size: p.size,
      manufactured_price: p.manufactured_price,
      market_average_price: p.market_average_price,
      canonical_name: p.canonical_name,
      sources: listingsByRow[p.row_id] || {}
    }));

    return new Response(JSON.stringify({
      success: true,
      product_count: products.length,
      products: products
    }), {
      headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
    });
  } catch (err) {
    return new Response(JSON.stringify({ success: false, error: err.message }), {
      status: 500,
      headers: { "Content-Type": "application/json" }
    });
  }
}
