/**
 * The catalog read path against a REAL database.
 *
 * tests/app.test.ts drives fetchCatalog through a hand-rolled fake that matches
 * on SQL substrings. That fake silently returned zero rows when the query was
 * aliased (`FROM products product`), and the suite still reported the shape it
 * expected — so a fake-only assertion cannot prove the query works. These run
 * the real schema.sql.
 */
import { describe, expect, test } from 'bun:test'
import { Database } from 'bun:sqlite'
import { readFileSync } from 'node:fs'
import { fetchCatalog } from '../src/server/catalog'

function realDb(): D1Database {
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
      (3, 'BioCare Vitamin C Whitening Facial Cream', 'BioCare', '50ml',
       1612.5, 2150.0, 'BioCare Vitamin C Whitening Facial Cream', 'workbook', 'local',
       'Local product ', 3),
      (500, 'Simple Face Wash Refreshing Gel 150ml (uk)', 'Simple', '150ml',
       425.0, 749.0, 'Simple Face Wash Refreshing Gel 150ml (uk)', 'official',
       'imported', 'imported Skincare', 2);
    INSERT INTO marketplace_listings
      (row_id, channel_name, price, url, matched_title, seller, confidence, available, verified)
    VALUES
      (2, 'Official Store', 1402.0, 'https://bioxin.com/en/product/x', 'Bio-Screen', 'Bio-Xin', 100.0, 1, 1);
  `)

  const prepare = (sql: string) => {
    let bound: unknown[] = []
    const statement = {
      bind(...args: unknown[]) {
        bound = args
        return statement
      },
      async first<T>() {
        return (db.query(sql).get(...(bound as never[])) as T) ?? null
      },
      async all<T>() {
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
    prepare,
    async batch(statements: Array<{ all: () => Promise<unknown> }>) {
      const out = []
      for (const statement of statements) out.push(await statement.all())
      return out
    },
  } as unknown as D1Database
}

describe('fetchCatalog against real SQLite', () => {
  test('returns every SKU for the requested origin', async () => {
    const db = realDb()

    const local = await fetchCatalog(db, 'local')
    expect(local.product_count).toBe(2)
    expect(local.products.map((p) => p.row).sort()).toEqual([2, 3])

    const imported = await fetchCatalog(db, 'imported')
    expect(imported.product_count).toBe(1)
    expect(imported.products[0]?.row).toBe(500)
  })

  test('prices come straight off products, not through the journal', async () => {
    const db = realDb()
    const catalog = await fetchCatalog(db, 'local')
    const sku = catalog.products.find((p) => p.row === 2)
    expect(sku?.manufactured_price).toBe(1237.5)
    expect(sku?.market_average_price).toBe(1650)
  })

  test('both edit flags are null until the SKU is actually edited', async () => {
    const db = realDb()
    const catalog = await fetchCatalog(db, 'local')
    for (const product of catalog.products) {
      expect(product.source_cost_edited_at).toBeNull()
      expect(product.mrp_edited_at).toBeNull()
    }
  })

  test('an edit surfaces its timestamp, and only on that SKU', async () => {
    const db = realDb()
    await db.prepare(
      `INSERT INTO price_edits
         (product_row_id, field, old_value, new_value, workbook_value, edited_at)
       VALUES (2, 'source_cost', 1237.5, 1300.0, 1237.5, '2026-09-07T10:00:00.000Z')`,
    ).run()

    const catalog = await fetchCatalog(db, 'local')
    const edited = catalog.products.find((p) => p.row === 2)
    const untouched = catalog.products.find((p) => p.row === 3)

    expect(edited?.source_cost_edited_at).toBe('2026-09-07T10:00:00.000Z')
    expect(untouched?.source_cost_edited_at).toBeNull()
  })

  // The regression: one timestamp for the whole row made an MRP-only edit
  // mark the untouched Source Cost as edited, offering to "revert" a figure
  // that already equalled the workbook.
  test('editing the MRP does not mark Source Cost as edited', async () => {
    const db = realDb()
    await db.prepare(
      `INSERT INTO price_edits
         (product_row_id, field, old_value, new_value, workbook_value, edited_at)
       VALUES (2, 'mrp', 1650.0, 1700.0, 1650.0, '2026-09-07T12:00:00.000Z')`,
    ).run()

    const sku = (await fetchCatalog(db, 'local')).products.find((p) => p.row === 2)
    expect(sku?.mrp_edited_at).toBe('2026-09-07T12:00:00.000Z')
    expect(sku?.source_cost_edited_at).toBeNull()
  })

  test('each field reports its own most recent edit', async () => {
    const db = realDb()
    await db.prepare(
      `INSERT INTO price_edits
         (product_row_id, field, old_value, new_value, workbook_value, edited_at)
       VALUES (2, 'source_cost', 1237.5, 1300.0, 1237.5, '2026-09-07T10:00:00.000Z')`,
    ).run()
    await db.prepare(
      `INSERT INTO price_edits
         (product_row_id, field, old_value, new_value, workbook_value, edited_at)
       VALUES (2, 'mrp', 1650.0, 1700.0, 1650.0, '2026-09-07T12:00:00.000Z')`,
    ).run()

    const sku = (await fetchCatalog(db, 'local')).products.find((p) => p.row === 2)
    expect(sku?.source_cost_edited_at).toBe('2026-09-07T10:00:00.000Z')
    expect(sku?.mrp_edited_at).toBe('2026-09-07T12:00:00.000Z')
  })

  // Undo appends a row restoring the workbook value. That row is the field's
  // latest, so the flag must clear -- not fall back to the earlier edit.
  test('a reverted field clears its flag while the other stays edited', async () => {
    const db = realDb()
    await db.prepare(
      `INSERT INTO price_edits
         (product_row_id, field, old_value, new_value, workbook_value, edited_at)
       VALUES (2, 'source_cost', 1237.5, 1300.0, 1237.5, '2026-09-07T10:00:00.000Z')`,
    ).run()
    await db.prepare(
      `INSERT INTO price_edits
         (product_row_id, field, old_value, new_value, workbook_value, edited_at)
       VALUES (2, 'mrp', 1650.0, 1700.0, 1650.0, '2026-09-07T11:00:00.000Z')`,
    ).run()
    // the undo of the source cost
    await db.prepare(
      `INSERT INTO price_edits
         (product_row_id, field, old_value, new_value, workbook_value, edited_at, reverted)
       VALUES (2, 'source_cost', 1300.0, 1237.5, 1237.5, '2026-09-07T12:00:00.000Z', 1)`,
    ).run()

    const sku = (await fetchCatalog(db, 'local')).products.find((p) => p.row === 2)
    expect(sku?.source_cost_edited_at).toBeNull()
    expect(sku?.mrp_edited_at).toBe('2026-09-07T11:00:00.000Z')
  })

  test('the journal join does not multiply rows', async () => {
    // A plain LEFT JOIN would return one product row per edit. The correlated
    // subquery must keep it at one row per SKU however many edits exist.
    const db = realDb()
    for (const at of ['10:00', '11:00', '12:00']) {
      await db.prepare(
        `INSERT INTO price_edits
           (product_row_id, field, old_value, new_value, workbook_value, edited_at)
         VALUES (2, 'source_cost', 1237.5, 1300.0, 1237.5, '2026-09-07T${at}:00.000Z')`,
      ).run()
    }

    const catalog = await fetchCatalog(db, 'local')
    expect(catalog.product_count).toBe(2)
    expect(catalog.products.filter((p) => p.row === 2)).toHaveLength(1)
  })

  test('listings still attach to their SKU', async () => {
    const db = realDb()
    const catalog = await fetchCatalog(db, 'local')
    const sku = catalog.products.find((p) => p.row === 2)
    expect(sku?.sources['Official Store']?.price).toBe(1402)
    expect(catalog.listing_count).toBe(1)
  })
})
