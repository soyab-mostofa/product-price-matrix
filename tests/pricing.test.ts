import { describe, expect, test } from 'bun:test'
import {
  PRICING_DEFAULTS,
  calculateSellingPrice,
  isEmptyOverride,
  overriddenFields,
  pricingOverrideSchema,
  pricingSchema,
  productRowIdParamSchema,
  productRowIdSchema,
  resolveCac,
  resolvePricingParams,
  sparsifyOverride,
  totalOverhead,
} from '../src/server/pricing'
import type { PricingParams } from '../src/types'

const defaults = {
  packaging: 45,
  transport: 0,
  delivery: 0,
  cac: 40,
  cacType: 'amt' as const,
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

  test('a JSON body must carry real numbers, not coercible junk', () => {
    // z.coerce.number() accepted anything Number() swallows, so a malformed
    // payload wrote a fabricated figure and answered 200: null and [] became 0,
    // true became 1. Zero is the dangerous one — a legal price that leaves the
    // SKU unpriceable rather than erroring.
    for (const junk of [null, true, false, [], '45', '', 'abc']) {
      expect(pricingSchema.safeParse({ ...defaults, packaging: junk }).success).toBe(false)
      expect(pricingOverrideSchema.safeParse({ packaging: junk, ...(junk === null ? { targetMarginPct: 1 } : {}) }).success)
        .toBe(junk === null) // explicit null is the documented "unpin", not a value
    }
  })

  test('requires immutable positive product row IDs', () => {
    // A JSON body must state the id as a number; a query string cannot, so the
    // param variant is the one that coerces.
    expect(productRowIdParamSchema.parse('42')).toBe(42)
    expect(productRowIdSchema.parse(42)).toBe(42)
    expect(productRowIdSchema.safeParse('42').success).toBe(false)
    expect(productRowIdSchema.safeParse(null).success).toBe(false)
    expect(productRowIdSchema.safeParse(true).success).toBe(false)
    expect(productRowIdParamSchema.safeParse('Product Name').success).toBe(false)
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
    // CAC pins as a pair now, so the mode travels with the value.
    const parsed = pricingOverrideSchema.parse({ packaging: null, cacType: 'amt', cac: 40 })
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

  test('shipped defaults charge CAC as 5% of the sourcing price', () => {
    expect(PRICING_DEFAULTS).toEqual({
      packaging: 45,
      transport: 0,
      delivery: 0,
      cac: 5,
      cacType: 'pct',
      targetMarginPct: 0,
      discountType: 'pct',
      discountVal: 0,
    })
  })
})

describe('CAC as a percentage of the sourcing price', () => {
  const pctCac: PricingParams = { ...defaults, cacType: 'pct', cac: 5 }

  test('a flat CAC is the same figure whatever the SKU costs', () => {
    expect(resolveCac(100, defaults)).toBe(40)
    expect(resolveCac(5000, defaults)).toBe(40)
  })

  test('a percentage CAC scales with the sourcing price', () => {
    expect(resolveCac(100, pctCac)).toBe(5)
    expect(resolveCac(5000, pctCac)).toBe(250)
  })

  test('overhead folds the resolved CAC in with the flat costs', () => {
    // packaging 45 + transport 0 + delivery 0 + 5% of 200
    expect(totalOverhead(200, pctCac)).toBe(55)
    expect(totalOverhead(200, defaults)).toBe(85)
  })

  test('the selling price tracks the sourcing price under a percentage CAC', () => {
    // (100 + 45 + 5) — the cheap SKU is no longer carrying a flat 40 BDT.
    expect(calculateSellingPrice(100, pctCac)).toBe(150)
    // (5000 + 45 + 250) — the expensive SKU now carries proportionate CAC.
    expect(calculateSellingPrice(5000, pctCac)).toBe(5295)
  })

  test('percentage CAC still composes with margin and discount', () => {
    expect(calculateSellingPrice(100, { ...pctCac, targetMarginPct: 50 })).toBe(300)
    expect(calculateSellingPrice(100, { ...pctCac, discountType: 'amt', discountVal: 50 })).toBe(100)
  })
})

describe('CAC mode validation', () => {
  test('the global engine requires a CAC mode', () => {
    const { cacType: _omitted, ...withoutMode } = defaults
    expect(pricingSchema.safeParse(withoutMode).success).toBe(false)
    expect(pricingSchema.safeParse({ ...defaults, cacType: 'bogus' }).success).toBe(false)
  })

  test('a percentage CAC cannot exceed 100', () => {
    expect(pricingSchema.safeParse({ ...defaults, cacType: 'pct', cac: 101 }).success).toBe(false)
    expect(pricingSchema.safeParse({ ...defaults, cacType: 'pct', cac: 100 }).success).toBe(true)
    expect(pricingSchema.safeParse({ ...defaults, cacType: 'amt', cac: 101 }).success).toBe(true)
  })

  test('rejects half a CAC pair', () => {
    expect(pricingOverrideSchema.safeParse({ cacType: 'pct' }).success).toBe(false)
    expect(pricingOverrideSchema.safeParse({ cac: 40 }).success).toBe(false)
    expect(pricingOverrideSchema.safeParse({ cacType: 'amt', cac: 40 }).success).toBe(true)
  })

  test('enforces the percentage range on a tune too', () => {
    expect(pricingOverrideSchema.safeParse({ cacType: 'pct', cac: 101 }).success).toBe(false)
    expect(pricingOverrideSchema.safeParse({ cacType: 'pct', cac: 12.5 }).success).toBe(true)
  })
})

describe('CAC override semantics', () => {
  test('CAC resolves as a pair, never half-inherited', () => {
    const globalParams: PricingParams = { ...defaults, cacType: 'pct', cac: 5 }
    const resolved = resolvePricingParams(globalParams, { cacType: 'amt', cac: 80 })
    expect(resolved.cacType).toBe('amt')
    expect(resolved.cac).toBe(80)

    const inherited = resolvePricingParams(globalParams, { targetMarginPct: 30 })
    expect(inherited.cacType).toBe('pct')
    expect(inherited.cac).toBe(5)
  })

  test('a SKU pinned to flat CAC ignores a global switch to percentage', () => {
    const override = { cacType: 'amt' as const, cac: 40 }
    const globalGoesPercentage: PricingParams = { ...defaults, cacType: 'pct', cac: 5 }
    expect(calculateSellingPrice(1000, resolvePricingParams(globalGoesPercentage, override))).toBe(1085)
  })

  test('an un-pinned CAC follows the global switch to percentage', () => {
    const override = { targetMarginPct: 0 }
    const globalGoesPercentage: PricingParams = { ...defaults, cacType: 'pct', cac: 5 }
    expect(calculateSellingPrice(1000, resolvePricingParams(globalGoesPercentage, override))).toBe(1095)
  })

  test('drops a CAC pair that merely echoes the global engine', () => {
    const globalParams: PricingParams = { ...defaults, cacType: 'pct', cac: 5 }
    expect(sparsifyOverride(globalParams, { cacType: 'pct', cac: 5 })).toEqual({})
  })

  test('keeps a CAC pair when either half differs from global', () => {
    const globalParams: PricingParams = { ...defaults, cacType: 'pct', cac: 5 }
    expect(sparsifyOverride(globalParams, { cacType: 'amt', cac: 5 }))
      .toEqual({ cacType: 'amt', cac: 5 })
    expect(sparsifyOverride(globalParams, { cacType: 'pct', cac: 12 }))
      .toEqual({ cacType: 'pct', cac: 12 })
  })

  test('reports a CAC tune once, in UI order', () => {
    expect(overriddenFields({ cacType: 'pct', cac: 12, packaging: 25 }))
      .toEqual(['packaging', 'cac', 'cacType'])
  })
})
