import { describe, expect, test } from 'bun:test'
import {
  PRICING_DEFAULTS,
  calculateSellingPrice,
  isEmptyOverride,
  overriddenFields,
  pricingOverrideSchema,
  pricingSchema,
  productRowIdSchema,
  resolvePricingParams,
  sparsifyOverride,
} from '../src/server/pricing'
import type { PricingParams } from '../src/types'

const defaults = {
  packaging: 45,
  transport: 0,
  delivery: 0,
  cac: 40,
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

describe('sparse override validation', () => {
  test('accepts a tune that pins a single field', () => {
    const parsed = pricingOverrideSchema.parse({ targetMarginPct: 30 })
    expect(parsed.targetMarginPct).toBe(30)
    expect(parsed.packaging).toBeUndefined()
  })

  test('accepts an empty tune (everything inherits global)', () => {
    expect(pricingOverrideSchema.safeParse({}).success).toBe(true)
  })

  test('treats explicit null as "unpin this field"', () => {
    const parsed = pricingOverrideSchema.parse({ packaging: null, cac: 40 })
    expect(parsed.packaging).toBeUndefined()
    expect(parsed.cac).toBe(40)
  })

  test('rejects half a discount pair', () => {
    expect(pricingOverrideSchema.safeParse({ discountType: 'amt' }).success).toBe(false)
    expect(pricingOverrideSchema.safeParse({ discountVal: 50 }).success).toBe(false)
    expect(pricingOverrideSchema.safeParse({ discountType: 'amt', discountVal: 50 }).success).toBe(true)
  })

  test('still enforces per-field ranges', () => {
    expect(pricingOverrideSchema.safeParse({ targetMarginPct: 100 }).success).toBe(false)
    expect(pricingOverrideSchema.safeParse({ packaging: -1 }).success).toBe(false)
    expect(pricingOverrideSchema.safeParse({ discountType: 'pct', discountVal: 101 }).success).toBe(false)
    expect(pricingOverrideSchema.safeParse({ discountType: 'amt', discountVal: 101 }).success).toBe(true)
  })
})

describe('override merge semantics', () => {
  test('an un-pinned field keeps tracking later global changes', () => {
    // The scenario that motivated sparse overrides: MFG 100, global overhead 85,
    // tuned to 30% margin. Raising global delivery must still reach this SKU.
    const override = { targetMarginPct: 30 }
    const before = calculateSellingPrice(100, resolvePricingParams(defaults, override))
    expect(before).toBe(264) // (100 + 85) / 0.7

    const globalAfterCourierHike: PricingParams = { ...defaults, delivery: 80 }
    const after = calculateSellingPrice(100, resolvePricingParams(globalAfterCourierHike, override))
    expect(after).toBe(379) // (100 + 165) / 0.7 — delivery change landed
  })

  test('a pinned field ignores the corresponding global change', () => {
    const override = { delivery: 60 }
    const globalAfterCourierHike: PricingParams = { ...defaults, delivery: 200 }
    const resolved = resolvePricingParams(globalAfterCourierHike, override)
    expect(resolved.delivery).toBe(60)
  })

  test('discount resolves as a pair, never half-inherited', () => {
    const globalParams: PricingParams = { ...defaults, discountType: 'pct', discountVal: 10 }
    const resolved = resolvePricingParams(globalParams, { discountType: 'amt', discountVal: 50 })
    expect(resolved.discountType).toBe('amt')
    expect(resolved.discountVal).toBe(50)

    const inherited = resolvePricingParams(globalParams, { targetMarginPct: 30 })
    expect(inherited.discountType).toBe('pct')
    expect(inherited.discountVal).toBe(10)
  })

  test('no override resolves to the global params unchanged', () => {
    expect(resolvePricingParams(defaults, undefined)).toEqual(defaults)
    expect(resolvePricingParams(defaults, null)).toEqual(defaults)
    expect(resolvePricingParams(defaults, {})).toEqual(defaults)
  })

  test('merging never mutates the caller and global params', () => {
    const globalParams: PricingParams = { ...defaults }
    resolvePricingParams(globalParams, { packaging: 999 })
    expect(globalParams.packaging).toBe(45)
  })
})

describe('override sparsification', () => {
  test('drops fields that merely echo the current global value', () => {
    const sparse = sparsifyOverride(defaults, {
      packaging: 45, // same as global — not a tune
      transport: 0, // same as global — not a tune
      delivery: 0, // same as global — not a tune
      cac: 40, // same as global — not a tune
      targetMarginPct: 30, // genuinely different
      discountType: 'pct',
      discountVal: 0, // same as global pair — not a tune
    })
    expect(sparse).toEqual({ targetMarginPct: 30 })
  })

  test('a fully-global tune sparsifies to nothing and should clear the row', () => {
    const sparse = sparsifyOverride(defaults, { ...defaults })
    expect(isEmptyOverride(sparse)).toBe(true)
  })

  test('keeps a discount pair when either half differs from global', () => {
    expect(sparsifyOverride(defaults, { discountType: 'amt', discountVal: 0 }))
      .toEqual({ discountType: 'amt', discountVal: 0 })
    expect(sparsifyOverride(defaults, { discountType: 'pct', discountVal: 15 }))
      .toEqual({ discountType: 'pct', discountVal: 15 })
  })

  test('reports pinned fields in UI order', () => {
    expect(overriddenFields({ targetMarginPct: 30, packaging: 25 }))
      .toEqual(['packaging', 'targetMarginPct'])
    expect(overriddenFields({})).toEqual([])
    expect(overriddenFields(undefined)).toEqual([])
  })
})

describe('selling price formula', () => {
  test('applies overhead, margin, and both discount modes', () => {
    expect(calculateSellingPrice(100, defaults)).toBe(185)
    expect(calculateSellingPrice(100, { ...defaults, targetMarginPct: 50 })).toBe(370)
    expect(calculateSellingPrice(100, { ...defaults, discountType: 'pct', discountVal: 10 })).toBe(167)
    expect(calculateSellingPrice(100, { ...defaults, discountType: 'amt', discountVal: 50 })).toBe(135)
  })

  test('never returns a negative price and rejects impossible inputs', () => {
    expect(calculateSellingPrice(100, { ...defaults, discountType: 'amt', discountVal: 100_000 })).toBe(0)
    expect(calculateSellingPrice(0, defaults)).toBeNull()
    expect(calculateSellingPrice(-5, defaults)).toBeNull()
    expect(calculateSellingPrice(100, { ...defaults, targetMarginPct: 100 })).toBeNull()
  })

  test('shipped defaults match the documented engine baseline', () => {
    expect(PRICING_DEFAULTS).toEqual(defaults)
  })
})
