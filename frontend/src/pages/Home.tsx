import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  api, type IndexQuote, type Mover, type Movers, type PortfolioSummary, type Position,
} from '../lib/api'
import { money, signedMoney, signedPct } from '../lib/format'
import { CountUp, LiveDot, Shimmer } from '../components/motion'
import { Card, DeltaPill, ErrorNote, SectionHead } from '../components/ui'

/**
 * Home.
 *
 * Stacked sections, in the order a holder actually cares about them:
 *
 *   1. What my portfolio is worth, and what it did today
 *   2. My holdings — current value, cost, and change. Nothing else.
 *   3. Where the market is (indices)
 *   4. What moved most today
 *
 * Two deliberate omissions. There are **no charts here** — a sparkline in every row
 * is decoration that competes with the numbers, and the detail page is one tap away
 * for anyone who wants the shape. And there are **no outcome chips**: "why did this
 * move" is the detail page's job, and putting an engine verdict beside every holding
 * on the home screen made the list read as a scorecard rather than a position list.
 */

// --- 1. Portfolio hero ------------------------------------------------------

function PortfolioHero({ data }: { data: PortfolioSummary | null }) {
  if (!data) {
    return (
      <div className="card-raised mb-3 p-4">
        <Shimmer className="h-3 w-24" />
        <Shimmer className="mt-2.5 h-8 w-44" />
        <Shimmer className="mt-3 h-3 w-56" />
      </div>
    )
  }

  const dayUp = (data.day_change ?? 0) >= 0
  const totalUp = (data.total_pnl ?? 0) >= 0

  return (
    <div className="card-raised rise mb-3 p-4 sm:p-5">
      <div className="flex items-center gap-1.5">
        <span className="text-[11px] font-medium tracking-wide uppercase"
              style={{ color: 'var(--text-muted)' }}>
          Portfolio value
        </span>
        <LiveDot colour={dayUp ? 'var(--up)' : 'var(--down)'} />
      </div>

      <div className="mt-1 flex flex-wrap items-end gap-x-3 gap-y-1">
        <CountUp
          value={data.total_value}
          format={(v) => money(v)}
          className="money text-[28px] leading-none font-semibold tracking-tight sm:text-[34px]"
        />
        <DeltaPill value={data.day_change_pct} />
      </div>

      <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2">
        {([
          ['Today', signedMoney(data.day_change), dayUp],
          ['Total returns', signedMoney(data.total_pnl), totalUp],
          ['Invested', money(data.total_invested), null],
        ] as Array<[string, string, boolean | null]>).map(([label, value, up]) => (
          <div key={label}>
            <div className="text-[10px] tracking-wide uppercase"
                 style={{ color: 'var(--text-muted)' }}>
              {label}
            </div>
            <div
              className="money mt-0.5 text-sm font-semibold"
              style={{ color: up === null ? 'var(--text-primary)'
                : up ? 'var(--up)' : 'var(--down)' }}
            >
              {value}
            </div>
          </div>
        ))}
      </div>

      {/* An unpriced position is excluded from the total, so the total is only
          trustworthy if we say when something is missing from it. */}
      {data.unpriced_positions > 0 && (
        <p className="mt-3 text-[11px]" style={{ color: 'var(--text-muted)' }}>
          {data.unpriced_positions} position{data.unpriced_positions === 1 ? '' : 's'} could
          not be priced and {data.unpriced_positions === 1 ? 'is' : 'are'} excluded from this total.
        </p>
      )}
    </div>
  )
}

// --- 2. Holdings ------------------------------------------------------------

