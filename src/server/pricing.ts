import { z } from 'zod'
import { PRICING_DEFAULTS } from '../shared/pricing'
import type { PricingParams, StoredPricingOverride } from '../types'

/**
 * Request validation for the pricing endpoints. Kept separate from
 * `shared/pricing.ts` so the browser bundle never pulls zod in; the worker
 * re-exports the shared domain helpers for convenience.
 */

export { PRICING_DEFAULTS }
export {
  calculateSellingPrice,
  isEmptyOverride,
  overriddenFields,
  resolveCac,
  resolvePricingParams,
  sparsifyOverride,
  totalOverhead,
} from '../shared/pricing'

interface GlobalPricingRow {
  packaging: number
  transport: number
  delivery: number
  cac: number
  cacType: 'amt' | 'pct'
  targetMarginPct: number
  discountType: 'pct' | 'amt'
  discountVal: number
}

interface StoredOverrideRow {
  productRowId: number
  packaging: number | null
  transport: number | null
  delivery: number | null
  cac: number | null
  cacType: 'amt' | 'pct' | null
  targetMarginPct: number | null
  discountType: 'pct' | 'amt' | null
  discountVal: number | null
  updatedAt: string | null
}

/** One authoritative D1 read path for the UI API and the XLSX export. */
export async function readPricingState(db: D1Database): Promise<{
  globalParams: PricingParams
  overrides: Record<string, StoredPricingOverride>
}> {
  const [globalResult, overridesResult] = await db.batch([
    db.prepare(`SELECT packaging, transport, delivery, cac, cac_type AS cacType,
      target_margin_pct AS targetMarginPct, discount_type AS discountType,
      discount_val AS discountVal FROM global_pricing_params WHERE id = 1`),
    db.prepare(`SELECT product_row_id AS productRowId, packaging, transport, delivery, cac,
      cac_type AS cacType, target_margin_pct AS targetMarginPct, discount_type AS discountType,
      discount_val AS discountVal, updated_at AS updatedAt FROM product_pricing_overrides
      WHERE product_row_id IS NOT NULL`),
  ])
  const globalRow = globalResult?.results[0] as unknown as GlobalPricingRow | undefined
  const overrides: Record<string, StoredPricingOverride> = {}
  const rows = (overridesResult?.results ?? []) as unknown as StoredOverrideRow[]
  for (const row of rows) {
    const override: StoredPricingOverride = { updatedAt: row.updatedAt }
    if (row.packaging !== null) override.packaging = row.packaging
    if (row.transport !== null) override.transport = row.transport
    if (row.delivery !== null) override.delivery = row.delivery
    if (row.targetMarginPct !== null) override.targetMarginPct = row.targetMarginPct
    if (row.cac !== null && row.cacType !== null) {
      override.cac = row.cac
      override.cacType = row.cacType
    }
    if (row.discountType !== null && row.discountVal !== null) {
      override.discountType = row.discountType
      override.discountVal = row.discountVal
    }
    overrides[String(row.productRowId)] = override
  }
  return { globalParams: globalRow ?? { ...PRICING_DEFAULTS }, overrides }
}

/**
 * JSON bodies carry real JSON types, so a numeric field must already BE a
 * number. `z.coerce.number()` here accepted anything `Number()` swallows and
 * wrote the result as a price: `null` and `[]` both became 0, `true` became 1,
 * and the endpoint answered 200. A fabricated 0 is the damaging case — it is a
 * legal price that passes every CHECK, so it lands in `products`, journals an
 * edit, and then reads back as an unpriceable SKU (`calculateSellingPrice`
 * returns null at cost <= 0, and every markup chip blanks).
 *
 * Coercion belongs only on query strings, which arrive as text by definition.
 */
const costField = z.number().finite().min(0).max(100_000)
const marginField = z.number().finite().min(0).max(99.99)
const discountValField = z.number().finite().min(0).max(1_000_000)

export const pricingSchema = z.object({
  packaging: costField,
  transport: costField,
  delivery: costField,
  cac: costField,
  cacType: z.enum(['amt', 'pct']),
  targetMarginPct: marginField,
  discountType: z.enum(['pct', 'amt']),
  discountVal: discountValField,
}).superRefine((value, context) => {
  if (value.discountType === 'pct' && value.discountVal > 100) {
    context.addIssue({ code: 'custom', path: ['discountVal'], message: 'Percentage discount cannot exceed 100' })
  }
  if (value.cacType === 'pct' && value.cac > 100) {
    context.addIssue({ code: 'custom', path: ['cac'], message: 'Percentage CAC cannot exceed 100' })
  }
})

/**
 * A sparse tune. Omitted (or explicitly null) fields inherit the global engine,
 * which is what keeps a tuned SKU tracking later global cost changes.
 *
 * `null` is accepted alongside `undefined` so the client can clear one pinned
 * field without having to resend the whole override.
 */
const optional = <T extends z.ZodType>(schema: T) =>
  schema.nullish().transform((value) => (value === null ? undefined : value))

export const pricingOverrideSchema = z.object({
  packaging: optional(costField),
  transport: optional(costField),
  delivery: optional(costField),
  cac: optional(costField),
  cacType: optional(z.enum(['amt', 'pct'])),
  targetMarginPct: optional(marginField),
  discountType: optional(z.enum(['pct', 'amt'])),
  discountVal: optional(discountValField),
}).superRefine((value, context) => {
  const hasType = value.discountType !== undefined
  const hasVal = value.discountVal !== undefined
  if (hasType !== hasVal) {
    context.addIssue({
      code: 'custom',
      path: [hasType ? 'discountVal' : 'discountType'],
      message: 'Pin discount type and value together, or neither',
    })
  }
  const hasCacType = value.cacType !== undefined
  const hasCacVal = value.cac !== undefined
  if (hasCacType !== hasCacVal) {
    context.addIssue({
      code: 'custom',
      path: [hasCacType ? 'cac' : 'cacType'],
      message: 'Pin CAC type and value together, or neither',
    })
  }
  if (value.cacType === 'pct' && value.cac !== undefined && value.cac > 100) {
    context.addIssue({ code: 'custom', path: ['cac'], message: 'Percentage CAC cannot exceed 100' })
  }
  if (value.discountType === 'pct' && value.discountVal !== undefined && value.discountVal > 100) {
    context.addIssue({ code: 'custom', path: ['discountVal'], message: 'Percentage discount cannot exceed 100' })
  }
})

/**
 * Row ids arrive two ways, and each needs its own reading.
 *
 * In a JSON body the id must already be a number — coercing there let `null`
 * and `[]` become 0 and `true` become 1, which then failed the `positive()`
 * check for the wrong reason or, on other fields, wrote silently.
 *
 * In a query string every value is text, so `?productRowId=2` can only ever be
 * the string "2" and coercion is the correct reading.
 */
export const productRowIdSchema = z.number().int().positive()
export const productRowIdParamSchema = z.coerce.number().int().positive()
