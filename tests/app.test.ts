import { describe, expect, test } from 'bun:test'
import app from '../src/index'
import { PRICING_DEFAULTS } from '../src/server/pricing'
import type { EnvBindings } from '../src/types'

function fakeDb({ products = [], listings = [], globalParams = null, overrides = [] }: any = {}) {
  const seen: string[] = []
  return {
    seen,
    batch(statements: any[]) {
      return Promise.all(statements.map((stmt) => stmt.all ? stmt.all() : stmt.first()))
    },
    prepare(sql: string) {
      // Origin filtering happens in SQL, so the fake binds the same way the
      // worker does: whatever origin is bound narrows both products and their
      // listings, exactly as the real WHERE clause would.
      let bound: any[] = []
      const origin = () => bound.find((value) => value === 'local' || value === 'imported')
      const visibleProducts = () => {
        const wanted = origin()
        return wanted ? products.filter((p: any) => p.sourcing_origin === wanted) : products
      }
      const visibleListings = () => {
        const rows = new Set(visibleProducts().map((p: any) => p.row_id))
        return origin() ? listings.filter((l: any) => rows.has(l.row_id)) : listings
      }
      return {
        bind(...args: any[]) {
          bound = args
          return this
        },
        async first() {
          seen.push(sql)
          if (sql.includes('FROM global_pricing_params')) return globalParams
          if (sql.includes('SELECT (SELECT COUNT(*)')) {
            return { product_count: visibleProducts().length, listing_count: visibleListings().length }
          }
          return null
        },
        async all() {
          seen.push(sql)
          if (sql.includes('FROM products') && sql.includes('ORDER BY row_id')) return { results: visibleProducts() }
          if (sql.includes('DISTINCT brand_name')) return { results: [...new Set(visibleProducts().map((p: any) => ({ brand_name: p.brand_name })))] }
          if (sql.includes('GROUP BY sourcing_origin')) {
            const tally = new Map<string, number>()
            for (const p of products) tally.set(p.sourcing_origin, (tally.get(p.sourcing_origin) ?? 0) + 1)
            return { results: [...tally].map(([sourcing_origin, product_count]) => ({ sourcing_origin, product_count })) }
          }
          if (sql.includes('DISTINCT category')) {
            const found = [...new Set(visibleProducts().map((p: any) => p.category).filter(Boolean))].sort()
            return { results: found.map((category) => ({ category })) }
          }
          if (sql.includes('GROUP BY listing.channel_name') || sql.includes('GROUP BY channel_name')) {
            return { results: visibleListings().map((l: any) => ({ channel_name: l.channel_name, listing_count: 1 })) }
          }
          if (sql.includes('marketplace_listings')) return { results: visibleListings() }
          if (sql.includes('FROM product_pricing_overrides')) return { results: overrides }
          return { results: [] }
        },
        async run() {
          seen.push(sql)
          return { success: true }
        },
      }
    },
  }
}

const env: EnvBindings = {
  DB: fakeDb({
    products: [{
      row_id: 1,
      product_name: 'Test Serum',
      brand_name: 'Guerniss',
      size: '30ml',
      manufactured_price: 100,
      market_average_price: 200,
      canonical_name: 'Test Serum',
      mrp_source_type: 'official',
      sourcing_origin: 'local',
      category: null,
    }],
    listings: [{
      row_id: 1,
      channel_name: 'Official Store',
      price: 200,
      url: 'https://example.com/item',
      matched_title: 'Test Serum 30ml',
      seller: 'Guerniss Official',
      confidence: 100,
      available: 1,
      verified: 1,
    }],
    globalParams: PRICING_DEFAULTS,
  }) as any,
  ADMIN_PASSWORD: 'correct-horse-battery-staple',
  SESSION_SECRET: 'long-secret-key-for-testing-hono-app',
}

async function loginCookie(testEnv: EnvBindings = env): Promise<string> {
  const response = await app.request('https://matrix.example/api/auth', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Origin: 'https://matrix.example',
      'X-Price-Matrix-Admin': '1',
    },
    body: JSON.stringify({ password: testEnv.ADMIN_PASSWORD }),
  }, testEnv)
  expect(response.status).toBe(200)
  return response.headers.get('Set-Cookie')?.split(';', 1)[0] ?? ''
}

