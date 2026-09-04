/**
 * Icon markup for the strings the client builds with innerHTML. Same drawn
 * set and stroke weight as `components/icons.tsx`, so nothing in the sheet
 * falls back to a unicode glyph.
 */

const attrs = 'fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"'

/** Opens a verified listing in a new tab. */
export const ICON_EXTERNAL =
  `<svg aria-hidden="true" viewBox="0 0 16 16" ${attrs}><path d="M6.4 3.2H3.2v9.6h9.6V9.6M9.6 3.2h3.2v3.2M12.8 3.2 7.4 8.6"/></svg>`

/** A price recorded from research whose product page is not confirmed. */
export const ICON_UNVERIFIED =
  `<svg aria-hidden="true" viewBox="0 0 16 16" ${attrs}><circle cx="8" cy="8" r="5" stroke-dasharray="2.2 2.2"/></svg>`

/** Direction marks inside a markup chip: measured above / below the basis. */
export const ICON_CHIP_UP =
  `<svg aria-hidden="true" viewBox="0 0 8 8" ${attrs} stroke-width="2"><path d="M4 6.6V1.6M1.6 4 4 1.6 6.4 4"/></svg>`
export const ICON_CHIP_DOWN =
  `<svg aria-hidden="true" viewBox="0 0 8 8" ${attrs} stroke-width="2"><path d="M4 1.4v5M1.6 4 4 6.4 6.4 4"/></svg>`
