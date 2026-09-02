import { describe, expect, test } from 'bun:test'
import { pricingSchema, productRowIdSchema } from '../src/server/pricing'

const defaults = {
  packaging: 20,
  transport: 0,
  delivery: 60,
  cac: 0,
  targetMarginPct: 0,
  discountType: 'pct' as const,
  discountVal: 0,
}

describe('pricing input validation', () => {
  test('rejects invalid ranges and modes', () => {
    expect(pricingSchema.safeParse({ ...defaults, discountVal: 101 }).success).toBe(false)
    expect(pricingSchema.safeParse({ ...defaults, packaging: -1 }).success).toBe(false)
    expect(pricingSchema.safeParse({ ...defaults, targetMarginPct: 100 }).success).toBe(false)
    expect(pricingSchema.safeParse({ ...defaults, discountType: 'bogus' }).success).toBe(false)
  })

  test('requires immutable positive product row IDs', () => {
    expect(productRowIdSchema.parse('42')).toBe(42)
    expect(productRowIdSchema.safeParse('Product Name').success).toBe(false)
    expect(productRowIdSchema.safeParse(0).success).toBe(false)
  })
})
