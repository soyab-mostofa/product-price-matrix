export async function onRequestPost(context) {
  const { env, request } = context;
  try {
    const body = await request.json();
    const { productName, packaging, transport, delivery, cac, targetMarginPct, discountType, discountVal } = body;

    if (!productName) {
      return new Response(JSON.stringify({ success: false, error: "productName is required" }), {
        status: 400,
        headers: { "Content-Type": "application/json" }
      });
    }

    await env.DB.prepare(
      `INSERT OR REPLACE INTO product_pricing_overrides (product_name, packaging, transport, delivery, cac, target_margin_pct, discount_type, discount_val, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)`
    ).bind(
      productName,
      Number(packaging) || 0,
      Number(transport) || 0,
      Number(delivery) || 0,
      Number(cac) || 0,
      Number(targetMarginPct) || 0,
      discountType || 'pct',
      Number(discountVal) || 0
    ).run();

    return new Response(JSON.stringify({ success: true, message: `Override saved for ${productName}` }), {
      headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
    });
  } catch (err) {
    return new Response(JSON.stringify({ success: false, error: err.message }), {
      status: 500,
      headers: { "Content-Type": "application/json" }
    });
  }
}

export async function onRequestDelete(context) {
  const { env, request } = context;
  try {
    const url = new URL(request.url);
    const productName = url.searchParams.get("productName");
    const resetAll = url.searchParams.get("all") === "true";

    if (resetAll) {
      await env.DB.prepare("DELETE FROM product_pricing_overrides").run();
      return new Response(JSON.stringify({ success: true, message: "All product overrides cleared" }), {
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
      });
    }

    if (!productName) {
      return new Response(JSON.stringify({ success: false, error: "productName parameter is required" }), {
        status: 400,
        headers: { "Content-Type": "application/json" }
      });
    }

    await env.DB.prepare("DELETE FROM product_pricing_overrides WHERE product_name = ?").bind(productName).run();

    return new Response(JSON.stringify({ success: true, message: `Override removed for ${productName}` }), {
      headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
    });
  } catch (err) {
    return new Response(JSON.stringify({ success: false, error: err.message }), {
      status: 500,
      headers: { "Content-Type": "application/json" }
    });
  }
}
