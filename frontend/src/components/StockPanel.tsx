import { Link } from 'react-router-dom'
import { useEffect, useRef, useState } from 'react'
import { api, type Position, type PricePoint, type Assessment, type Driver, type StockDetail, type StockRow } from '../lib/api'
import { money, signedMoney, signedPct, pct, OUTCOME_HELP, directionOf } from '../lib/format'
import { LineChart } from './charts/LineChart'
import { OutcomeChip } from './ui'
import { NewsFeed } from './NewsFeed'
import { RefreshButton } from './RefreshButton'

/**
 * Slide-over detail for one holding.
 *
 * The order is deliberate: position facts, then price, then *why it moved*. The
 * explanation is the reason this app exists, so it gets its own block with the
 * engine's own words -- never paraphrased here, because the renderer already
 * guarantees every sentence traces to a verified claim.
 */
export function StockPanel({ position, onClose }: { position: Position | StockRow; onClose: () => void }) {
  const holding = 'qty' in position ? position : null
  const panelRef = useRef<HTMLElement>(null)
  const [prices, setPrices] = useState<PricePoint[]>([])
  const [loading, setLoading] = useState(true)
  const [assessment, setAssessment] = useState<Assessment | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    const update = () => setRevision(n => n + 1)
    window.addEventListener('moneyfest-data-updated', update)
    return () => window.removeEventListener('moneyfest-data-updated', update)
  }, [])

  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null
    panelRef.current?.querySelector<HTMLElement>('button')?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key !== 'Tab') return
      const nodes = panelRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input, select, [tabindex="0"]')
      if (!nodes?.length) return
      const first = nodes[0], last = nodes[nodes.length - 1]
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
      previousFocus?.focus()
    }
  }, [onClose])

  useEffect(() => {
    setLoading(true)
    let alive = true
    setError(null); setAssessment(null)
    Promise.all([api.prices(position.stock_id, 90), api.assessment(position.stock_id)])
      .then(([points, result]) => { if (alive) { setPrices(points); setAssessment(result) } })
      .catch((e) => { if (alive) setError(e.message) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [position.stock_id, revision])

  const outcome = assessment?.outcome ?? holding?.outcome ?? position.gate_result
  const drivers: Driver[] = assessment?.drivers_json ? JSON.parse(assessment.drivers_json) : []
  const evidence: StockDetail['evidence'] = assessment?.evidence_json ? JSON.parse(assessment.evidence_json) : []
  const dir = directionOf(holding?.day_change ?? ('change_pct' in position ? position.change_pct : null))

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div
        className="absolute inset-0"
        style={{ background: 'rgba(0,0,0,0.45)' }}
        onClick={onClose}
        aria-hidden="true"
      />

      <aside
        ref={panelRef}
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
          <RefreshButton stockId={position.stock_id} /><Link className="text-link" to={`/stock-research?stockId=${position.stock_id}`}>Open stock research & trade planner →</Link>
          {error && <p role="alert" className="text-sm">Unable to load stock details: {error}</p>}
          {/* Value + P&L */}
          {holding && <>
          <div>
            <div className="text-3xl font-semibold tracking-tight">
              {money(holding.market_value, false, position.currency)}
            </div>
            <div className="mt-1 text-sm">
              <span style={{ color: (holding.pnl ?? 0) >= 0 ? 'var(--up)' : 'var(--down)' }}>
                <span className="tnum font-semibold">{signedMoney(holding.pnl, position.currency)}</span>
                <span className="tnum ml-1">({signedPct(holding.pnl_pct)})</span>
              </span>
              <span className="ml-1" style={{ color: 'var(--text-muted)' }}>overall</span>
            </div>
          </div>

          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm sm:grid-cols-4">
            {[
              ['Qty', String(holding.qty)],
              ['Avg cost', money(holding.avg_cost, true, position.currency)],
              ['Last price', money(holding.price, true, position.currency)],
              ['Weight', pct(holding.weight, 1)],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs" style={{ color: 'var(--text-muted)' }}>{k}</dt>
                <dd className="tnum mt-0.5 font-medium">{v}</dd>
              </div>
            ))}
          </dl>
          </>}

          {/* Price history */}
          <section>
            <h3 className="mb-3 text-sm font-semibold">Price · 90 days</h3>
            {loading ? (
              <div className="h-[220px] animate-pulse rounded-lg"
                   style={{ background: 'color-mix(in srgb, var(--text-primary) 8%, transparent)' }} />
            ) : (
              <LineChart
                currency={position.currency}
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
                {assessment?.rendered_text ?? OUTCOME_HELP[outcome] ?? outcome}
              </p>
            ) : (
              <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
                No assessment recorded for this date yet.
              </p>
            )}
            {drivers.map((driver) => <div key={driver.rank} className="mt-3 border-t pt-3" style={{ borderColor: 'var(--border)' }}>
              <p className="text-sm">{driver.chain_text}</p>
              <p className="mt-1 text-xs" style={{ color: 'var(--text-muted)' }}>{driver.confidence} · {driver.confidence_reason}</p>
              <ul className="mt-2 space-y-1 text-xs">{evidence.filter((item) => driver.evidence_ids.includes(item.id)).map((item) => <li key={item.id}>
                {item.url && /^https?:\/\//i.test(item.url) ? <a href={item.url} target="_blank" rel="noopener noreferrer" className="underline">{item.headline ?? item.source}</a> : item.headline ?? item.source}
                <span className="ml-2" style={{ color: 'var(--text-muted)' }}>{item.source} · Tier {item.tier}</span>
              </li>)}</ul>
            </div>)}

            <p className="mt-3 text-[11px]" style={{ color: 'var(--text-muted)' }}>
              {outcome === 'NOISE' || outcome === 'MARKET'
                ? '“Nothing to explain” is a real answer — most trading days are exactly this.'
                : 'Detailed drivers and cited evidence appear here once the reasoning layer has run for this day.'}
            </p>
          </section>

          <NewsFeed stockId={position.stock_id} />
          <p className="pb-4 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
            Explanation only — not investment advice.
          </p>
        </div>
      </aside>
    </div>
  )
}
