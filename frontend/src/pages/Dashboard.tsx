import { useCallback, useEffect, useState } from 'react'
import {
  api, type PortfolioSummary, type AllocationSlice, type HistoryPoint, type Position,
} from '../lib/api'
import { money, signedMoney, signedPct, longDate, OUTCOME_HELP } from '../lib/format'
import { LineChart } from '../components/charts/LineChart'
import { DonutChart } from '../components/charts/DonutChart'
import { PositionRow } from '../components/PositionRow'
import { StockPanel } from '../components/StockPanel'
import { Card, CardTitle, ErrorNote, Skeleton } from '../components/ui'
import { PageHeader, SECTIONS } from '../components/Shell'

const RANGES = [30, 90, 180] as const

export function Dashboard() {
  const [pf, setPf] = useState<PortfolioSummary | null>(null)
  const [alloc, setAlloc] = useState<AllocationSlice[]>([])
  const [hist, setHist] = useState<HistoryPoint[]>([])
  const [days, setDays] = useState<(typeof RANGES)[number]>(90)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Position | null>(null)

  const load = useCallback(() => {
    setError(null)
    Promise.all([api.portfolio(), api.allocation(), api.portfolioHistory(days)])
      .then(([p, a, h]) => { setPf(p); setAlloc(a); setHist(h) })
      .catch((e) => setError(e.message))
  }, [days])

  useEffect(load, [load])

  if (error) return <ErrorNote error={error} onRetry={load} />

  const gainers = pf?.positions.filter((p) => (p.pnl ?? 0) > 0).length ?? 0

  // Same fallback the position rows use: `outcome` is only set once the reasoning
  // layer has written an attribution row, but the gate result is always present and
  // is what the chip already displays. Reading only `outcome` here made this section
  // disappear on days the chips clearly had something to say.
  const noteworthy = pf?.positions.filter((p) => {
    const o = p.outcome ?? p.gate_result
    return o !== null && !['NOISE', 'WARMING_UP'].includes(o)
  }) ?? []

  return (
    <>
      <PageHeader
        title={SECTIONS['/dashboard'].title}
        subtitle={pf?.as_of ? `Valued at close — ${longDate(pf.as_of)}` : SECTIONS['/dashboard'].subtitle}
      />

      <div className="space-y-5">
        {/* ---- Hero: the one number, then its context ---- */}
        <section className="rise">
          {!pf ? (
            <Card><Skeleton className="h-24 w-full" /></Card>
          ) : (
            <Card>
              <div className="flex flex-wrap items-end justify-between gap-6">
                <div>
                  <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Current value</div>
                  <div className="mt-1 text-4xl font-semibold tracking-tight sm:text-5xl">
                    {money(pf.total_value)}
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                    <span style={{ color: (pf.day_change ?? 0) >= 0 ? 'var(--up)' : 'var(--down)' }}>
                      <span className="tnum font-semibold">{signedMoney(pf.day_change)}</span>
                      <span className="tnum ml-1">({signedPct(pf.day_change_pct)})</span>
                      <span className="ml-1" style={{ color: 'var(--text-muted)' }}>today</span>
                    </span>
                    <span style={{ color: 'var(--text-secondary)' }}>
                      Total{' '}
                      <span
                        className="tnum font-semibold"
                        style={{ color: pf.total_pnl >= 0 ? 'var(--up)' : 'var(--down)' }}
                      >
                        {signedMoney(pf.total_pnl)} ({signedPct(pf.total_pnl_pct)})
                      </span>
                    </span>
                  </div>
                </div>

                <dl className="flex gap-6 text-sm">
                  <div>
                    <dt className="text-xs" style={{ color: 'var(--text-muted)' }}>Invested</dt>
                    <dd className="tnum mt-0.5 font-semibold">{money(pf.total_invested)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs" style={{ color: 'var(--text-muted)' }}>Holdings</dt>
                    <dd className="tnum mt-0.5 font-semibold">{pf.positions.length}</dd>
                  </div>
                  <div>
                    <dt className="text-xs" style={{ color: 'var(--text-muted)' }}>In profit</dt>
                    <dd className="tnum mt-0.5 font-semibold">{gainers}/{pf.positions.length}</dd>
                  </div>
                </dl>
              </div>

              {pf.unpriced_positions > 0 && (
                <p
                  className="mt-4 rounded-lg px-3 py-2 text-xs"
                  style={{
                    background: 'color-mix(in srgb, var(--warning) 14%, transparent)',
                    color: 'var(--text-secondary)',
                  }}
                >
                  {pf.unpriced_positions} holding{pf.unpriced_positions === 1 ? '' : 's'} had no
                  price for this date and {pf.unpriced_positions === 1 ? 'is' : 'are'} excluded from
                  the totals above — not counted as zero.
                </p>
              )}
            </Card>
          )}
        </section>

        {/* ---- Value over time + allocation ---- */}
        <div className="grid gap-5 lg:grid-cols-[1.6fr_1fr]">
          <Card className="rise">
            <CardTitle
              aside={
                <div className="flex gap-1" role="group" aria-label="Time range">
                  {RANGES.map((d) => (
                    <button
                      key={d}
                      onClick={() => setDays(d)}
                      className="rounded-md px-2 py-1 text-xs font-medium transition-colors"
                      style={{
                        background: days === d
                          ? 'color-mix(in srgb, var(--text-primary) 8%, transparent)' : 'transparent',
                        color: days === d ? 'var(--text-primary)' : 'var(--text-muted)',
                      }}
                    >
                      {d}d
                    </button>
                  ))}
                </div>
              }
            >
              Value over time
            </CardTitle>
            {pf ? <LineChart data={hist} label="Portfolio value" /> : <Skeleton className="h-[260px] w-full" />}
            <p className="mt-3 text-[11px]" style={{ color: 'var(--text-muted)' }}>
              Today's holdings valued at past closing prices — not a record of what the
              portfolio was actually worth then.
            </p>
          </Card>

          <Card className="rise">
            <CardTitle aside={`${alloc.length} sectors`}>Allocation</CardTitle>
            {pf ? (
              <DonutChart data={alloc} total={pf.total_value} />
            ) : (
              <Skeleton className="h-[190px] w-full" />
            )}
          </Card>
        </div>

        {/* ---- What moved, and why ---- */}
        {noteworthy.length > 0 && (
          <Card className="rise">
            <CardTitle aside="from the explanation engine">Worth a look today</CardTitle>
            <ul className="space-y-2">
              {noteworthy.map((p) => {
                const o = (p.outcome ?? p.gate_result)!
                return (
                  <li key={p.stock_id} className="flex items-start gap-3 text-sm">
                    <span className="mt-1.5 size-1.5 shrink-0 rounded-full" style={{ background: 'var(--series-1)' }} />
                    <span>
                      <button onClick={() => setSelected(p)} className="font-semibold underline-offset-2 hover:underline">
                        {p.ticker}
                      </button>{' '}
                      <span style={{ color: 'var(--text-secondary)' }}>{OUTCOME_HELP[o] ?? o}</span>
                    </span>
                  </li>
                )
              })}
            </ul>
          </Card>
        )}

        {/* ---- Holdings ---- */}
        <Card className="rise">
          <CardTitle aside={pf ? `${pf.positions.length} positions` : undefined}>Holdings</CardTitle>
          {!pf ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-14 w-full" />)}
            </div>
          ) : pf.positions.length === 0 ? (
            <p className="py-8 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
              No holdings yet.
            </p>
          ) : (
            <div className="-mx-3 divide-y" style={{ borderColor: 'var(--border)' }}>
              {pf.positions.map((p) => (
                <PositionRow key={p.stock_id} p={p} onOpen={setSelected} />
              ))}
            </div>
          )}
        </Card>

        <p className="pb-2 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
          Explanation only — not investment advice.
        </p>
      </div>

      {selected && <StockPanel position={selected} onClose={() => setSelected(null)} />}
    </>
  )
}
