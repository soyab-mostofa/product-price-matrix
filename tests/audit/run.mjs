#!/usr/bin/env bun
/**
 * Runs every audit in this directory against a live dev server and reports a
 * single pass/fail. Each audit recomputes what the browser painted from the
 * raw API and diffs the two, so a rendering bug fails here even when the unit
 * tests pass.
 *
 *   bun run dev                  # in one shell
 *   bun tests/audit/run.mjs      # in another
 */
import { spawn } from 'node:child_process'
import { readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const BASE = process.env.AUDIT_BASE ?? 'http://localhost:5173'

try {
  const res = await fetch(BASE, { signal: AbortSignal.timeout(4000) })
  if (!res.ok) throw new Error(`status ${res.status}`)
} catch (err) {
  console.error(`No dev server at ${BASE} — start one with \`bun run dev\`.`)
  console.error(`  ${err.message}`)
  process.exit(2)
}

const audits = readdirSync(here).filter((f) => f.endsWith('.mjs') && f !== 'run.mjs').sort()
let failed = 0

for (const file of audits) {
  const out = await new Promise((resolve) => {
    const p = spawn('bun', [join(here, file)], { encoding: 'utf8' })
    let buf = ''
    p.stdout.on('data', (d) => (buf += d))
    p.stderr.on('data', (d) => (buf += d))
    p.on('close', (code) => resolve({ code, buf }))
  })

  // Each audit prints a "=== PROBLEMS ===" block; "none" means clean.
  const block = out.buf.split('=== PROBLEMS ===')[1] ?? ''
  const clean = out.code === 0 && /^\s*none/m.test(block)
  console.log(`${clean ? 'PASS' : 'FAIL'}  ${file}`)
  if (!clean) {
    failed++
    console.log(block.trim().split('\n').slice(0, 12).map((l) => `      ${l}`).join('\n'))
  }
}

console.log(`\n${audits.length - failed}/${audits.length} audits clean`)
process.exit(failed ? 1 : 0)
