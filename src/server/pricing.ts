import { z } from 'zod'
import type { PricingParams } from '../types'

export const PRICING_DEFAULTS: Readonly<PricingParams> = Object.freeze({
  packaging: 20,
  transport: 0,
  delivery: 60,
  cac: 0,
  targetMarginPct: 0,
  discountType: 'pct',
  discountVal: 0,
})

export const pricingSchema = z.object({
  packaging: z.coerce.number().finite().min(0).max(100_000),
  transport: z.coerce.number().finite().min(0).max(100_000),
  delivery: z.coerce.number().finite().min(0).max(100_000),
  cac: z.coerce.number().finite().min(0).max(100_000),
  targetMarginPct: z.coerce.number().finite().min(0).max(99.99),
  discountType: z.enum(['pct', 'amt']),
  discountVal: z.coerce.number().finite().min(0).max(1_000_000),
}).superRefine((value, context) => {
  if (value.discountType === 'pct' && value.discountVal > 100) {
    context.addIssue({ code: 'custom', path: ['discountVal'], message: 'Percentage discount cannot exceed 100' })
  }
})

export const productRowIdSchema = z.coerce.number().int().positive()

export function calculateSellingPrice(manufacturedPrice: number, params: PricingParams): number | null {
  if (!Number.isFinite(manufacturedPrice) || manufacturedPrice <= 0) return null
  const totalCost = manufacturedPrice + params.packaging + params.transport + params.delivery + params.cac
  const listPrice = totalCost / (1 - params.targetMarginPct / 100)
  const discounted = params.discountType === 'pct'
    ? listPrice * (1 - params.discountVal / 100)
    : listPrice - params.discountVal
  return Math.round(Math.max(0, discounted))
}