function HoldingRow({ position, index, asOf }: {
  position: Position; index: number; asOf: string | null
}) {
  // A position priced before the portfolio's as-of date is stale — say so on the row
  // rather than letting an old close pass as today's.
  const stale = position.priced_on != null && asOf != null && position.priced_on < asOf

  return (
    <Link
      to={`/stock/${position.stock_id}`}
      className="row-hover stagger flex items-center gap-3 px-3.5 py-2.5"
      style={{ '--i': index } as React.CSSProperties}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="truncate text-[13px] font-semibold">
            {position.ticker ?? position.name}
          </span>
          {stale && (
            <span
              title={`Priced ${position.priced_on}, older than the rest of the portfolio`}
              className="shrink-0 rounded px-1 text-[9px] font-medium"
              style={{ border: '1px solid var(--border)', color: 'var(--text-muted)' }}
            >
              {position.priced_on?.slice(5)}
            </span>
          )}
        </div>
        <div className="money mt-0.5 text-[11px]" style={{ color: 'var(--text-muted)' }}>
          {position.qty} × {money(position.avg_cost, true)}
        </div>
      </div>

      <div className="shrink-0 text-right">
        <div className="money text-[13px] font-semibold">{money(position.market_value)}</div>
        <div
          className="money mt-0.5 text-[11px] font-medium"
          style={{ color: (position.pnl ?? 0) >= 0 ? 'var(--up)' : 'var(--down)' }}
        >
          {signedMoney(position.pnl)} · {signedPct(position.pnl_pct)}
        </div>
      </div>

      <div className="w-[72px] shrink-0 text-right">
        <DeltaPill value={position.day_change_pct} size="sm" />
      </div>
    </Link>
  )
}

function Holdings({ data }: { data: PortfolioSummary | null }) {
  if (!data) {
    return (
      <Card className="!p-0">
        <div className="row-list">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex items-center justify-between px-3.5 py-3">
              <Shimmer className="h-7 w-32" />
              <Shimmer className="h-7 w-24" />
            </div>
          ))}
        </div>
      </Card>
    )
  }

  if (data.positions.length === 0) {
    return (
      <Card>
        <p className="py-6 text-center text-[13px]" style={{ color: 'var(--text-muted)' }}>
          No holdings yet.{' '}
          <Link to="/explore" className="font-medium underline underline-offset-2"
                style={{ color: 'var(--series-1)' }}>
            Find a stock
          </Link>{' '}
          to get started.
        </p>
      </Card>
    )
  }

  return (
    <Card className="!p-0 overflow-hidden">
      <div className="row-list">
        {data.positions.map((p, i) => (
          <HoldingRow key={p.stock_id} position={p} index={i} asOf={data.as_of} />
        ))}
      </div>
    </Card>
  )
}

// --- 3. Indices -------------------------------------------------------------

