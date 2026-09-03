import type { DashboardMeta, SourcingOrigin } from '../types'

const BOOKS: ReadonlyArray<{ origin: SourcingOrigin; href: string; label: string }> = [
  { origin: 'local', href: '/', label: 'Local' },
  { origin: 'imported', href: '/imported', label: 'Imported' },
]

/**
 * Floating switch between the two sourcing books. It navigates between real
 * routes rather than filtering in place, so each book stays bookmarkable, and
 * it carries both counts so the size of the other book is visible from here.
 */
export function OriginSwitch({ meta }: { meta: DashboardMeta }) {
  return (
    <nav class="origin-switch" aria-label="Sourcing origin">
      {BOOKS.map(({ origin, href, label }) => {
        const active = meta.origin === origin
        return (
          <a
            href={href}
            class={active ? 'origin-option is-active' : 'origin-option'}
            data-origin={origin}
            aria-current={active ? 'page' : undefined}
          >
            {label}
            <span class="origin-count">{meta.originCounts[origin]}</span>
          </a>
        )
      })}
    </nav>
  )
}
