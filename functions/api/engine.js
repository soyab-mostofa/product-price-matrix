export async function onRequestGet(context) {
  const { env } = context;
  try {
    // 1. Fetch global parameters
    const globalRes = await env.DB.prepare(
      "SELECT packaging, transport, delivery, cac, target_margin_pct as targetMarginPct, discount_type as discountType, discount_val as discountVal FROM global_pricing_params WHERE id = 1"
    ).first();

    // 2. Fetch all per-product overrides
    const overridesRes = await env.DB.prepare(
      "SELECT product_name, packaging, transport, delivery, cac, target_margin_pct as targetMarginPct, discount_type as discountType, discount_val as discountVal FROM product_pricing_overrides"
    ).all();

    const overrides = {};
    for (const row of overridesRes.results || []) {
      overrides[row.product_name] = {
        packaging: row.packaging,
        transport: row.transport,
        delivery: row.delivery,
        cac: row.cac,
        targetMarginPct: row.targetMarginPct,
        discountType: row.discountType,
        discountVal: row.discountVal
      };
    }

    return new Response(JSON.stringify({
      success: true,
      globalParams: globalRes || null,
      overrides: overrides
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

export async function onRequestPost(context) {
  const { env, request } = context;
  try {
    const body = await request.json();
    const { packaging, transport, delivery, cac, targetMarginPct, discountType, discountVal } = body;

    await env.DB.prepare(
      `INSERT OR REPLACE INTO global_pricing_params (id, packaging, transport, delivery, cac, target_margin_pct, discount_type, discount_val, updated_at)
       VALUES (1, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)`
    ).bind(
      Number(packaging) || 0,
      Number(transport) || 0,
      Number(delivery) || 0,
      Number(cac) || 0,
      Number(targetMarginPct) || 0,
      discountType || 'pct',
      Number(discountVal) || 0
    ).run();

    return new Response(JSON.stringify({ success: true, message: "Global pricing engine updated in D1" }), {
      headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
    });
  } catch (err) {
    return new Response(JSON.stringify({ success: false, error: err.message }), {
      status: 500,
      headers: { "Content-Type": "application/json" }
    });
  }
}