describe('Hono application', () => {
  test('serves SSR layout from GET / with live meta', async () => {
    const res = await app.request('/', {}, env)
    expect(res.status).toBe(200)
    const text = await res.text()
    expect(text).toContain('Price Matrix')
    expect(text).toContain('/static/app.js')
  })

  test('the CAC inputs accept a fractional percentage', async () => {
    // A percentage CAC is routinely fractional (5%, 7.5%, 12.5%). These inputs
    // sit in a <form>, so a step that forbids decimals makes the browser refuse
    // to submit and the save silently does nothing.
    const text = await (await app.request('/', {}, env)).text()
    for (const id of ['inputCAC', 'prodInputCAC']) {
      const tag = text.match(new RegExp(`<input[^>]*id="${id}"[^>]*>`))?.[0]
      expect(tag).toBeString()
      const step = tag!.match(/step="([^"]+)"/)?.[1]
      expect(step).toBeString()
      expect(Number(step)).toBeLessThan(1)
    }
  })

  test('serves public products JSON from GET /api/products', async () => {
    const res = await app.request('/api/products', {}, env)
    expect(res.status).toBe(200)
    const data = await res.json() as any
    expect(data.success).toBe(true)
    expect(data.product_count).toBe(1)
    expect(data.listing_count).toBe(1)
    expect(data.source_columns).toEqual(['Official Store'])
  })

  test('carries listing verification through to the catalog payload', async () => {
    const mixedEnv = {
      ...env,
      DB: fakeDb({
        products: [{
          row_id: 1,
          product_name: 'CeraVe Moisturizing Cream 56ml',
          brand_name: 'CeraVe',
          size: '56ml',
          manufactured_price: 930,
          market_average_price: 1465,
          canonical_name: 'CeraVe Moisturizing Cream 56ml',
          mrp_source_type: 'third_party_avg',
          sourcing_origin: 'local',
          category: null,
        }],
        listings: [
          {
            row_id: 1,
            channel_name: 'Shajgoj',
            price: 1465,
            url: 'https://shajgoj.com/cerave',
            matched_title: 'CeraVe Moisturizing Cream',
            seller: 'Shajgoj',
            confidence: 100,
            available: 1,
            verified: 1,
          },
          {
            // Seeded from the workbook: a real price with no product page yet.
            row_id: 1,
            channel_name: 'Klassy Missy',
            price: 1450,
            url: null,
            matched_title: null,
            seller: null,
            confidence: 100,
            available: 1,
            verified: 0,
          },
        ],
        globalParams: PRICING_DEFAULTS,
      }) as any,
    }

    const res = await app.request('/api/products', {}, mixedEnv)
    expect(res.status).toBe(200)
    const data = await res.json() as any
    const sources = data.products[0].sources

    expect(sources['Shajgoj'].verified).toBe(true)
    expect(sources['Shajgoj'].url).toBe('https://shajgoj.com/cerave')

    // An unverified listing still carries its price — that research is real.
    expect(sources['Klassy Missy'].verified).toBe(false)
    expect(sources['Klassy Missy'].price).toBe(1450)
    expect(sources['Klassy Missy'].url).toBeNull()
  })

  test('serves only local SKUs from / and only imported SKUs from /imported', async () => {
    const splitDb = () => fakeDb({
      products: [
        {
          row_id: 1, product_name: 'Guerniss Matte Lipstick 03', brand_name: 'Guerniss',
          size: '4g', manufactured_price: 100, market_average_price: 200,
          canonical_name: 'Guerniss Matte Lipstick 03', mrp_source_type: 'official',
          sourcing_origin: 'local', category: null,
        },
        {
          row_id: 2, product_name: 'CeraVe Moisturizing Cream 56ml', brand_name: 'CeraVe',
          size: '56ml', manufactured_price: 930, market_average_price: 1465,
          canonical_name: 'CeraVe Moisturizing Cream 56ml', mrp_source_type: 'third_party_avg',
          sourcing_origin: 'imported', category: 'Skincare',
        },
      ],
      listings: [
        {
          row_id: 1, channel_name: 'Official Store', price: 200, url: 'https://guerniss.com/x',
          matched_title: null, seller: null, confidence: 100, available: 1, verified: 1,
        },
        {
          row_id: 2, channel_name: 'Klassy Missy', price: 1450, url: null,
          matched_title: null, seller: null, confidence: 100, available: 1, verified: 0,
        },
      ],
      globalParams: PRICING_DEFAULTS,
    }) as any

    const localRes = await app.request('/api/products', {}, { ...env, DB: splitDb() })
    const local = await localRes.json() as any
    expect(local.product_count).toBe(1)
    expect(local.products[0].product_name).toBe('Guerniss Matte Lipstick 03')
    // A channel that only carries imported SKUs must not pad the local view.
    expect(local.source_columns).toEqual(['Official Store'])

    const importedRes = await app.request('/api/products?origin=imported', {}, { ...env, DB: splitDb() })
    const imported = await importedRes.json() as any
    expect(imported.product_count).toBe(1)
    expect(imported.products[0].product_name).toBe('CeraVe Moisturizing Cream 56ml')
    expect(imported.products[0].category).toBe('Skincare')
    expect(imported.source_columns).toEqual(['Klassy Missy'])
  })

  test('serves the imported dashboard at GET /imported', async () => {
    const res = await app.request('/imported', {}, env)
    expect(res.status).toBe(200)
    const text = await res.text()
    expect(text).toContain('Price Matrix')
    expect(text).toContain('/static/app.js')
  })

  test('rejects an unknown origin rather than silently serving everything', async () => {
    const res = await app.request('/api/products?origin=wholesale', {}, env)
    expect(res.status).toBe(400)
  })

  test('creates signed admin sessions and rejects tampered cookies', async () => {
    const cookie = await loginCookie()
    expect(cookie).toStartWith('price_matrix_admin=')

    const authenticated = await app.request('https://matrix.example/api/auth', {
      headers: { Cookie: cookie },
    }, env)
    expect(authenticated.status).toBe(200)
    expect((await authenticated.json() as any).authenticated).toBe(true)

    const tampered = await app.request('https://matrix.example/api/auth', {
      headers: { Cookie: `${cookie}x` },
    }, env)
    expect((await tampered.json() as any).authenticated).toBe(false)
  })

  test('rejects cross-origin admin login attempts', async () => {
    const res = await app.request('https://matrix.example/api/auth', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Origin: 'https://attacker.example',
        'X-Price-Matrix-Admin': '1',
      },
      body: JSON.stringify({ password: env.ADMIN_PASSWORD }),
    }, env)
    expect(res.status).toBe(403)
  })

  test('validates authenticated pricing writes before touching D1', async () => {
    const db = fakeDb()
    const testEnv: EnvBindings = {
      DB: db as any,
      ADMIN_PASSWORD: 'correct-horse-battery-staple',
      SESSION_SECRET: 'another-long-secret-key-for-testing',
    }
    const cookie = await loginCookie(testEnv)
    db.seen.length = 0

    const res = await app.request('https://matrix.example/api/engine', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Origin: 'https://matrix.example',
        Cookie: cookie,
        'X-Price-Matrix-Admin': '1',
      },
      body: JSON.stringify({ ...PRICING_DEFAULTS, discountVal: 150 }),
    }, testEnv)
    expect(res.status).toBe(400)
    expect(db.seen).toHaveLength(0)
  })

  test('blocks unauthenticated POST /api/engine with same-origin header', async () => {
    const res = await app.request('https://matrix.example/api/engine', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Origin: 'https://matrix.example',
        'X-Price-Matrix-Admin': '1',
      },
      body: JSON.stringify(PRICING_DEFAULTS),
    }, env)
    expect(res.status).toBe(401)
  })

  test('blocks cross-origin or missing header POST /api/engine with 403', async () => {
    const res = await app.request('/api/engine', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(PRICING_DEFAULTS),
    }, env)
    expect(res.status).toBe(403)
  })

  test('rejects malformed mutation referrers instead of throwing', async () => {
    const res = await app.request('https://matrix.example/api/engine', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Referer: 'not a valid URL',
        'X-Price-Matrix-Admin': '1',
      },
      body: JSON.stringify(PRICING_DEFAULTS),
    }, env)
    expect(res.status).toBe(403)
  })

  test('keeps GET /api/engine public so anyone can read prices', async () => {
    const res = await app.request('/api/engine', {}, env)
    expect(res.status).toBe(200)
    const data = await res.json() as any
    expect(data.success).toBe(true)
  })
})

