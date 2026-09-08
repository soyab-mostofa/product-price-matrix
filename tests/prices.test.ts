import { describe, expect, test } from 'bun:test'
import { Database } from 'bun:sqlite'
import { readFileSync } from 'node:fs'
import app from '../src/index'
import type { EnvBindings } from '../src/types'

/**
 * A real SQLite database behind a D1-shaped adapter.
 *
 * tests/app.test.ts uses a hand-rolled fake whose `run()` returns
 * `{ success: true }` without executing anything. That is right for read-path
 * assertions, but this suite is about writes: journal rows, CHECK constraints,
 * and mrp_source_type transitions. Against a fake, those assertions would only
 * prove the fake agrees with itself — so this runs the real schema.
 */
function sqliteD1(): D1Database & { raw: Database } {
  const db = new Database(':memory:')
  db.exec('PRAGMA foreign_keys = ON')
  db.exec(readFileSync('schema.sql', 'utf8'))

  db.exec(`
    INSERT INTO products
      (row_id, product_name, brand_name, size, manufactured_price,
       market_average_price, canonical_name, mrp_source_type, sourcing_origin,
       source_sheet, source_row)
    VALUES
      (2, 'Bio-Screen Powder Sunblock SPF 50+', 'Bio-Screen', '12gm',
       1237.5, 1650.0, 'Bio-Screen Powder Sunblock SPF 50+', 'workbook', 'local',
       'Local product ', 2),
      (500, 'Simple Face Wash Refreshing Gel 150ml (uk)', 'Simple', '150ml',
       425.0, 749.0, 'Simple Face Wash Refreshing Gel 150ml (uk)', 'official',
       'imported', 'imported Skincare', 2);
  `)

  // An imported SKU resolves its MRP provenance from listings, so a revert has
  // to have something to resolve against — otherwise the test would assert
  // 'official' for a row with no official listing and pass on a lie.
  db.exec(`
    INSERT INTO marketplace_listings
      (row_id, channel_name, price, url, matched_title, seller, confidence, available, verified)
    VALUES
      (500, 'Official Store', 749.0, 'https://example.com/simple-face-wash',
       'Simple Face Wash Refreshing Gel 150ml', 'Simple Official', 100.0, 1, 1);
  `)

  const prepare = (sql: string) => {
    let bound: unknown[] = []
    const statement = {
      bind(...args: unknown[]) {
        bound = args
        return statement
      },
      async first<T>(): Promise<T | null> {
        return (db.query(sql).get(...(bound as never[])) as T) ?? null
      },
      async all<T>(): Promise<{ results: T[] }> {
        return { results: db.query(sql).all(...(bound as never[])) as T[] }
      },
      async run() {
        db.query(sql).run(...(bound as never[]))
        return { success: true }
      },
    }
    return statement
  }

  return {
    raw: db,
    prepare,
    async batch(statements: Array<{ run: () => Promise<unknown> }>) {
      const out = []
      for (const statement of statements) out.push(await statement.run())
      return out
    },
  } as unknown as D1Database & { raw: Database }
}

function envWith(db: D1Database): EnvBindings {
  return {
    DB: db,
    ADMIN_PASSWORD: 'correct-horse-battery-staple',
    SESSION_SECRET: 'long-secret-key-for-testing-hono-app',
  }
}

async function loginCookie(env: EnvBindings): Promise<string> {
  const response = await app.request('https://matrix.example/api/auth', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Origin: 'https://matrix.example',
      'X-Price-Matrix-Admin': '1',
    },
    body: JSON.stringify({ password: env.ADMIN_PASSWORD }),
  }, env)
  expect(response.status).toBe(200)
  return response.headers.get('Set-Cookie')?.split(';', 1)[0] ?? ''
}

function editRequest(cookie: string, body: unknown) {
  return {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Origin: 'https://matrix.example',
      'X-Price-Matrix-Admin': '1',
      Cookie: cookie,
    },
    body: JSON.stringify(body),
  }
}

async function edit(env: EnvBindings, cookie: string, body: unknown) {
  return app.request('https://matrix.example/api/prices', editRequest(cookie, body), env)
}

