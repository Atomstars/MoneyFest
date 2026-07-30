import { useEffect, useState } from 'react'
import { api, type Position, type PricePoint } from '../lib/api'
import { money, signedMoney, signedPct, pct, OUTCOME_HELP, directionOf } from '../lib/format'
import { LineChart } from './charts/LineChart'
import { OutcomeChip } from './ui'

/**
 * Slide-over detail for one holding.
 *
 * The order is deliberate: position facts, then price, then *why it moved*. The
 * explanation is the reason this app exists, so it gets its own block with the
 * engine's own words -- never paraphrased here, because the renderer already
 * guarantees every sentence traces to a verified claim.
 */
export function StockPanel({ position, onClose }: { position: Position; onClose: () => void }) {
  const [prices, setPrices] = useState<PricePoint[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose])

  useEffect(() => {
    setLoading(true)
    api.prices(position.stock_id, 90)
      .then(setPrices)
      .catch(() => setPrices([]))
      .finally(() => setLoading(false))
  }, [position.stock_id])

  const outcome = position.outcome ?? position.gate_result
  const dir = directionOf(position.day_change)

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div
        className="absolute inset-0"
        style={{ background: 'rgba(0,0,0,0.45)' }}
        onClick={onClose}
        aria-hidden="true"
      />

      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`${position.ticker} details`}
        className="relative flex h-full w-full max-w-lg flex-col overflow-y-auto"
        style={{ background: 'var(--surface-1)', borderLeft: '1px solid var(--border)' }}
      >
        {/* Header */}
        <header
          className="sticky top-0 z-10 flex items-start justify-between gap-3 px-6 py-4 backdrop-blur-xl"
          style={{
            background: 'color-mix(in srgb, var(--surface-1) 88%, transparent)',
            borderBottom: '1px solid var(--border)',
          }}
        >
          <div className="min-w-0">
            <h2 className="truncate text-lg font-semibold tracking-tight">
              {position.ticker ?? position.name}
            </h2>
            <p className="truncate text-xs" style={{ color: 'var(--text-muted)' }}>
              {position.name}
              {position.sector && ` · ${position.sector.replace(/_/g, ' ').toLowerCase()}`}
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="grid size-8 shrink-0 place-items-center rounded-lg"
            style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6 6 18M6 6l12 12" strokeLinecap="round" />
            </svg>
          </button>
        </header>

        <div className="space-y-6 px-6 py-5">
          {/* Value + P&L */}
          <div>
            <div className="text-3xl font-semibold tracking-tight">
              {money(position.market_value)}
            </div>
            <div className="mt-1 text-sm">
              <span style={{ color: (position.pnl ?? 0) >= 0 ? 'var(--up)' : 'var(--down)' }}>
                <span className="tnum font-semibold">{signedMoney(position.pnl)}</span>
                <span className="tnum ml-1">({signedPct(position.pnl_pct)})</span>
              </span>
              <span className="ml-1" style={{ color: 'var(--text-muted)' }}>overall</span>
            </div>
          </div>

          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm sm:grid-cols-4">
            {[
              ['Qty', String(position.qty)],
              ['Avg cost', money(position.avg_cost, true)],
              ['Last price', money(position.price, true)],
              ['Weight', pct(position.weight, 1)],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs" style={{ color: 'var(--text-muted)' }}>{k}</dt>
                <dd className="tnum mt-0.5 font-medium">{v}</dd>
              </div>
            ))}
          </dl>

          {/* Price history */}
          <section>
            <h3 className="mb-3 text-sm font-semibold">Price · 90 days</h3>
            {loading ? (
              <div className="h-[220px] animate-pulse rounded-lg"
                   style={{ background: 'color-mix(in srgb, var(--text-primary) 8%, transparent)' }} />
            ) : (
              <LineChart
                data={prices.map((p) => ({ date: p.date, value: p.close }))}
                height={220}
                label={`${position.ticker} close`}
                color={dir === 'down' ? 'var(--down)' : 'var(--series-1)'}
              />
            )}
          </section>

          {/* The differentiator */}
          <section
            className="rounded-xl p-4"
            style={{ background: 'color-mix(in srgb, var(--text-primary) 4%, transparent)' }}
          >
            <div className="mb-2 flex items-center gap-2">
              <h3 className="text-sm font-semibold">Why it moved</h3>
              <OutcomeChip outcome={outcome} />
            </div>

            {outcome ? (
              <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                {OUTCOME_HELP[outcome] ?? outcome}
              </p>
            ) : (
              <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
                No assessment recorded for this date yet.
              </p>
            )}

            <p className="mt-3 text-[11px]" style={{ color: 'var(--text-muted)' }}>
              {outcome === 'NOISE' || outcome === 'MARKET'
                ? '“Nothing to explain” is a real answer — most trading days are exactly this.'
                : 'Detailed drivers and cited evidence appear here once the reasoning layer has run for this day.'}
            </p>
          </section>

          <p className="pb-4 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
            Explanation only — not investment advice.
          </p>
        </div>
      </aside>
    </div>
  )
}
