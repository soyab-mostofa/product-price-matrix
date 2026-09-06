import { z } from 'zod'

/**
 * Request validation for the pricing endpoints. Kept separate from
 * `shared/pricing.ts` so the browser bundle never pulls zod in; the worker
 * re-exports the shared domain helpers for convenience.
 */

export {
  PRICING_DEFAULTS,
  calculateSellingPrice,
  isEmptyOverride,
  overriddenFields,
  resolveCac,
  resolvePricingParams,
  sparsifyOverride,
  totalOverhead,
} from '../shared/pricing'

const costField = z.coerce.number().finite().min(0).max(100_000)
const marginField = z.coerce.number().finite().min(0).max(99.99)
const discountValField = z.coerce.number().finite().min(0).max(1_000_000)

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

export const productRowIdSchema = z.coerce.number().int().positive()
