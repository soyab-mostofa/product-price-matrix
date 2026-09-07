export type XlsxCellStyle = 'text' | 'header' | 'money' | 'percent' | 'integer' | 'datetime'

export interface XlsxCell {
  value: string | number | boolean | null | undefined
  style?: XlsxCellStyle
}

export interface XlsxSheet {
  name: string
  rows: XlsxCell[][]
  /** Approximate character widths, one per exported column. */
  widths?: number[]
  freezeHeader?: boolean
  autoFilter?: boolean
}

const encoder = new TextEncoder()

function xml(value: unknown): string {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')
}

function columnName(index: number): string {
  let n = index + 1
  let out = ''
  while (n > 0) {
    const remainder = (n - 1) % 26
    out = String.fromCharCode(65 + remainder) + out
    n = Math.floor((n - 1) / 26)
  }
  return out
}

function safeSheetName(name: string, fallback: string): string {
  const cleaned = name.replace(/[\\/?*\[\]:]/g, ' ').trim().slice(0, 31)
  return cleaned || fallback
}

const STYLE_INDEX: Record<XlsxCellStyle, number> = {
  text: 0,
  header: 1,
  money: 2,
  percent: 3,
  integer: 4,
  datetime: 5,
}

function cellXml(cell: XlsxCell, rowIndex: number, columnIndex: number): string {
  const ref = `${columnName(columnIndex)}${rowIndex + 1}`
  const value = cell.value
  const style = STYLE_INDEX[cell.style ?? 'text']

  if (value === null || value === undefined || value === '') {
    return `<c r="${ref}" s="${style}"/>`
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return `<c r="${ref}" s="${style}"/>`
    return `<c r="${ref}" s="${style}" t="n"><v>${value}</v></c>`
  }
  if (typeof value === 'boolean') {
    return `<c r="${ref}" s="${style}" t="b"><v>${value ? 1 : 0}</v></c>`
  }
  return `<c r="${ref}" s="${style}" t="inlineStr"><is><t xml:space="preserve">${xml(value)}</t></is></c>`
}

function sheetXml(sheet: XlsxSheet): string {
  const columnCount = Math.max(1, ...sheet.rows.map((row) => row.length))
  const rowCount = Math.max(1, sheet.rows.length)
  const dimension = `A1:${columnName(columnCount - 1)}${rowCount}`
  const widths = sheet.widths?.length
    ? `<cols>${sheet.widths.map((width, index) =>
        `<col min="${index + 1}" max="${index + 1}" width="${Math.max(4, Math.min(80, width))}" customWidth="1"/>`,
      ).join('')}</cols>`
    : ''
  const rows = sheet.rows.map((row, rowIndex) =>
    `<row r="${rowIndex + 1}">${row.map((cell, columnIndex) =>
      cellXml(cell, rowIndex, columnIndex),
    ).join('')}</row>`,
  ).join('')
  const freeze = sheet.freezeHeader === false
    ? ''
    : '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/><selection pane="bottomLeft" activeCell="A2" sqref="A2"/></sheetView></sheetViews>'
  const filter = sheet.autoFilter === false
    ? ''
    : `<autoFilter ref="A1:${columnName(columnCount - 1)}${rowCount}"/>`

  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<dimension ref="${dimension}"/>${freeze}${widths}<sheetData>${rows}</sheetData>${filter}
<pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>
</worksheet>`
}

function workbookXml(sheets: XlsxSheet[]): string {
  const names = new Set<string>()
  const entries = sheets.map((sheet, index) => {
    let name = safeSheetName(sheet.name, `Sheet ${index + 1}`)
    let suffix = 2
    const base = name.slice(0, 27)
    while (names.has(name)) name = `${base} ${suffix++}`.slice(0, 31)
    names.add(name)
    return `<sheet name="${xml(name)}" sheetId="${index + 1}" r:id="rId${index + 1}"/>`
  }).join('')
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<bookViews><workbookView xWindow="0" yWindow="0" windowWidth="24000" windowHeight="12000"/></bookViews>
<sheets>${entries}</sheets><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>`
}

function workbookRelsXml(sheetCount: number): string {
  const sheets = Array.from({ length: sheetCount }, (_, index) =>
    `<Relationship Id="rId${index + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${index + 1}.xml"/>`,
  ).join('')
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${sheets}
<Relationship Id="rId${sheetCount + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>`
}

