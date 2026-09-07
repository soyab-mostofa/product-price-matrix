import { afterEach, describe, expect, test } from 'bun:test'
import { Database } from 'bun:sqlite'
import { readFileSync, unlinkSync } from 'node:fs'
import app from '../src/index'
import type { EnvBindings } from '../src/types'

const OUTPUT = '/tmp/product-price-matrix-export-route-test.xlsx'

afterEach(() => {
  try { unlinkSync(OUTPUT) } catch { /* absent */ }
})

function sqliteD1(): D1Database & { raw: Database } {
  const db = new Database(':memory:')
  db.exec('PRAGMA foreign_keys = ON')
  db.exec(readFileSync('schema.sql', 'utf8'))
  db.exec(`
    INSERT INTO global_pricing_params
      (id, packaging, transport, delivery, cac, cac_type,
       target_margin_pct, discount_type, discount_val)
    VALUES (1, 45, 0, 0, 5, 'pct', 0, 'pct', 0);

    INSERT INTO products
      (row_id, product_name, brand_name, size, manufactured_price,
       market_average_price, canonical_name, mrp_source_type, sourcing_origin,
       category, source_sheet, source_row)
    VALUES
      (2, 'Bio-Screen Powder Sunblock SPF 50+', 'Bio-Screen', '12gm',
       1300, 1650, 'Bio-Screen Powder Sunblock SPF 50+', 'workbook', 'local',
       NULL, 'Local product ', 2),
      (500, 'Simple Face Wash Refreshing Gel 150ml (uk)', 'Simple', '150ml',
       425, 749, 'Simple Face Wash Refreshing Gel 150ml (uk)', 'official', 'imported',
       'Skincare', 'imported Skincare', 2);

    INSERT INTO marketplace_listings
      (row_id, channel_name, price, url, matched_title, seller, confidence, available, verified)
    VALUES
      (2, 'Official Store', 1402, 'https://example.com/local', 'Bio-Screen', 'Bio-Xin', 100, 1, 1),
      (500, 'Shajgoj', 749, 'https://example.com/imported', 'Simple Face Wash', 'Shajgoj', 100, 1, 1);

    INSERT INTO price_edits
      (product_row_id, field, old_value, new_value, workbook_value, edited_at, folded)
    VALUES
      (2, 'source_cost', 1237.5, 1300, 1237.5, '2026-09-07T10:00:00.000Z', 1);
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
    async batch(statements: Array<{ all: () => Promise<unknown> }>) {
      const out = []
      for (const statement of statements) out.push(await statement.all())
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

function openpyxlProbe(path: string): Record<string, unknown> {
  const code = String.raw`
import json, openpyxl, sys
wb = openpyxl.load_workbook(sys.argv[1], data_only=False)
out = {'sheets': wb.sheetnames}
for name in wb.sheetnames:
    ws = wb[name]
    headers = {cell.value: cell.column for cell in ws[1]}
    row = 2
    out[name] = {
      'rows': ws.max_row,
      'cols': ws.max_column,
      'product': ws.cell(row, headers['Product']).value,
      'source_cost': ws.cell(row, headers['Source Cost']).value,
      'source_cost_type': ws.cell(row, headers['Source Cost']).data_type,
      'mrp': ws.cell(row, headers['MRP']).value,
      'selling': ws.cell(row, headers['Selling Price']).value,
      'workbook_cost': ws.cell(row, headers['Workbook Source Cost']).value,
      'edited': ws.cell(row, headers['Edited?']).value,
      'source_sheet': ws.cell(row, headers['Source Sheet']).value,
      'source_row': ws.cell(row, headers['Source Row']).value,
      'official': ws.cell(row, headers['Official Store']).value,
      'shajgoj': ws.cell(row, headers['Shajgoj']).value,
      'frozen': ws.freeze_panes,
    }
print(json.dumps(out))
`
  const result = Bun.spawnSync([
    'uv', 'run', '--with', 'openpyxl', 'python3', '-c', code, path,
  ], { stdout: 'pipe', stderr: 'pipe' })
  if (result.exitCode !== 0) throw new Error(result.stderr.toString())
  return JSON.parse(result.stdout.toString())
}

describe('GET /api/export.xlsx', () => {
  test('is admin-only', async () => {
    const env = envWith(sqliteD1())
    const response = await app.request('https://matrix.example/api/export.xlsx', {
      headers: { Origin: 'https://matrix.example', 'X-Price-Matrix-Admin': '1' },
    }, env)
    expect(response.status).toBe(401)
  })

  test('requires the same-origin admin header even with a valid session', async () => {
    const env = envWith(sqliteD1())
    const cookie = await loginCookie(env)
    const response = await app.request('https://matrix.example/api/export.xlsx', {
      headers: { Origin: 'https://matrix.example', Cookie: cookie },
    }, env)
    expect(response.status).toBe(403)
  })

  test('downloads one valid workbook with Local and Imported sheets', async () => {
    const env = envWith(sqliteD1())
    const cookie = await loginCookie(env)
    const response = await app.request('https://matrix.example/api/export.xlsx', {
      headers: {
        Origin: 'https://matrix.example',
        'X-Price-Matrix-Admin': '1',
        Cookie: cookie,
      },
    }, env)

    expect(response.status).toBe(200)
    expect(response.headers.get('Content-Type')).toContain('spreadsheetml.sheet')
    expect(response.headers.get('Content-Disposition')).toMatch(/product-price-matrix-\d{4}-\d{2}-\d{2}\.xlsx/)
    expect(response.headers.get('Cache-Control')).toBe('private, no-store')

    await Bun.write(OUTPUT, await response.arrayBuffer())
    const probe = openpyxlProbe(OUTPUT) as any

    expect(probe.sheets).toEqual(['Local', 'Imported'])
    expect(probe.Local.rows).toBe(2)
    expect(probe.Imported.rows).toBe(2)
    expect(probe.Local.frozen).toBe('A2')
  })

  test('exports current static prices, workbook baselines, provenance and channels', async () => {
    const env = envWith(sqliteD1())
    const cookie = await loginCookie(env)
    const response = await app.request('https://matrix.example/api/export.xlsx', {
      headers: {
        Origin: 'https://matrix.example',
        'X-Price-Matrix-Admin': '1',
        Cookie: cookie,
      },
    }, env)
    await Bun.write(OUTPUT, await response.arrayBuffer())
    const probe = openpyxlProbe(OUTPUT) as any

    // Current hard-overwritten value vs the journal's immutable workbook baseline.
    expect(probe.Local.source_cost).toBe(1300)
    expect(probe.Local.source_cost_type).toBe('n')
    expect(probe.Local.workbook_cost).toBe(1237.5)
    expect(probe.Local.edited).toBe('Yes')
    expect(probe.Local.source_sheet).toBe('Local product ')
    expect(probe.Local.source_row).toBe(2)
    expect(probe.Local.official).toBe(1402)
    expect(probe.Local.shajgoj).toBeNull()

    expect(probe.Imported.source_cost).toBe(425)
    expect(probe.Imported.mrp).toBe(749)
    expect(probe.Imported.official).toBeNull()
    expect(probe.Imported.shajgoj).toBe(749)
    expect(probe.Imported.source_sheet).toBe('imported Skincare')
  })

  test('selling price matches the shipped pricing engine', async () => {
    const env = envWith(sqliteD1())
    const cookie = await loginCookie(env)
    const response = await app.request('https://matrix.example/api/export.xlsx', {
      headers: {
        Origin: 'https://matrix.example',
        'X-Price-Matrix-Admin': '1',
        Cookie: cookie,
      },
    }, env)
    await Bun.write(OUTPUT, await response.arrayBuffer())
    const probe = openpyxlProbe(OUTPUT) as any

    // Cost 1300 + packaging 45 + CAC 5% of cost (65) = 1410, rounded by
    // calculateSellingPrice exactly as the UI does.
    expect(probe.Local.selling).toBe(1410)
  })
})
