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
      return {
        bind() {
          return this
        },
        async first() {
          seen.push(sql)
          if (sql.includes('FROM global_pricing_params')) return globalParams
          if (sql.includes('SELECT (SELECT COUNT(*)')) return { product_count: products.length, listing_count: listings.length }
          return null
        },
        async all() {
          seen.push(sql)
          if (sql.includes('FROM products ORDER BY row_id')) return { results: products }
          if (sql.includes('FROM marketplace_listings WHERE available = 1')) return { results: listings }
          if (sql.includes('DISTINCT brand_name')) return { results: [...new Set(products.map((p: any) => ({ brand_name: p.brand_name })))] }
          if (sql.includes('GROUP BY channel_name')) return { results: listings.map((l: any) => ({ channel_name: l.channel_name, listing_count: 1 })) }
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

  test('serves public products JSON from GET /api/products', async () => {
    const res = await app.request('/api/products', {}, env)
    expect(res.status).toBe(200)
    const data = await res.json() as any
    expect(data.success).toBe(true)
    expect(data.product_count).toBe(1)
    expect(data.listing_count).toBe(1)
    expect(data.source_columns).toEqual(['Official Store'])
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
})
