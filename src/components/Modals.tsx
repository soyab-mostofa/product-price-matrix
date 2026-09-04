import { CloseIcon } from './icons'

export function Modals() {
  return (
    <>
      <dialog id="authModal" aria-labelledby="authModalTitle">
        <div class="modal-header">
          <div class="modal-heading-group">
            <span class="modal-kicker">Restricted</span>
            <h2 class="modal-title" id="authModalTitle">Admin access</h2>
          </div>
          <button class="modal-btn-close" id="closeAuthModal" type="button" aria-label="Close admin modal"><CloseIcon /></button>
        </div>
        <form id="authForm" class="modal-body">
          <p class="text-sm text-muted">Enter the administrator password to unlock global pricing and SKU tuning controls.</p>
          <div class="engine-field">
            <label for="adminPassword">Password</label>
            <input id="adminPassword" type="password" class="engine-input" autocomplete="current-password" required />
          </div>
          <div id="authStatus" class="status-message" role="status" aria-live="polite"></div>
          <button class="btn-calc" type="submit" style="height:36px;">Unlock admin mode</button>
        </form>
      </dialog>

      <dialog id="engineModal" aria-labelledby="engineModalTitle">
        <div class="modal-header">
          <div class="modal-heading-group">
            <span class="modal-kicker">Applies to every SKU</span>
            <h2 class="modal-title" id="engineModalTitle">Pricing engine</h2>
          </div>
          <button class="modal-btn-close" id="closeEngineModal" type="button" aria-label="Close pricing engine modal"><CloseIcon /></button>
        </div>
        <form id="engineForm" class="modal-body">
          <div class="read-only-note" id="engineReadOnlyBanner" hidden></div>

          <div class="record-section">
            <div class="record-legend">Per-unit overhead</div>
            <div class="engine-grid">
              <div class="engine-field"><label for="inputPackaging">Packaging (BDT)</label><input id="inputPackaging" class="engine-input" type="number" min="0" max="100000" step="1" required /></div>
              <div class="engine-field"><label for="inputTransport">Transport (BDT)</label><input id="inputTransport" class="engine-input" type="number" min="0" max="100000" step="1" required /><span class="hint">Per unit. Leave 0 unless inbound freight is charged per item.</span></div>
              <div class="engine-field"><label for="inputDelivery">Delivery (BDT)</label><input id="inputDelivery" class="engine-input" type="number" min="0" max="100000" step="1" required /><span class="hint">Delivery is an order-level cost. Charging it per unit prices low-value SKUs above market — amortise it across expected units per order.</span></div>
              <div class="engine-field"><label for="inputCAC">CAC (BDT)</label><input id="inputCAC" class="engine-input" type="number" min="0" max="100000" step="1" required /><span class="hint">Also order-level. Same caution as delivery.</span></div>
            </div>
          </div>

          <div class="record-section">
            <div class="record-legend">Margin and promotion</div>
            <div class="engine-grid">
              <div class="engine-field"><label for="inputMarginPct">Target margin (%)</label><input id="inputMarginPct" class="engine-input" type="number" min="0" max="99.99" step="0.1" required /><span class="hint">Gross margin on the list price, before any promotional discount.</span></div>
              <fieldset class="engine-field" style="border:0;padding:0;margin:0;">
                <legend>Discount type and value</legend>
                <div class="discount-type-group" role="radiogroup" aria-label="Discount mode">
                  <button type="button" class="discount-type-btn active" id="btnTypePct" role="radio" aria-checked="true">Percentage</button>
                  <button type="button" class="discount-type-btn" id="btnTypeAmt" role="radio" aria-checked="false">Amount (BDT)</button>
                </div>
                <input id="inputDiscountVal" class="engine-input" type="number" min="0" step="1" style="margin-top:5px;" required />
                <span class="hint" id="discountHint">Promotional discount percentage</span>
              </fieldset>
            </div>
          </div>

          <div class="engine-preview-card">
            <div class="engine-preview-row"><span>Total variable overhead</span><strong id="summaryOverhead">—</strong></div>
            <div class="engine-preview-row"><span>Formula</span><span id="formulaDescription">(Source cost + overhead) ÷ (1 − margin%) − discount</span></div>
            <div class="engine-preview-row total-highlight"><span>Worked example at ৳1,000 source cost</span><strong id="summarySample">—</strong></div>
          </div>

          <div id="engineStatus" class="status-message" role="status" aria-live="polite"></div>
          <div class="form-actions">
            <button class="btn-calc" id="applyEngineBtn" type="submit">Save global defaults</button>
          </div>

          <div class="danger-zone">
            <div class="danger-zone-copy">
              <strong>Reset every SKU tune</strong>
              <span>Deletes all per-product overrides across the catalog. This cannot be undone.</span>
            </div>
            <button class="btn-danger" id="resetCustomOverridesBtn" type="button">Reset all tunes</button>
          </div>
        </form>
      </dialog>

      <dialog id="dialog" aria-labelledby="dialogName">
        <div class="modal-header">
          <div class="modal-heading-group">
            <span class="modal-kicker" id="dialogBrand"></span>
            <h2 class="modal-title" id="dialogName"></h2>
          </div>
          <button class="modal-btn-close" id="close" type="button" aria-label="Close product detail"><CloseIcon /></button>
        </div>
        <div class="modal-body">
          <div class="tab-nav" role="tablist" aria-label="Product detail views">
            <button class="tab-btn active" id="tabOverviewBtn" type="button" role="tab" tabindex={0} aria-selected="true" aria-controls="tabOverviewContent">Market position</button>
            <button class="tab-btn" id="tabTuneBtn" type="button" role="tab" tabindex={-1} aria-selected="false" aria-controls="tabTuneContent">Tune this SKU</button>
          </div>
          <div id="tabOverviewContent" role="tabpanel" aria-labelledby="tabOverviewBtn" style="display:grid;gap:22px;"></div>
          <form id="tabTuneContent" role="tabpanel" aria-labelledby="tabTuneBtn" style="display:none;gap:20px;">
            <div class="read-only-note" id="productReadOnlyBanner" hidden></div>
            <p class="tune-inherit-note">Leave a field blank to follow the global engine — blank fields keep tracking later global changes. Fill one only to pin it for this SKU.</p>
            <div class="engine-grid">
              <div class="engine-field"><label for="prodInputPackaging">Packaging (BDT)</label><input id="prodInputPackaging" class="engine-input" type="number" min="0" max="100000" step="1" /></div>
              <div class="engine-field"><label for="prodInputTransport">Transport (BDT)</label><input id="prodInputTransport" class="engine-input" type="number" min="0" max="100000" step="1" /></div>
              <div class="engine-field"><label for="prodInputDelivery">Delivery (BDT)</label><input id="prodInputDelivery" class="engine-input" type="number" min="0" max="100000" step="1" /></div>
              <div class="engine-field"><label for="prodInputCAC">CAC (BDT)</label><input id="prodInputCAC" class="engine-input" type="number" min="0" max="100000" step="1" /></div>
              <div class="engine-field"><label for="prodInputMarginPct">Target margin (%)</label><input id="prodInputMarginPct" class="engine-input" type="number" min="0" max="99.99" step="0.1" /></div>
              <fieldset class="engine-field" style="border:0;padding:0;margin:0;">
                <legend>Discount type and value</legend>
                <div class="discount-type-group" role="radiogroup" aria-label="Product discount mode">
                  <button type="button" class="discount-type-btn active" id="prodBtnTypeGlobal" role="radio" aria-checked="true">Global</button>
                  <button type="button" class="discount-type-btn" id="prodBtnTypePct" role="radio" aria-checked="false">Percentage</button>
                  <button type="button" class="discount-type-btn" id="prodBtnTypeAmt" role="radio" aria-checked="false">Amount</button>
                </div>
                <input id="prodInputDiscountVal" class="engine-input" type="number" min="0" step="1" style="margin-top:5px;" />
              </fieldset>
            </div>
            <div class="engine-preview-card">
              <div class="engine-preview-row"><span>Pinned for this SKU</span><strong id="prodSummaryPinned">Nothing — follows global</strong></div>
              <div class="engine-preview-row"><span>Global engine price</span><strong id="prodSummaryGlobalPrice">—</strong></div>
              <div class="engine-preview-row total-highlight"><span>Selling price for this SKU</span><strong id="prodSummarySelling">—</strong></div>
            </div>
            <div id="productTuneStatus" class="status-message" role="status" aria-live="polite"></div>
            <div class="form-actions">
              <button class="btn-calc" id="saveProductCustomEngineBtn" type="submit">Save custom SKU settings</button>
              <button class="btn-ghost" id="clearProductCustomEngineBtn" type="button">Reset to global</button>
            </div>
          </form>
        </div>
      </dialog>
    </>
  )
}