describe('PATCH /api/prices', () => {
  test('rejects an unauthenticated edit', async () => {
    const env = envWith(sqliteD1())
    const res = await app.request('https://matrix.example/api/prices', {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Origin: 'https://matrix.example',
        'X-Price-Matrix-Admin': '1',
      },
      body: JSON.stringify({ productRowId: 2, field: 'source_cost', value: 1300 }),
    }, env)
    expect(res.status).toBe(401)
  })

  test('rejects an edit without the same-origin admin header', async () => {
    const env = envWith(sqliteD1())
    const cookie = await loginCookie(env)
    const res = await app.request('https://matrix.example/api/prices', {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Origin: 'https://matrix.example',
        Cookie: cookie,
      },
      body: JSON.stringify({ productRowId: 2, field: 'source_cost', value: 1300 }),
    }, env)
    expect(res.status).toBe(403)
  })

  test('writes the new source cost and journals the change', async () => {
    const db = sqliteD1()
    const env = envWith(db)
    const cookie = await loginCookie(env)

    const res = await edit(env, cookie, { productRowId: 2, field: 'source_cost', value: 1300 })
    expect(res.status).toBe(200)
    const body = await res.json() as any
    expect(body.changed).toBe(true)
    expect(body.previousValue).toBe(1237.5)
    expect(body.workbookValue).toBe(1237.5)

    const product = db.raw.query('SELECT manufactured_price FROM products WHERE row_id = 2').get() as any
    expect(product.manufactured_price).toBe(1300)

    const journal = db.raw.query('SELECT * FROM price_edits').all() as any[]
    expect(journal).toHaveLength(1)
    expect(journal[0].field).toBe('source_cost')
    expect(journal[0].old_value).toBe(1237.5)
    expect(journal[0].new_value).toBe(1300)
    expect(journal[0].folded).toBe(0)
  })

  test('an edited MRP stops claiming to be the workbook benchmark', async () => {
    const db = sqliteD1()
    const env = envWith(db)
    const cookie = await loginCookie(env)

    await edit(env, cookie, { productRowId: 2, field: 'mrp', value: 1700 })

    const product = db.raw.query(
      'SELECT market_average_price, mrp_source_type FROM products WHERE row_id = 2',
    ).get() as any
    expect(product.market_average_price).toBe(1700)
    expect(product.mrp_source_type).toBe('manual')
  })

  test('editing source cost leaves MRP provenance alone', async () => {
    const db = sqliteD1()
    const env = envWith(db)
    const cookie = await loginCookie(env)

    await edit(env, cookie, { productRowId: 2, field: 'source_cost', value: 1300 })

    const product = db.raw.query('SELECT mrp_source_type FROM products WHERE row_id = 2').get() as any
    expect(product.mrp_source_type).toBe('workbook')
  })

  test('successive edits keep pointing at the workbook baseline', async () => {
    const db = sqliteD1()
    const env = envWith(db)
    const cookie = await loginCookie(env)

    await edit(env, cookie, { productRowId: 2, field: 'source_cost', value: 1300 })
    const second = await edit(env, cookie, { productRowId: 2, field: 'source_cost', value: 1400 })
    const body = await second.json() as any

    expect(body.previousValue).toBe(1300)
    expect(body.workbookValue).toBe(1237.5)

    const baselines = db.raw.query('SELECT DISTINCT workbook_value FROM price_edits').all() as any[]
    expect(baselines).toHaveLength(1)
    expect(baselines[0].workbook_value).toBe(1237.5)
  })

  test('a no-op edit is reported honestly and never journalled', async () => {
    const db = sqliteD1()
    const env = envWith(db)
    const cookie = await loginCookie(env)

    const res = await edit(env, cookie, { productRowId: 2, field: 'source_cost', value: 1237.5 })
    expect(res.status).toBe(200)
    expect((await res.json() as any).changed).toBe(false)

    const journal = db.raw.query('SELECT COUNT(*) AS n FROM price_edits').get() as any
    expect(journal.n).toBe(0)
  })

  test('rejects an unknown SKU', async () => {
    const env = envWith(sqliteD1())
    const cookie = await loginCookie(env)
    const res = await edit(env, cookie, { productRowId: 99999, field: 'source_cost', value: 100 })
    expect(res.status).toBe(404)
  })

  test('rejects invalid values and unknown fields', async () => {
    const env = envWith(sqliteD1())
    const cookie = await loginCookie(env)

    for (const body of [
      { productRowId: 2, field: 'source_cost', value: -1 },
      { productRowId: 2, field: 'source_cost', value: 'abc' },
      { productRowId: 2, field: 'discount_rate', value: 10 },
      { productRowId: 2, field: 'source_cost', value: 5_000_000 },
    ]) {
      const res = await edit(env, cookie, body)
      expect(res.status).toBe(400)
    }
  })

  test('imported SKUs are editable on both fields', async () => {
    const db = sqliteD1()
    const env = envWith(db)
    const cookie = await loginCookie(env)

    expect((await edit(env, cookie, { productRowId: 500, field: 'source_cost', value: 450 })).status).toBe(200)
    expect((await edit(env, cookie, { productRowId: 500, field: 'mrp', value: 800 })).status).toBe(200)

    const product = db.raw.query(
      'SELECT manufactured_price, market_average_price FROM products WHERE row_id = 500',
    ).get() as any
    expect(product.manufactured_price).toBe(450)
    expect(product.market_average_price).toBe(800)
  })
})

