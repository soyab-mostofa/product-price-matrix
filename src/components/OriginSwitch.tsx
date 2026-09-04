import type { DashboardMeta, SourcingOrigin } from '../types'

const BOOKS: ReadonlyArray<{ origin: SourcingOrigin; href: string; label: string }> = [
  { origin: 'local', href: '/', label: 'Local' },
  { origin: 'imported', href: '/imported', label: 'Imported' },
]

/**
 * The two sourcing books, docked into the header rule as register tabs. They
 * navigate real routes rather than filtering in place, so each book stays
 * bookmarkable, and each carries its own count so the size of the book you
 * are not reading is legible from here.
 */
export function OriginSwitch({ meta }: { meta: DashboardMeta }) {
  return (
    <nav class="origin-switch" aria-label="Sourcing origin">
      {BOOKS.map(({ origin, href, label }) => {
        const active = meta.origin === origin
        const count = meta.originCounts[origin]
        return (
          <a
            href={href}
            class={active ? 'origin-option is-active' : 'origin-option'}
            data-origin={origin}
            aria-current={active ? 'page' : undefined}
            // Without this the count abuts the label and announces as
            // "Local407"; the visible text stays a label and a numeral.
            aria-label={`${label} sourcing — ${count} SKUs`}
          >
            {label}
            <span class="origin-count" aria-hidden="true">{count}</span>
          </a>
        )
      })}
    </nav>
  )
}