function IndexCard({ index, i }: { index: IndexQuote; i: number }) {
  const up = (index.change_pct ?? 0) >= 0
  return (
    <div
      className="stagger shrink-0 rounded-[10px] px-3 py-2.5"
      style={{
        minWidth: 148,
        border: '1px solid var(--border)',
        background: 'var(--surface-1)',
        '--i': i,
      } as React.CSSProperties}
    >
      <div className="truncate text-[10px] font-medium tracking-wide uppercase"
           style={{ color: 'var(--text-muted)' }}>
        {index.name}
      </div>
      <div className="money mt-1 text-[15px] font-semibold">
        {index.value.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
      </div>
      <div className="money mt-0.5 text-[11px] font-medium"
           style={{ color: up ? 'var(--up)' : 'var(--down)' }}>
        {index.change != null
          ? `${up ? '+' : '−'}${Math.abs(index.change).toFixed(2)}`
          : '—'}{' '}
        ({signedPct(index.change_pct)})
      </div>
    </div>
  )
}

function Indices({ data }: { data: IndexQuote[] | null }) {
  if (!data) {
    return (
      <div className="flex gap-2 overflow-hidden">
        {Array.from({ length: 4 }).map((_, i) => (
          <Shimmer key={i} className="h-[70px] shrink-0" style={{ minWidth: 148 }} />
        ))}
      </div>
    )
  }
  if (data.length === 0) return null
  return (
    <div className="-mx-5 flex gap-2 overflow-x-auto px-5 pb-1">
      {data.map((index, i) => <IndexCard key={index.symbol} index={index} i={i} />)}
    </div>
  )
}

// --- 4. Top movers ----------------------------------------------------------

function MoverRow({ mover, index }: { mover: Mover; index: number }) {
  const body = (
    <>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[12px] font-semibold">{mover.symbol}</div>
        <div className="money mt-0.5 text-[11px]" style={{ color: 'var(--text-muted)' }}>
          {money(mover.price, true)}
        </div>
      </div>
      <DeltaPill value={mover.change_pct} size="sm" />
    </>
  )

  // Only tracked names have a stock page; the rest are not clickable rather than
  // linking somewhere that would silently promote and backfill them.
  return mover.stock_id ? (
    <Link
      to={`/stock/${mover.stock_id}`}
      className="row-hover stagger flex items-center gap-2 px-3.5 py-2"
      style={{ '--i': index } as React.CSSProperties}
    >
      {body}
    </Link>
  ) : (
    <div
      className="stagger flex items-center gap-2 px-3.5 py-2"
      style={{ '--i': index } as React.CSSProperties}
    >
      {body}
    </div>
  )
}

function MoversColumn({ title, rows, tone }: {
  title: string; rows: Mover[]; tone: 'up' | 'down'
}) {
  return (
    <Card className="!p-0 overflow-hidden">
      <div
        className="flex items-center gap-1.5 px-3.5 py-2"
        style={{ borderBottom: '1px solid var(--hairline)' }}
      >
        <span className="size-1.5 rounded-full"
              style={{ background: tone === 'up' ? 'var(--up)' : 'var(--down)' }} />
        <h3 className="text-[11px] font-semibold tracking-wide uppercase"
            style={{ color: 'var(--text-secondary)' }}>
          {title}
        </h3>
      </div>
      <div className="row-list">
        {rows.length === 0 ? (
          <p className="px-3.5 py-5 text-center text-[12px]" style={{ color: 'var(--text-muted)' }}>
            Nothing {tone === 'up' ? 'up' : 'down'} today.
          </p>
        ) : (
          rows.map((m, i) => <MoverRow key={m.symbol} mover={m} index={i} />)
        )}
      </div>
    </Card>
  )
}

// --- Page -------------------------------------------------------------------

export function Home() {
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null)
  const [indices, setIndices] = useState<IndexQuote[] | null>(null)
  const [movers, setMovers] = useState<Movers | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    setError(null)
    // Independent: a market-data outage must not blank the portfolio, which is the
    // one thing on this screen that comes from our own database and always works.
    api.portfolio().then(setPortfolio).catch((e) => setError(e.message))
    api.indices().then((r) => setIndices(r.indices)).catch(() => setIndices([]))
    api.movers().then(setMovers).catch(() => setMovers(null))
  }
  useEffect(load, [])

  if (error) return <ErrorNote error={error} onRetry={load} />

  return (
    <div className="space-y-5">
      <section>
        <PortfolioHero data={portfolio} />
        <SectionHead
          title="Your holdings"
          action={
            portfolio && (
              <Link to="/dashboard" className="text-[11px] font-medium"
                    style={{ color: 'var(--series-1)' }}>
                Full breakdown →
              </Link>
            )
          }
        />
        <Holdings data={portfolio} />
      </section>

      <section>
        <SectionHead
          title="Markets"
          action={
            <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
              Delayed
            </span>
          }
        />
        <Indices data={indices} />
      </section>

      <section>
        <SectionHead
          title="Today's top movers"
          action={
            movers?.universe ? (
              <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                Top {movers.universe} by market cap
              </span>
            ) : undefined
          }
        />
        {!movers ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <Shimmer className="h-[210px]" />
            <Shimmer className="h-[210px]" />
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            <MoversColumn title="Gainers" rows={movers.gainers} tone="up" />
            <MoversColumn title="Losers" rows={movers.losers} tone="down" />
          </div>
        )}
      </section>

      <p className="pb-2 text-center text-[11px]" style={{ color: 'var(--text-muted)' }}>
        Delayed prices — not a live feed. Explanation only, not investment advice.
      </p>
    </div>
  )
}
