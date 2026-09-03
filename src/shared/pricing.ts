import {
  PRICING_FIELDS,
  type PricingField,
  type PricingOverride,
  type PricingParams,
} from '../types'

/**
 * Pure pricing domain logic, shared verbatim by the Cloudflare worker and the
 * browser bundle. Deliberately dependency-free — the zod request schemas live
 * in `server/pricing.ts` so validation never reaches the client bundle.
 */

export const PRICING_DEFAULTS: Readonly<PricingParams> = Object.freeze({
  packaging: 45,
  transport: 0,
  delivery: 60,
  cac: 40,
  targetMarginPct: 0,
  discountType: 'pct',
  discountVal: 0,
})

/** Which fields this override actually pins, in UI order. */
export function overriddenFields(override: PricingOverride | undefined | null): PricingField[] {
  if (!override) return []
  return PRICING_FIELDS.filter((field) => override[field] !== undefined && override[field] !== null)
}

/** True when the override pins nothing — such a row should be deleted, not stored. */
export function isEmptyOverride(override: PricingOverride | undefined | null): boolean {
  return overriddenFields(override).length === 0
}

/**
 * Merge a sparse tune onto the live global parameters.
 *
 * Pinned fields win; everything else follows global, so a global cost change
 * still reaches tuned SKUs. Discount is treated as one unit: pinning a type
 * carries its value, and pinning neither inherits both from global.
 */
export function resolvePricingParams(
  globalParams: PricingParams,
  override?: PricingOverride | null,
): PricingParams {
  const resolved: PricingParams = { ...globalParams }
  if (!override) return resolved

  if (override.packaging !== undefined) resolved.packaging = override.packaging
  if (override.transport !== undefined) resolved.transport = override.transport
  if (override.delivery !== undefined) resolved.delivery = override.delivery
  if (override.cac !== undefined) resolved.cac = override.cac
  if (override.targetMarginPct !== undefined) resolved.targetMarginPct = override.targetMarginPct
  if (override.discountType !== undefined && override.discountVal !== undefined) {
    resolved.discountType = override.discountType
    resolved.discountVal = override.discountVal
  }
  return resolved
}

/**
 * Drop any field whose pinned value equals the current global value.
 *
 * Saving "the same as global" is not a tune — keeping it would silently freeze
 * that field against future global changes, which is exactly the behaviour this
 * sparse model exists to avoid.
 */
export function sparsifyOverride(
  globalParams: PricingParams,
  override: PricingOverride,
): PricingOverride {
  const sparse: PricingOverride = {}
  if (override.packaging !== undefined && override.packaging !== globalParams.packaging) sparse.packaging = override.packaging
  if (override.transport !== undefined && override.transport !== globalParams.transport) sparse.transport = override.transport
  if (override.delivery !== undefined && override.delivery !== globalParams.delivery) sparse.delivery = override.delivery
  if (override.cac !== undefined && override.cac !== globalParams.cac) sparse.cac = override.cac
  if (override.targetMarginPct !== undefined && override.targetMarginPct !== globalParams.targetMarginPct) {
    sparse.targetMarginPct = override.targetMarginPct
  }
  if (override.discountType !== undefined && override.discountVal !== undefined) {
    const matchesGlobal = override.discountType === globalParams.discountType
      && override.discountVal === globalParams.discountVal
    if (!matchesGlobal) {
      sparse.discountType = override.discountType
      sparse.discountVal = override.discountVal
    }
  }
  return sparse
}

/**
 * Recommended selling price for one SKU.
 *
 *   list  = (MFG + packaging + transport + delivery + CAC) / (1 - margin)
 *   final = list * (1 - discount%)   |   list - discountBDT
 */
export function calculateSellingPrice(manufacturedPrice: number, params: PricingParams): number | null {
  if (!Number.isFinite(manufacturedPrice) || manufacturedPrice <= 0) return null

  const overhead = params.packaging + params.transport + params.delivery + params.cac
  const marginRate = params.targetMarginPct / 100
  if (!Number.isFinite(overhead) || marginRate < 0 || marginRate >= 1) return null

  const listPrice = (manufacturedPrice + overhead) / (1 - marginRate)
  const discounted = params.discountType === 'pct'
    ? listPrice * (1 - params.discountVal / 100)
    : listPrice - params.discountVal
  if (!Number.isFinite(discounted)) return null

  return Math.round(Math.max(0, discounted))
}
