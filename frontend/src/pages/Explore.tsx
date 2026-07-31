import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type SecurityRow, type StockRow, type UniverseStats } from '../lib/api'
import { croreMoney, count } from '../lib/format'
import { Card, ErrorNote, Skeleton } from '../components/ui'
import { PageHeader, SECTIONS } from '../components/Shell'

type Exchange = 'all' | 'NSE' | 'BSE'

/**
 * The universe browser.
 *
 * Home shows what the engine is already analysing; this shows everything that
 * *exists* -- roughly 5,000 active NSE and BSE listings. The distinction matters
 * because analysing a name is expensive (a price backfill and a gate warm-up) while
 * listing one is free, so the catalogue can be complete without the EOD job growing.
 *
 * With no query typed this shows the tracked names rather than an arbitrary slice of
 * five thousand rows: "here is what you follow, search for anything else" is a more
 * useful empty state than a meaningless alphabetical page one.
 */
function ResultRow({ row, onOpen }: { row: SecurityRow; onOpen: () => void }) {
  return (
    <button
      onClick={onOpen}
      className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-[color-mix(in_srgb,var(--text-primary)_4%,transparent)]"
      style={{ borderBottom: '1px solid var(--border)' }}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="truncate text-sm font-semibold">
            {row.symbol_nse ?? row.scrip_bse}
          </span>
          {row.stock_id && (
            <span
              className="rounded px-1.5 py-px text-[10px] font-medium"
              style={{
                background: 'color-mix(in srgb, var(--series-1) 16%, transparent)',
                color: 'var(--text-secondary)',
              }}
            >
              tracked
            </span>
          )}
        </div>
        <p className="truncate text-xs" style={{ color: 'var(--text-muted)' }}>
          {row.name}
          {row.industry ? ` · ${row.industry}` : ''}
        </p>
      </div>
      <div className="shrink-0 text-right">
        <div className="tnum text-xs font-medium">{croreMoney(row.market_cap ? row.market_cap * 1e7 : null)}</div>
        <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{row.exchanges}</div>
      </div>
    </button>
  )
}

export function Explore() {
  const [query, setQuery] = useState('')
  const [exchange, setExchange] = useState<Exchange>('all')
  const [results, setResults] = useState<SecurityRow[] | null>(null)
  const [tracked, setTracked] = useState<StockRow[] | null>(null)
  const [stats, setStats] = useState<UniverseStats | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [searching, setSearching] = useState(false)
  const navigate = useNavigate()

  const load = () => {
    setError(null)
    api.universeStats().then(setStats).catch((e) => setError(e.message))
    api.stocks().then(setTracked).catch(() => setTracked([]))
  }
  useEffect(load, [])

  useEffect(() => {
    const term = query.trim()
    if (!term) { setResults(null); setSearching(false); return }
    setSearching(true)
    let alive = true
    const timer = setTimeout(() => {
      api.universeSearch(term, exchange === 'all' ? undefined : exchange, 50)
        .then((r) => alive && setResults(r.results))
        .catch((e) => alive && setError(e.message))
        .finally(() => alive && setSearching(false))
    }, 200)
    return () => { alive = false; clearTimeout(timer) }
  }, [query, exchange])

  // The tracked list reuses the same row shape so the two states render identically.
  const trackedRows = useMemo<SecurityRow[]>(
    () => (tracked ?? []).map((s) => ({
      isin: `stock-${s.stock_id}`,
      symbol_nse: s.ticker,
      scrip_bse: null,
      name: s.name,
      industry: s.sector,
      exchanges: 'NSE',
      market_cap: null,
      stock_id: s.stock_id,
    })),
    [tracked],
  )

  if (error) return <ErrorNote error={error} onRetry={load} />

  const showing = results ?? trackedRows
  const isSearch = results !== null

  return (
    <>
      <PageHeader
        title={SECTIONS['/explore'].title}
        subtitle={
          stats
            ? `${count(stats.total)} active listings · ${count(stats.nse)} NSE · ${count(stats.bse)} BSE`
            : SECTIONS['/explore'].subtitle
        }
      />

      <div className="mb-5 flex flex-wrap items-center gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by ticker, company name or BSE scrip code"
          aria-label="Search all listed stocks"
          className="min-w-0 flex-1 rounded-lg px-3 py-2 text-sm outline-none sm:max-w-md"
          style={{
            background: 'var(--surface-1)', border: '1px solid var(--border)',
            color: 'var(--text-primary)',
          }}
        />
        <div className="flex gap-1" role="group" aria-label="Exchange filter">
          {(['all', 'NSE', 'BSE'] as const).map((k) => (
            <button
              key={k}
              onClick={() => setExchange(k)}
              className="rounded-lg px-3 py-2 text-xs font-medium transition-colors"
              style={{
                background: exchange === k
                  ? 'color-mix(in srgb, var(--text-primary) 8%, transparent)' : 'transparent',
                color: exchange === k ? 'var(--text-primary)' : 'var(--text-muted)',
                border: '1px solid var(--border)',
              }}
            >
              {k === 'all' ? 'All' : k}
            </button>
          ))}
        </div>
      </div>

      <Card className="!p-0">
        <div
          className="flex items-center justify-between px-4 py-2.5"
          style={{ borderBottom: '1px solid var(--border)' }}
        >
          <h2 className="text-xs font-semibold tracking-wide uppercase"
              style={{ color: 'var(--text-muted)' }}>
            {isSearch ? `${showing.length} result${showing.length === 1 ? '' : 's'}` : 'Currently tracked'}
          </h2>
          {searching && (
            <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Searching…</span>
          )}
        </div>

        {!tracked && !isSearch ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
          </div>
        ) : showing.length === 0 ? (
          <p className="px-4 py-10 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
            {isSearch
              ? `No active listing matches “${query}”.`
              : 'Nothing tracked yet — search above to add your first stock.'}
          </p>
        ) : (
          showing.map((row) => (
            <ResultRow
              key={row.isin}
              row={row}
              onOpen={() =>
                navigate(row.stock_id ? `/stock/${row.stock_id}` : `/stock/isin/${row.isin}`)
              }
            />
          ))
        )}
      </Card>

      {stats?.synced_at && (
        <p className="mt-3 text-[11px]" style={{ color: 'var(--text-muted)' }}>
          Listings synced {new Date(stats.synced_at).toLocaleDateString('en-IN', {
            day: 'numeric', month: 'short', year: 'numeric',
          })} from the NSE and BSE published lists. Run{' '}
          <code>python -m scripts.sync_universe</code> to refresh.
        </p>
      )}
    </>
  )
}
