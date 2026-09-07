import { afterEach, describe, expect, test } from 'bun:test'
import { unlinkSync } from 'node:fs'
import { buildXlsx, type XlsxSheet } from '../src/server/xlsx'

const OUTPUT = '/tmp/product-price-matrix-xlsx-writer-test.xlsx'

afterEach(() => {
  try { unlinkSync(OUTPUT) } catch { /* already absent */ }
})

const sheets: XlsxSheet[] = [
  {
    name: 'Local',
    widths: [8, 38, 18, 16, 16, 14],
    rows: [
      [
        { value: 'Row ID', style: 'header' },
        { value: 'Product', style: 'header' },
        { value: 'Source Cost', style: 'header' },
        { value: 'MRP', style: 'header' },
        { value: 'Markup %', style: 'header' },
        { value: 'Edited?', style: 'header' },
      ],
      [
        { value: 2, style: 'integer' },
        { value: 'Bio-Screen Powder Sunblock SPF 50+ & “special”', style: 'text' },
        { value: 1237.5, style: 'money' },
        { value: 1650, style: 'money' },
        { value: (1650 - 1237.5) / 1237.5, style: 'percent' },
        { value: false, style: 'text' },
      ],
    ],
  },
  {
    name: 'Imported',
    widths: [8, 42, 16],
    rows: [
      [
        { value: 'Row ID', style: 'header' },
        { value: 'Product', style: 'header' },
        { value: 'Source Cost', style: 'header' },
      ],
      [
        { value: 500, style: 'integer' },
        { value: 'Simple Face Wash Refreshing Gel 150ml (uk)', style: 'text' },
        { value: 425, style: 'money' },
      ],
    ],
  },
]

function openpyxlProbe(path: string): { exitCode: number; stdout: string; stderr: string } {
  const code = String.raw`
import json, openpyxl, sys
wb = openpyxl.load_workbook(sys.argv[1], data_only=False)
local = wb['Local']
imported = wb['Imported']
print(json.dumps({
  'sheets': wb.sheetnames,
  'local_rows': local.max_row,
  'imported_rows': imported.max_row,
  'product': local['B2'].value,
  'cost': local['C2'].value,
  'cost_type': local['C2'].data_type,
  'mrp': local['D2'].value,
  'markup': local['E2'].value,
  'cost_format': local['C2'].number_format,
  'markup_format': local['E2'].number_format,
  'font': local['A1'].font.name,
  'header_bold': local['A1'].font.bold,
  'frozen': local.freeze_panes,
  'filter': local.auto_filter.ref,
}))
`
  const result = Bun.spawnSync([
    'uv', 'run', '--with', 'openpyxl', 'python3', '-c', code, path,
  ], { stdout: 'pipe', stderr: 'pipe' })
  return {
    exitCode: result.exitCode,
    stdout: result.stdout.toString(),
    stderr: result.stderr.toString(),
  }
}

describe('zero-dependency XLSX writer', () => {
  test('emits a ZIP/OOXML workbook with Local and Imported sheets', async () => {
    const bytes = buildXlsx(sheets)
    expect(bytes[0]).toBe(0x50) // P
    expect(bytes[1]).toBe(0x4b) // K
    expect(bytes.length).toBeGreaterThan(1000)

    await Bun.write(OUTPUT, bytes)
    const probe = openpyxlProbe(OUTPUT)
    expect(probe.exitCode).toBe(0)
    const data = JSON.parse(probe.stdout)

    expect(data.sheets).toEqual(['Local', 'Imported'])
    expect(data.local_rows).toBe(2)
    expect(data.imported_rows).toBe(2)
  })

  test('writes prices and percentages as real numeric cells', async () => {
    await Bun.write(OUTPUT, buildXlsx(sheets))
    const probe = openpyxlProbe(OUTPUT)
    expect(probe.exitCode).toBe(0)
    const data = JSON.parse(probe.stdout)

    expect(data.cost).toBe(1237.5)
    expect(data.mrp).toBe(1650)
    expect(data.cost_type).toBe('n')
    expect(data.markup).toBeCloseTo(1 / 3, 10)
    expect(data.cost_format).toContain('৳')
    expect(data.markup_format).toBe('0.00%')
  })

  test('escapes XML-sensitive product names without corrupting text', async () => {
    await Bun.write(OUTPUT, buildXlsx(sheets))
    const probe = openpyxlProbe(OUTPUT)
    expect(probe.exitCode).toBe(0)
    const data = JSON.parse(probe.stdout)
    expect(data.product).toBe('Bio-Screen Powder Sunblock SPF 50+ & “special”')
  })

  test('uses Arial, a bold header, frozen row 1, and an autofilter', async () => {
    await Bun.write(OUTPUT, buildXlsx(sheets))
    const probe = openpyxlProbe(OUTPUT)
    expect(probe.exitCode).toBe(0)
    const data = JSON.parse(probe.stdout)

    expect(data.font).toBe('Arial')
    expect(data.header_bold).toBe(true)
    expect(data.frozen).toBe('A2')
    expect(data.filter).toBe('A1:F2')
  })

  test('rejects an empty workbook', () => {
    expect(() => buildXlsx([])).toThrow('at least one sheet')
  })

  test('sanitises illegal and duplicate sheet names', async () => {
    const bytes = buildXlsx([
      { name: 'Bad/Name:*?', rows: [[{ value: 'A', style: 'header' }]] },
      { name: 'Bad/Name:*?', rows: [[{ value: 'B', style: 'header' }]] },
    ])
    await Bun.write(OUTPUT, bytes)
    const code = "import openpyxl,sys,json; print(json.dumps(openpyxl.load_workbook(sys.argv[1]).sheetnames))"
    const result = Bun.spawnSync([
      'uv', 'run', '--with', 'openpyxl', 'python3', '-c', code, OUTPUT,
    ], { stdout: 'pipe', stderr: 'pipe' })
    expect(result.exitCode).toBe(0)
    expect(JSON.parse(result.stdout.toString())).toEqual(['Bad Name', 'Bad Name 2'])
  })
})