describe('DELETE /api/prices (revert)', () => {
  test('restores the workbook figure and journals the revert', async () => {
    const db = sqliteD1()
    const env = envWith(db)
    const cookie = await loginCookie(env)

    await edit(env, cookie, { productRowId: 2, field: 'source_cost', value: 1300 })
    await edit(env, cookie, { productRowId: 2, field: 'source_cost', value: 1400 })

    const res = await app.request(
      'https://matrix.example/api/prices?productRowId=2&field=source_cost',
      {
        method: 'DELETE',
        headers: {
          Origin: 'https://matrix.example',
          'X-Price-Matrix-Admin': '1',
          Cookie: cookie,
        },
      },
      env,
    )
    expect(res.status).toBe(200)
    const body = await res.json() as any
    expect(body.reverted).toBe(true)
    expect(body.value).toBe(1237.5)

    const product = db.raw.query('SELECT manufactured_price FROM products WHERE row_id = 2').get() as any
    expect(product.manufactured_price).toBe(1237.5)

    // The revert is itself an edit, so the fold script carries it downstream.
    const journal = db.raw.query('SELECT * FROM price_edits ORDER BY id').all() as any[]
    expect(journal).toHaveLength(3)
    expect(journal[2].new_value).toBe(1237.5)
    expect(journal[2].folded).toBe(0)
  })

  test('a reverted local MRP is the workbook benchmark again', async () => {
    const db = sqliteD1()
    const env = envWith(db)
    const cookie = await loginCookie(env)

    await edit(env, cookie, { productRowId: 2, field: 'mrp', value: 1700 })
    expect(
      (db.raw.query('SELECT mrp_source_type FROM products WHERE row_id = 2').get() as any).mrp_source_type,
    ).toBe('manual')

    await app.request(
      'https://matrix.example/api/prices?productRowId=2&field=mrp',
      {
        method: 'DELETE',
        headers: { Origin: 'https://matrix.example', 'X-Price-Matrix-Admin': '1', Cookie: cookie },
      },
      env,
    )

    const product = db.raw.query(
      'SELECT market_average_price, mrp_source_type FROM products WHERE row_id = 2',
    ).get() as any
    expect(product.market_average_price).toBe(1650)
    expect(product.mrp_source_type).toBe('workbook')
  })

  test('a reverted imported MRP does not claim workbook provenance', async () => {
    const db = sqliteD1()
    const env = envWith(db)
    const cookie = await loginCookie(env)

    await edit(env, cookie, { productRowId: 500, field: 'mrp', value: 900 })
    await app.request(
      'https://matrix.example/api/prices?productRowId=500&field=mrp',
      {
        method: 'DELETE',
        headers: { Origin: 'https://matrix.example', 'X-Price-Matrix-Admin': '1', Cookie: cookie },
      },
      env,
    )

    const product = db.raw.query('SELECT mrp_source_type FROM products WHERE row_id = 500').get() as any
    expect(product.mrp_source_type).toBe('official')
  })

  // A live probe caught this: a 'reference' SKU came back as 'third_party_avg'
  // after an undo, because the resolver counted any AVAILABLE listing while
  // seed_imported.py counts only listings that are available AND VERIFIED. The
  // two predicates must stay identical or undo silently rewrites provenance.
  test('an unverified listing does not promote a reference SKU on revert', async () => {
    const db = sqliteD1()
    const env = envWith(db)
    const cookie = await loginCookie(env)

    db.raw.exec(`
      INSERT INTO products
        (row_id, product_name, brand_name, size, manufactured_price, market_average_price,
         canonical_name, mrp_source_type, sourcing_origin, source_sheet, source_row)
      VALUES
        (501, 'Dove Pink Moisturising Beauty Bar 100g', 'Dove', '100g',
         225.0, 235.5, 'Dove Pink Moisturising Beauty Bar 100g', 'reference',
         'imported', 'imported Skincare', 3);
      INSERT INTO marketplace_listings
        (row_id, channel_name, price, url, matched_title, seller, confidence, available, verified)
      VALUES
        (501, 'Daraz', 240.0, 'https://example.com/dove-bar',
         'Dove Pink Beauty Bar 100g', 'Daraz Seller', 80.0, 1, 0);
    `)

    await edit(env, cookie, { productRowId: 501, field: 'mrp', value: 300 })
    await app.request(
      'https://matrix.example/api/prices?productRowId=501&field=mrp',
      {
        method: 'DELETE',
        headers: { Origin: 'https://matrix.example', 'X-Price-Matrix-Admin': '1', Cookie: cookie },
      },
      env,
    )

    const product = db.raw.query(
      'SELECT market_average_price, mrp_source_type FROM products WHERE row_id = 501',
    ).get() as any
    expect(product.market_average_price).toBe(235.5)
    expect(product.mrp_source_type).toBe('reference')
  })

  test('reverting an unedited price changes nothing', async () => {
    const db = sqliteD1()
    const env = envWith(db)
    const cookie = await loginCookie(env)

    const res = await app.request(
      'https://matrix.example/api/prices?productRowId=2&field=source_cost',
      {
        method: 'DELETE',
        headers: { Origin: 'https://matrix.example', 'X-Price-Matrix-Admin': '1', Cookie: cookie },
      },
      env,
    )
    expect((await res.json() as any).changed).toBe(false)
    expect((db.raw.query('SELECT COUNT(*) AS n FROM price_edits').get() as any).n).toBe(0)
  })

  test('rejects an unauthenticated revert', async () => {
    const env = envWith(sqliteD1())
    const res = await app.request(
      'https://matrix.example/api/prices?productRowId=2&field=source_cost',
      { method: 'DELETE', headers: { Origin: 'https://matrix.example', 'X-Price-Matrix-Admin': '1' } },
      env,
    )
    expect(res.status).toBe(401)
  })
})
