# Rendering audits

These check the **rendered page** against the API, which the unit tests cannot
do. Each script recomputes every figure the browser painted — using an
independent implementation of the formulas in `src/shared/pricing.ts` — and
diffs it against what is actually in the DOM.

They found three real accessibility defects (inline counts announcing as
`"Local407"`, `"Imported189"`, `"Show51above market"`) that every other check
passed straight over.

## Running

```bash
bun run dev              # one shell
bun tests/audit/run.mjs  # another
```

Point at a deployed build with `AUDIT_BASE=https://… bun tests/audit/run.mjs`.
Exit code is 0 when every audit is clean, 1 on a finding, 2 if no server is up.

| Audit | Checks |
| --- | --- |
| `counts.mjs` | SKU/listing totals, per-channel counts, above-market count, rendered row count — both books |
| `figures.mjs` | Every row × column and every channel cell: selling price, both chip modes, tier bands, above-market override |
| `record.mjs` | Product record: cost-stack segments sum to the price, spread-rail geometry, identity strip, channel audit |
| `behaviour.mjs` | Search, filters, column auto-hiding, all sorts, `aria-sort`, the out-of-spec filter, empty state, copy |
| `a11y.mjs` | Computed accessible names, contrast on the smallest type, focus visibility |

## Two traps

**Chips derive from the rounded price.** `calculateSellingPrice` returns a whole
number and every percentage is computed from *that* against the unrounded source
cost. A SKU costing ৳93.6 displays `BDT 94` but its chips read against 93.6.
Recomputing from the displayed cost produces ~50 false positives.

**The API returns `""`, not `null`, for a sizeless SKU.** 22 local SKUs have no
pack size; the page correctly renders no size line. Comparing against `null`
reports 22 phantom failures.

Both cost a full debugging pass the first time. The scripts handle them; a new
audit written from scratch will not.
