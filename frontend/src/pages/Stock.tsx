import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, type Overview, type PricePoint } from '../lib/api'
import { longDate, money, pct, signedMoney, signedPct } from '../lib/format'
import { LineChart } from '../components/charts/LineChart'
import { Card, CardTitle, ErrorNote, OutcomeChip, Skeleton } from '../components/ui'
import { Fundamentals } from '../components/stock/Fundamentals'
import { Shareholding } from '../components/stock/Shareholding'
import { Explanation } from '../components/stock/Explanation'

const TABS = ['Overview', 'Fundamentals', 'Shareholding', 'Why it moved'] as const
type Tab = (typeof TABS)[number]

const CHART_RANGES: Array<[label: string, days: number]> = [
  ['1M', 30], ['3M', 90], ['6M', 180], ['1Y', 365], ['Max', 3650],
]

/** The 1D/1W/1M/… strip. A window with no basis close renders as a dash, never 0%. */
function WindowStrip({ windows }: { windows: Overview['windows'] }) {
  const order = ['1D', '1W', '1M', '3M', '6M', '1Y', '3Y', '5Y']
  const shown = order.filter((k) => windows[k])
  if (shown.length === 0) return null

  return (
    <div className="flex flex-wrap gap-x-6 gap-y-2">
      {shown.map((k) => {
        const w = windows[k]!
        return (
          <div key={k}>
            <div className="text-[10px] tracking-wide uppercase" style={{ color: 'var(--text-muted)' }}>
              {k}
            </div>
            <div
              className="tnum text-sm font-semibold"
              style={{ color: w.pct > 0 ? 'var(--up)' : w.pct < 0 ? 'var(--down)' : 'var(--text-muted)' }}
            >
              {signedPct(w.pct)}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/** 52-week band with the current close marked. Range comes from our own stored
 *  closes, so it always agrees with the chart directly below it. */
function RangeBar({ range }: { range: Overview['range'] }) {
  if (range.high_52w == null || range.low_52w == null) return null
  const position = range.band_position

  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between text-[11px]">
        <span className="tnum" style={{ color: 'var(--text-muted)' }}>{money(range.low_52w, true)}</span>
        <span style={{ color: 'var(--text-muted)' }}>
          {range.covers_days >= 350 ? '52-week range' : `range over ${range.covers_days} days`}
        </span>
        <span className="tnum" style={{ color: 'var(--text-muted)' }}>{money(range.high_52w, true)}</span>
      </div>
      <div className="relative h-1.5 rounded-full"
           style={{ background: 'color-mix(in srgb, var(--text-primary) 10%, transparent)' }}>
        {position != null && (
          <div
            className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full"
            style={{
              left: `${Math.min(Math.max(position * 100, 0), 100)}%`,
              background: 'var(--series-1)',
              border: '2px solid var(--plane)',
            }}
          />
        )}
      </div>
    </div>
  )
}

/** Shown while a never-before-analysed stock warms up. Honest about the wait and
 *  about why: below the gate's lookback floor, every classification is WARMING_UP. */
function WarmingNotice({ history, busy, onWarm }: {
  history: Overview['history']; busy: boolean; onWarm: () => void
}) {
  return (
    <Card>
      <CardTitle>Warming up the engine</CardTitle>
      <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
        This stock has {history.days} day{history.days === 1 ? '' : 's'} of price history.
        The gate needs {history.min_required} trading days before it can tell a
        stock-specific move apart from a market move, so it has nothing to say yet.
      </p>
      <button
        onClick={onWarm}
        disabled={busy}
        className="mt-4 rounded-lg px-3.5 py-2 text-sm font-medium disabled:opacity-60"
        style={{ background: 'var(--series-1)', color: '#fff' }}
      >
        {busy ? 'Fetching a year of prices…' : 'Fetch price history'}
      </button>
      {busy && (
        <p className="mt-2 text-[11px]" style={{ color: 'var(--text-muted)' }}>
          This takes a few seconds — one download, then the gate replays over every day.
        </p>
      )}
    </Card>
  )
}

export function Stock() {
  const { stockId: stockIdParam, isin } = useParams()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()

  const [stockId, setStockId] = useState<number | null>(
    stockIdParam ? Number(stockIdParam) : null,
  )
  const [data, setData] = useState<Overview | null>(null)
  const [prices, setPrices] = useState<PricePoint[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [chartDays, setChartDays] = useState(180)

  const tab = (params.get('tab') as Tab) ?? 'Overview'
  const setTab = (t: Tab) => setParams(t === 'Overview' ? {} : { tab: t }, { replace: true })

  // Arriving by ISIN means the stock is not tracked yet: promote it, then continue
  // by id. Deliberately not done inside the search dropdown -- a multi-second wait
  // belongs on a page that can explain itself.
  useEffect(() => {
    if (stockId != null || !isin) return
    let alive = true
    api.track(isin)
      .then((r) => {
        if (!alive) return
        setStockId(r.stock_id)
        navigate(`/stock/${r.stock_id}`, { replace: true })
      })
      .catch((e) => alive && setError(e.message))
    return () => { alive = false }
  }, [isin, stockId, navigate])

  const load = useCallback(() => {
    if (stockId == null) return
    setError(null)
    api.overview(stockId).then(setData).catch((e) => setError(e.message))
  }, [stockId])

  useEffect(load, [load])

  useEffect(() => {
    if (stockId == null) return
    let alive = true
    api.prices(stockId, chartDays)
      .then((p) => alive && setPrices(p))
      .catch(() => alive && setPrices([]))
    return () => { alive = false }
  }, [stockId, chartDays, data?.history.days])

  const warm = async () => {
    if (stockId == null) return
    setBusy(true)
    try {
      await api.backfill(stockId)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const toggleTrack = async () => {
    if (stockId == null || !data) return
    setBusy(true)
    try {
      if (data.watched) await api.untrack(stockId)
      else if (data.security?.isin) await api.track(data.security.isin)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  if (error) return <ErrorNote error={error} onRetry={load} />
  if (stockId == null || !data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-72 w-full" />
      </div>
    )
  }

  const { stock, quote, windows, range, history, gate_result: gate, holding } = data
  const dir = quote.change_pct == null ? 'flat' : quote.change_pct > 0 ? 'up' : quote.change_pct < 0 ? 'down' : 'flat'
  const moneyColour = dir === 'up' ? 'var(--up)' : dir === 'down' ? 'var(--down)' : 'var(--text-muted)'

  return (
    <>
      {/* ---- Header: identity, price, windows ---- */}
      <header className="mb-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">
                {stock.ticker_nse ?? stock.name}
              </h1>
              <OutcomeChip outcome={gate} />
            </div>
            <p className="mt-0.5 text-sm" style={{ color: 'var(--text-muted)' }}>
              {stock.name}
              {data.security?.exchanges && ` · ${data.security.exchanges}`}
              {stock.sector && ` · ${stock.sector.replace(/_/g, ' ').toLowerCase()}`}
            </p>
          </div>

          <button
            onClick={toggleTrack}
            disabled={busy}
            className="rounded-lg px-3.5 py-2 text-sm font-medium disabled:opacity-60"
            style={
              data.watched
                ? { border: '1px solid var(--border)', color: 'var(--text-secondary)' }
                : { background: 'var(--series-1)', color: '#fff' }
            }
          >
            {data.watched ? 'Tracking' : 'Track'}
          </button>
        </div>

        <div className="mt-4 flex flex-wrap items-end gap-x-8 gap-y-3">
          <div>
            <div className="tnum text-3xl font-semibold tracking-tight">
              {money(quote.price, true)}
            </div>
            <div className="tnum mt-0.5 text-sm font-medium" style={{ color: moneyColour }}>
              {signedMoney(quote.change)} ({signedPct(quote.change_pct)})
            </div>
          </div>
          <WindowStrip windows={windows} />
        </div>

        {/* Provenance, always. A delayed scrape must never read as a live tick. */}
        <p className="mt-2 text-[11px]" style={{ color: 'var(--text-muted)' }}>
          {quote.disclaimer ?? 'Delayed price.'}
          {quote.source && quote.source !== 'none' && ` Source: ${quote.source}.`}
          {quote.stale && ' Cached — the last refresh failed.'}
        </p>
      </header>

      {/* ---- Tabs ---- */}
      <div className="mb-5 flex gap-1 overflow-x-auto" role="tablist">
        {TABS.map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className="shrink-0 rounded-lg px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors"
            style={{
              background: tab === t
                ? 'color-mix(in srgb, var(--text-primary) 8%, transparent)' : 'transparent',
              color: tab === t ? 'var(--text-primary)' : 'var(--text-muted)',
            }}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === 'Overview' && (
        <div className="space-y-4">
          {!history.warm && (
            <WarmingNotice history={history} busy={busy} onWarm={warm} />
          )}

          <Card>
            <CardTitle
              aside={
                <div className="flex gap-1">
                  {CHART_RANGES.map(([label, days]) => (
                    <button
                      key={label}
                      onClick={() => setChartDays(days)}
                      className="rounded px-2 py-0.5 text-[11px] font-medium"
                      style={{
                        background: chartDays === days
                          ? 'color-mix(in srgb, var(--text-primary) 8%, transparent)' : 'transparent',
                        color: chartDays === days ? 'var(--text-primary)' : 'var(--text-muted)',
                      }}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              }
            >
              Price
            </CardTitle>
            <LineChart
              data={prices.map((p) => ({ date: p.date, value: p.close }))}
              height={260}
              label={`${stock.ticker_nse ?? stock.name} close`}
              color={dir === 'down' ? 'var(--down)' : 'var(--series-1)'}
            />
            <div className="mt-4">
              <RangeBar range={range} />
            </div>
          </Card>

          <div className="grid gap-4 sm:grid-cols-2">
            <Card>
              <CardTitle>Today</CardTitle>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
                {([
                  ['Open', money(quote.open, true)],
                  ['High', money(quote.high, true)],
                  ['Low', money(quote.low, true)],
                  ['Previous close', money(quote.prev_close, true)],
                ] as Array<[string, string]>).map(([k, v]) => (
                  <div key={k}>
                    <dt className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{k}</dt>
                    <dd className="tnum mt-0.5 text-sm font-medium">{v}</dd>
                  </div>
                ))}
              </dl>
            </Card>

            {holding ? (
              <Card>
                <CardTitle>Your position</CardTitle>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
                  {([
                    ['Quantity', String(holding.qty)],
                    ['Average cost', money(holding.avg_cost, true)],
                    ['Invested', money(holding.qty * holding.avg_cost)],
                    ['Current value', quote.price != null ? money(holding.qty * quote.price) : '—'],
                  ] as Array<[string, string]>).map(([k, v]) => (
                    <div key={k}>
                      <dt className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{k}</dt>
                      <dd className="tnum mt-0.5 text-sm font-medium">{v}</dd>
                    </div>
                  ))}
                </dl>
              </Card>
            ) : (
              <Card>
                <CardTitle>Coverage</CardTitle>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
                  {([
                    ['Price history', `${history.days} days`],
                    ['From', history.first_date ? longDate(history.first_date) : '—'],
                    ['Latest close', history.last_date ? longDate(history.last_date) : '—'],
                    ['Band position', pct(range.band_position, 0)],
                  ] as Array<[string, string]>).map(([k, v]) => (
                    <div key={k}>
                      <dt className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{k}</dt>
                      <dd className="mt-0.5 text-sm font-medium">{v}</dd>
                    </div>
                  ))}
                </dl>
              </Card>
            )}
          </div>
        </div>
      )}

      {tab === 'Fundamentals' && <Fundamentals stockId={stockId} />}
      {tab === 'Shareholding' && <Shareholding stockId={stockId} />}
      {tab === 'Why it moved' && (
        <Explanation stockId={stockId} gateResult={gate} gateDate={data.gate_date} />
      )}
    </>
  )
}
