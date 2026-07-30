import { useState } from 'react'
import { money, pct } from '../../lib/format'
import type { AllocationSlice } from '../../lib/api'

/** Categorical slots in fixed order. Assigned by entity (sector), never cycled:
 *  filtering the list must not repaint the survivors. */
const SERIES = [
  'var(--series-1)', 'var(--series-2)', 'var(--series-3)',
  'var(--series-4)', 'var(--series-5)', 'var(--series-6)',
]
const MAX_SLICES = 6   // a 7th sector folds into "Other" -- never a generated hue

function arc(cx: number, cy: number, r: number, from: number, to: number) {
  const p = (a: number) => [cx + r * Math.cos(a), cy + r * Math.sin(a)]
  const [x1, y1] = p(from)
  const [x2, y2] = p(to)
  return `M${x1},${y1}A${r},${r} 0 ${to - from > Math.PI ? 1 : 0} 1 ${x2},${y2}`
}

/**
 * Sector allocation donut.
 *
 * The legend always shows name + value + weight. That is required, not
 * decorative: three light-mode slots sit below 3:1 contrast on the light
 * surface, so the palette's relief rule mandates visible direct labels.
 */
export function DonutChart({ data, total }: { data: AllocationSlice[]; total: number }) {
  const [active, setActive] = useState<number | null>(null)

  const slices =
    data.length <= MAX_SLICES
      ? data
      : [
          ...data.slice(0, MAX_SLICES - 1),
          {
            sector: 'Other',
            value: data.slice(MAX_SLICES - 1).reduce((s, d) => s + d.value, 0),
            weight: data.slice(MAX_SLICES - 1).reduce((s, d) => s + (d.weight ?? 0), 0),
          },
        ]

  const size = 190
  const cx = size / 2
  const cy = size / 2
  const r = 74
  const stroke = 22
  const GAP = 0.02   // ~2px surface gap between adjacent fills

  let angle = -Math.PI / 2
  const arcs = slices.map((s, i) => {
    const frac = total > 0 ? s.value / total : 0
    const sweep = frac * Math.PI * 2
    const a0 = angle + GAP / 2
    const a1 = angle + sweep - GAP / 2
    angle += sweep
    return { ...s, a0: a1 > a0 ? a0 : angle - sweep, a1: Math.max(a1, a0 + 0.001), color: SERIES[i], frac }
  })

  const shown = active !== null ? arcs[active] : null

  return (
    <div className="flex flex-col items-center gap-5 sm:flex-row sm:items-center sm:gap-7">
      <div className="relative shrink-0">
        <svg width={size} height={size} role="img" aria-label="Allocation by sector">
          {arcs.map((a, i) => (
            <path
              key={a.sector}
              d={arc(cx, cy, r, a.a0, a.a1)}
              fill="none"
              stroke={a.color}
              strokeWidth={active === i ? stroke + 5 : stroke}
              strokeLinecap="butt"
              style={{ transition: 'stroke-width .18s ease', cursor: 'pointer' }}
              onPointerEnter={() => setActive(i)}
              onPointerLeave={() => setActive(null)}
            />
          ))}
        </svg>
        <div className="pointer-events-none absolute inset-0 grid place-content-center text-center">
          <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            {shown ? shown.sector.replace(/_/g, ' ') : 'Total'}
          </div>
          <div className="text-lg font-semibold">
            {shown ? pct(shown.frac) : money(total)}
          </div>
          {shown && (
            <div className="tnum text-[11px]" style={{ color: 'var(--text-secondary)' }}>
              {money(shown.value)}
            </div>
          )}
        </div>
      </div>

      {/* Legend: identity is never carried by colour alone. */}
      <ul className="w-full min-w-0 space-y-1.5">
        {arcs.map((a, i) => (
          <li
            key={a.sector}
            className="flex items-center gap-2.5 rounded-md px-1.5 py-1 text-sm transition-colors"
            style={{ background: active === i ? 'color-mix(in srgb, var(--text-primary) 5%, transparent)' : undefined }}
            onPointerEnter={() => setActive(i)}
            onPointerLeave={() => setActive(null)}
          >
            <span className="size-2.5 shrink-0 rounded-full" style={{ background: a.color }} />
            <span className="min-w-0 flex-1 truncate" style={{ color: 'var(--text-secondary)' }}>
              {a.sector.replace(/_/g, ' ').toLowerCase()}
            </span>
            <span className="tnum shrink-0 font-medium">{pct(a.frac, 1)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
