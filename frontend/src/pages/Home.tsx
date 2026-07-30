import { useEffect, useMemo, useState } from 'react'
import { api, type StockRow } from '../lib/api'
import { money, signedPct, longDate, OUTCOME_HELP } from '../lib/format'
import { Sparkline } from '../components/charts/Sparkline'
import { Card, ErrorNote, OutcomeChip, Skeleton } from '../components/ui'
import { PageHeader, SECTIONS } from '../components/Shell'

type Filter = 'all' | 'held' | 'moved'

function StockCard({ s }: { s: StockRow }) {
  const [spark, setSpark] = useState<number[]>([])

  useEffect(() => {
    let alive = true
    api.prices(s.stock_id, 30)
      .then((r) => alive && setSpark(r.map((x) => x.close)))
      .catch(() => { /* decorative only */ })
    return () => { alive = false }
  }, [s.stock_id])

  const dir = s.change_pct == null ? 'flat' : s.change_pct > 0 ? 'up' : s.change_pct < 0 ? 'down' : 'flat'

  return (
    <article className="card flex flex-col gap-3 p-4 transition-transform hover:-translate-y-0.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <h3 className="truncate text-sm font-semibold">{s.ticker ?? s.name}</h3>
            {s.held && (
              <span
                className="rounded px-1.5 py-px text-[10px] font-medium"
                style={{ background: 'color-mix(in srgb, var(--series-1) 16%, transparent)',
                         color: 'var(--text-secondary)' }}
              >
                held
              </span>
            )}
          </div>
          <p className="truncate text-xs" style={{ color: 'var(--text-muted)' }}>{s.name}</p>
        </div>
        <OutcomeChip outcome={s.gate_result} />
      </div>

      <div className="flex items-end justify-between gap-2">
        <div>
          <div className="tnum text-lg font-semibold">{money(s.close, true)}</div>
          <div
            className="tnum text-xs font-medium"
            style={{ color: dir === 'up' ? 'var(--up)' : dir === 'down' ? 'var(--down)' : 'var(--text-muted)' }}
          >
            {signedPct(s.change_pct)}
          </div>
        </div>
        <Sparkline values={spark} direction={dir} width={84} height={34} />
      </div>

      {s.gate_result && (
        <p className="text-[11px] leading-snug" style={{ color: 'var(--text-muted)' }}>
          {OUTCOME_HELP[s.gate_result] ?? ''}
        </p>
      )}
    </article>
  )
}

export function Home() {
  const [rows, setRows] = useState<StockRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<Filter>('all')
  const [q, setQ] = useState('')

  const load = () => {
    setError(null)
    api.stocks().then(setRows).catch((e) => setError(e.message))
  }
  useEffect(load, [])

  const shown = useMemo(() => {
    if (!rows) return []
    const term = q.trim().toLowerCase()
    return rows.filter((s) => {
      if (filter === 'held' && !s.held) return false
      // "Moved" means the gate found something beyond ordinary noise.
      if (filter === 'moved' && (!s.gate_result || ['NOISE', 'WARMING_UP'].includes(s.gate_result)))
        return false
      if (!term) return true
      return `${s.ticker ?? ''} ${s.name} ${s.sector ?? ''}`.toLowerCase().includes(term)
    })
  }, [rows, filter, q])

  if (error) return <ErrorNote error={error} onRetry={load} />

  const asOf = rows?.find((r) => r.date)?.date ?? null

  return (
    <>
      <PageHeader
        title={SECTIONS['/home'].title}
        subtitle={asOf ? `Closing prices — ${longDate(asOf)}` : SECTIONS['/home'].subtitle}
      />

      <div className="mb-5 flex flex-wrap items-center gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search ticker, name or sector"
          aria-label="Search stocks"
          className="min-w-0 flex-1 rounded-lg px-3 py-2 text-sm outline-none sm:max-w-xs"
          style={{ background: 'var(--surface-1)', border: '1px solid var(--border)',
                   color: 'var(--text-primary)' }}
        />
        <div className="flex gap-1" role="group" aria-label="Filter">
          {([['all', 'All'], ['held', 'Holdings'], ['moved', 'Moved']] as const).map(([k, label]) => (
            <button
              key={k}
              onClick={() => setFilter(k)}
              className="rounded-lg px-3 py-2 text-xs font-medium transition-colors"
              style={{
                background: filter === k
                  ? 'color-mix(in srgb, var(--text-primary) 8%, transparent)' : 'transparent',
                color: filter === k ? 'var(--text-primary)' : 'var(--text-muted)',
                border: '1px solid var(--border)',
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {!rows ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-36 w-full" />)}
        </div>
      ) : shown.length === 0 ? (
        <Card>
          <p className="py-8 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
            {q || filter !== 'all' ? 'Nothing matches that filter.' : 'No stocks tracked yet.'}
          </p>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {shown.map((s) => <StockCard key={s.stock_id} s={s} />)}
        </div>
      )}
    </>
  )
}
