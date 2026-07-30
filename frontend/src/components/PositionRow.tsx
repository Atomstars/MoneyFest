import { useEffect, useState } from 'react'
import { api, type Position } from '../lib/api'
import { money, signedMoney, signedPct, directionOf } from '../lib/format'
import { Sparkline } from './charts/Sparkline'
import { OutcomeChip } from './ui'

/**
 * One holding. Left: identity + why-it-moved. Right: the numbers.
 *
 * The `outcome` chip is what a broker app cannot show -- it is the join between
 * the position and the explanation engine. It stays visually quiet so it reads
 * as context, not as a signal to act on.
 */
export function PositionRow({ p, onOpen }: { p: Position; onOpen: (p: Position) => void }) {
  const [spark, setSpark] = useState<number[]>([])

  useEffect(() => {
    let alive = true
    api.prices(p.stock_id, 30)
      .then((rows) => { if (alive) setSpark(rows.map((r) => r.close)) })
      .catch(() => { /* sparkline is decoration; its absence must not break the row */ })
    return () => { alive = false }
  }, [p.stock_id])

  const dir = directionOf(p.day_change)
  const unpriced = p.price === null

  return (
    <button
      onClick={() => onOpen(p)}
      className="group flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left transition-colors sm:gap-4"
      style={{ background: 'transparent' }}
      onPointerEnter={(e) => {
        e.currentTarget.style.background = 'color-mix(in srgb, var(--text-primary) 4%, transparent)'
      }}
      onPointerLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
    >
      {/* Identity */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-semibold">{p.ticker ?? p.name}</span>
          <OutcomeChip outcome={p.outcome ?? p.gate_result} />
        </div>
        <div className="mt-0.5 truncate text-xs" style={{ color: 'var(--text-muted)' }}>
          {p.qty} share{p.qty === 1 ? '' : 's'} · avg {money(p.avg_cost, true)}
        </div>
      </div>

      {/* Trend shape -- hidden on narrow screens where the numbers matter more */}
      <div className="hidden shrink-0 sm:block">
        <Sparkline values={spark} direction={dir} />
      </div>

      {/* Numbers */}
      <div className="shrink-0 text-right">
        <div className="tnum text-sm font-semibold">
          {unpriced ? '—' : money(p.market_value)}
        </div>
        <div className="tnum text-xs">
          {unpriced ? (
            <span style={{ color: 'var(--text-muted)' }}>no price</span>
          ) : (
            <span style={{ color: (p.pnl ?? 0) >= 0 ? 'var(--up)' : 'var(--down)' }}>
              {signedMoney(p.pnl)} ({signedPct(p.pnl_pct)})
            </span>
          )}
        </div>
      </div>
    </button>
  )
}