describe('sparse per-product overrides', () => {
  function overrideEnv() {
    const db = fakeDb({
      products: [{ row_id: 1, product_name: 'Test Serum', brand_name: 'Guerniss', manufactured_price: 100, market_average_price: 200 }],
      globalParams: PRICING_DEFAULTS,
    })
    // The route looks the product up by row_id before writing.
    const originalPrepare = db.prepare.bind(db)
    db.prepare = (sql: string) => {
      const statement = originalPrepare(sql)
      if (sql.includes('SELECT row_id FROM products')) {
        return { ...statement, bind: () => ({ ...statement, first: async () => ({ row_id: 1 }) }) }
      }
      return statement
    }
    return {
      db,
      env: {
        DB: db as any,
        ADMIN_PASSWORD: 'correct-horse-battery-staple',
        SESSION_SECRET: 'long-secret-key-for-testing-hono-app',
      } satisfies EnvBindings,
    }
  }

  async function postOverride(testEnv: EnvBindings, cookie: string, body: unknown) {
    return app.request('https://matrix.example/api/overrides', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Origin: 'https://matrix.example',
        Cookie: cookie,
        'X-Price-Matrix-Admin': '1',
      },
      body: JSON.stringify(body),
    }, testEnv)
  }

  test('stores only the fields that differ from global', async () => {
    const { env: testEnv } = overrideEnv()
    const cookie = await loginCookie(testEnv)

    // Packaging echoes the global default; only the margin is a real tune.
    const res = await postOverride(testEnv, cookie, {
      productRowId: 1,
      override: { packaging: 45, targetMarginPct: 30 },
    })
    expect(res.status).toBe(200)
    const data = await res.json() as any
    expect(data.success).toBe(true)
    expect(data.override.targetMarginPct).toBe(30)
    expect(data.override.packaging).toBeUndefined()
    expect(data.override.updatedAt).toBeString()
  })

  test('clears the row when a tune pins nothing', async () => {
    const { db, env: testEnv } = overrideEnv()
    const cookie = await loginCookie(testEnv)
    db.seen.length = 0

    const res = await postOverride(testEnv, cookie, {
      productRowId: 1,
      override: { packaging: 45, cacType: 'pct', cac: 5 }, // all identical to global
    })
    expect(res.status).toBe(200)
    const data = await res.json() as any
    expect(data.cleared).toBe(true)
    expect(data.override).toBeNull()
    expect(db.seen.some((sql) => sql.includes('DELETE FROM product_pricing_overrides'))).toBe(true)
    expect(db.seen.some((sql) => sql.includes('INSERT INTO product_pricing_overrides'))).toBe(false)
  })

  test('rejects half a discount pair before touching D1', async () => {
    const { db, env: testEnv } = overrideEnv()
    const cookie = await loginCookie(testEnv)
    db.seen.length = 0

    const res = await postOverride(testEnv, cookie, {
      productRowId: 1,
      override: { discountType: 'amt' },
    })
    expect(res.status).toBe(400)
    expect(db.seen).toHaveLength(0)
  })

  test('blocks unauthenticated override writes', async () => {
    const { env: testEnv } = overrideEnv()
    const res = await app.request('https://matrix.example/api/overrides', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Origin: 'https://matrix.example',
        'X-Price-Matrix-Admin': '1',
      },
      body: JSON.stringify({ productRowId: 1, override: { targetMarginPct: 30 } }),
    }, testEnv)
    expect(res.status).toBe(401)
  })

  test('blocks unauthenticated bulk override deletion', async () => {
    const { db, env: testEnv } = overrideEnv()
    db.seen.length = 0
    const res = await app.request('https://matrix.example/api/overrides?all=true', {
      method: 'DELETE',
      headers: { Origin: 'https://matrix.example', 'X-Price-Matrix-Admin': '1' },
    }, testEnv)
    expect(res.status).toBe(401)
    expect(db.seen).toHaveLength(0)
  })
})
