/**
 * One drawn icon set at a single stroke weight, so no unicode glyph ever
 * stands in for an icon. Server-rendered variants live here; the browser
 * bundle carries string equivalents in `client/icons.ts`.
 */

const stroke = {
  fill: 'none',
  stroke: 'currentColor',
  'stroke-width': '1.6',
  'stroke-linecap': 'round',
  'stroke-linejoin': 'round',
} as const

export const SearchIcon = () => (
  <svg aria-hidden="true" viewBox="0 0 16 16" {...stroke}>
    <circle cx="7" cy="7" r="4.5" />
    <path d="M10.4 10.4 14 14" />
  </svg>
)

export const SlidersIcon = () => (
  <svg aria-hidden="true" viewBox="0 0 16 16" {...stroke}>
    <path d="M2 4.5h8M13 4.5h1M2 11.5h1M6 11.5h8" />
    <circle cx="11.5" cy="4.5" r="1.6" />
    <circle cx="4.5" cy="11.5" r="1.6" />
  </svg>
)

export const LockIcon = () => (
  <svg aria-hidden="true" viewBox="0 0 16 16" {...stroke}>
    <rect x="3" y="7" width="10" height="7" />
    <path d="M5.5 7V4.9a2.5 2.5 0 0 1 5 0V7" />
  </svg>
)

export const DownloadIcon = () => (
  <svg aria-hidden="true" viewBox="0 0 16 16" {...stroke}>
    <path d="M8 2v8M4.8 6.9 8 10.2l3.2-3.3M2.6 13.4h10.8" />
  </svg>
)

export const CompareIcon = () => (
  <svg aria-hidden="true" viewBox="0 0 16 16" {...stroke}>
    <path d="M2.5 5.5h8M8 3l2.5 2.5L8 8" />
    <path d="M13.5 10.5h-8M8 13l-2.5-2.5L8 8" />
  </svg>
)

export const CloseIcon = () => (
  <svg aria-hidden="true" viewBox="0 0 16 16" {...stroke}>
    <path d="M4 4l8 8M12 4l-8 8" />
  </svg>
)