function contentTypesXml(sheetCount: number): string {
  const sheets = Array.from({ length: sheetCount }, (_, index) =>
    `<Override PartName="/xl/worksheets/sheet${index + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`,
  ).join('')
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>${sheets}
</Types>`
}

const ROOT_RELS = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`

/** Arial throughout; green ruled header; real numeric money/percentage cells. */
const STYLES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="3"><numFmt numFmtId="164" formatCode="৳#,##0.00;[Red]-৳#,##0.00;৳-"/><numFmt numFmtId="165" formatCode="0.00%"/><numFmt numFmtId="166" formatCode="yyyy-mm-dd hh:mm"/></numFmts>
<fonts count="2"><font><sz val="10"/><name val="Arial"/><family val="2"/></font><font><b/><color rgb="FF0B4D39"/><sz val="10"/><name val="Arial"/><family val="2"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFD6E9DF"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left style="thin"><color rgb="FFDEDCD6"/></left><right style="thin"><color rgb="FFDEDCD6"/></right><top style="thin"><color rgb="FFDEDCD6"/></top><bottom style="thin"><color rgb="FFA9A89F"/></bottom><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="6">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="right" vertical="top"/></xf>
<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="right" vertical="top"/></xf>
<xf numFmtId="1" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="right" vertical="top"/></xf>
<xf numFmtId="166" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment vertical="top"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>`

// ── Stored ZIP writer (method 0; no compression dependency) ───────────────

const CRC_TABLE = (() => {
  const table = new Uint32Array(256)
  for (let n = 0; n < 256; n += 1) {
    let c = n
    for (let k = 0; k < 8; k += 1) c = (c & 1) ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    table[n] = c >>> 0
  }
  return table
})()

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff
  for (const byte of bytes) crc = CRC_TABLE[(crc ^ byte) & 0xff]! ^ (crc >>> 8)
  return (crc ^ 0xffffffff) >>> 0
}

function le16(value: number): Uint8Array {
  const out = new Uint8Array(2)
  new DataView(out.buffer).setUint16(0, value, true)
  return out
}

function le32(value: number): Uint8Array {
  const out = new Uint8Array(4)
  new DataView(out.buffer).setUint32(0, value >>> 0, true)
  return out
}

function concat(parts: Uint8Array[]): Uint8Array {
  const size = parts.reduce((total, part) => total + part.length, 0)
  const out = new Uint8Array(size)
  let offset = 0
  for (const part of parts) {
    out.set(part, offset)
    offset += part.length
  }
  return out
}

interface ZipEntry {
  name: string
  data: Uint8Array
  crc: number
  offset: number
}

function zip(files: Array<{ name: string; content: string }>): Uint8Array {
  const locals: Uint8Array[] = []
  const entries: ZipEntry[] = []
  let offset = 0

  // Fixed DOS timestamp: deterministic output and no timezone ambiguity.
  const dosTime = 0
  const dosDate = (1 << 5) | 1 // 1980-01-01

  for (const file of files) {
    const name = encoder.encode(file.name)
    const data = encoder.encode(file.content)
    const crc = crc32(data)
    const header = concat([
      le32(0x04034b50), le16(20), le16(0x0800), le16(0), le16(dosTime), le16(dosDate),
      le32(crc), le32(data.length), le32(data.length), le16(name.length), le16(0), name,
    ])
    entries.push({ name: file.name, data, crc, offset })
    locals.push(header, data)
    offset += header.length + data.length
  }

  const centralOffset = offset
  const central: Uint8Array[] = []
  for (const entry of entries) {
    const name = encoder.encode(entry.name)
    const record = concat([
      le32(0x02014b50), le16(20), le16(20), le16(0x0800), le16(0),
      le16(dosTime), le16(dosDate), le32(entry.crc), le32(entry.data.length),
      le32(entry.data.length), le16(name.length), le16(0), le16(0), le16(0),
      le16(0), le32(0), le32(entry.offset), name,
    ])
    central.push(record)
    offset += record.length
  }
  const centralSize = offset - centralOffset
  const end = concat([
    le32(0x06054b50), le16(0), le16(0), le16(entries.length), le16(entries.length),
    le32(centralSize), le32(centralOffset), le16(0),
  ])
  return concat([...locals, ...central, end])
}

/** Build an Excel-compatible .xlsx byte stream. */
export function buildXlsx(sheets: XlsxSheet[]): Uint8Array {
  if (sheets.length === 0) throw new Error('An XLSX workbook needs at least one sheet')
  if (sheets.length > 255) throw new Error('Too many sheets')

  const files: Array<{ name: string; content: string }> = [
    { name: '[Content_Types].xml', content: contentTypesXml(sheets.length) },
    { name: '_rels/.rels', content: ROOT_RELS },
    { name: 'xl/workbook.xml', content: workbookXml(sheets) },
    { name: 'xl/_rels/workbook.xml.rels', content: workbookRelsXml(sheets.length) },
    { name: 'xl/styles.xml', content: STYLES },
  ]
  sheets.forEach((sheet, index) => {
    files.push({ name: `xl/worksheets/sheet${index + 1}.xml`, content: sheetXml(sheet) })
  })
  return zip(files)
}
