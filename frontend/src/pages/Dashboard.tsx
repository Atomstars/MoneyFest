import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type PortfolioSummary, type AllocationSlice, type HistoryPoint, type Position, type FundPortfolio, type Currency } from '../lib/api'
import { money, signedMoney, signedPct, longDate } from '../lib/format'
import { LineChart } from '../components/charts/LineChart'
import { DonutChart } from '../components/charts/DonutChart'
import { PositionRow } from '../components/PositionRow'
import { StockPanel } from '../components/StockPanel'
import { Card, CardTitle, ErrorNote, Skeleton } from '../components/ui'
import { PageHeader } from '../components/Shell'
import { HoldingEditor } from '../components/HoldingEditor'
import { Icon } from '../components/Icon'
import { NewsFeed } from '../components/NewsFeed'
import { RefreshButton } from '../components/RefreshButton'

export function Dashboard() {
  const [currency, setCurrency] = useState<Currency>('INR')
  const [pf, setPf] = useState<PortfolioSummary | null>(null)
  const [alloc, setAlloc] = useState<AllocationSlice[]>([])
  const [history, setHistory] = useState<HistoryPoint[]>([])
  const [funds, setFunds] = useState<FundPortfolio | null>(null)
  const [days, setDays] = useState(90)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Position | null>(null)
  const [editing, setEditing] = useState<Position | null | undefined>(undefined)
  const [removing, setRemoving] = useState<string | null>(null)
  const [mutationError, setMutationError] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [query, setQuery] = useState('')
  const [revision, setRevision] = useState(0)
  const load = useCallback(() => setRevision(n => n + 1), [])
  useEffect(() => {
    let active = true
    Promise.all([api.portfolio(currency), api.allocation(currency), api.portfolioHistory(days, currency)])
      .then(([p, a, h]) => { if (active) { setPf(p); setAlloc(a); setHistory(h); setError(null) } })
      .catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [days, revision, currency])
  useEffect(() => { api.fundPortfolio().then(setFunds).catch(() => {}) }, [revision])
  useEffect(() => {
    window.addEventListener('moneyfest-data-updated', load)
    const timer = setInterval(load, 15000)
    return () => { clearInterval(timer); window.removeEventListener('moneyfest-data-updated', load) }
  }, [load])
  async function remove(ticker: string) {
    setDeleting(true); setMutationError('')
    try { await api.deleteHolding(ticker); setRemoving(null); load() }
    catch (e) { setMutationError(e instanceof Error ? e.message : 'Could not remove holding.') }
    finally { setDeleting(false) }
  }
  if (error && !pf) return <ErrorNote error={error} onRetry={load} />
  const positions = pf?.positions.filter(p => `${p.ticker} ${p.name}`.toLowerCase().includes(query.toLowerCase())) ?? []
  const color = (value: number | null | undefined) => value == null ? 'var(--text-muted)' : value >= 0 ? 'var(--up)' : 'var(--down)'
  return <>
    <PageHeader title="Your portfolio" subtitle={pf?.as_of ? `Closing snapshot · ${longDate(pf.as_of)}` : 'Your investments, in perspective'} aside={<><Link className="secondary-button" to="/portfolio-lab"><Icon name="spark" size={18} />Build a plan</Link><RefreshButton /><button className="action-button" onClick={() => setEditing(null)}><Icon name="plus" size={17} />Add holding</button></>} />
    <div className="segmented-nav" aria-label="Portfolio currency">{(['INR', 'USD'] as const).map(c => <button key={c} aria-pressed={currency === c} onClick={() => { setCurrency(c); setPf(null); setAlloc([]); setHistory([]); setEditing(undefined); setSelected(null) }}>{c === 'INR' ? 'India · INR' : 'US · USD'}</button>)}</div><p className="data-caption">Separate currency totals · no FX conversion</p>
    {(error || mutationError) && <p className="status-note" role="alert">{error ?? mutationError}</p>}
    {editing !== undefined && <HoldingEditor currency={currency} key={editing?.stock_id ?? 'new'} position={editing} onCancel={() => setEditing(undefined)} onSaved={() => { setEditing(undefined); load() }} />}
    <div className="portfolio-stats rise">
      <section className="stat-card primary-stat"><span className="stat-label">Portfolio value <Icon name="portfolio" size={17} /></span>{pf ? <><strong className="stat-value">{money(pf.total_value, false, currency)}</strong><span className="stat-detail">{pf.priced_positions} of {pf.positions.length} holdings priced</span></> : <Skeleton className="h-10 w-40" />}</section>
      <section className="stat-card"><span className="stat-label">Total invested <span>{currency === 'USD' ? '$' : '₹'}</span></span><strong className="stat-value">{pf ? money(pf.total_invested, false, currency) : '—'}</strong><span className="stat-detail">Across {pf?.positions.length ?? '—'} holdings</span></section>
      <section className="stat-card"><span className="stat-label">Total return <Icon name="markets" size={17} /></span><strong className="stat-value" style={{ color: color(pf?.total_pnl) }}>{signedMoney(pf?.total_pnl, currency)}</strong><span className="stat-detail" style={{ color: color(pf?.total_pnl_pct) }}>{signedPct(pf?.total_pnl_pct)} <span className="muted">overall</span></span></section>
      <section className="stat-card"><span className="stat-label">Day’s change <Icon name="markets" size={17} /></span><strong className="stat-value" style={{ color: color(pf?.day_change) }}>{signedMoney(pf?.day_change, currency)}</strong><span className="stat-detail" style={{ color: color(pf?.day_change_pct) }}>{signedPct(pf?.day_change_pct)} <span className="muted">last close</span></span></section>
    </div>
    {!!pf?.unpriced_positions && <p className="status-note">{pf.unpriced_positions} holding{pf.unpriced_positions > 1 ? 's' : ''} awaiting a closing price · excluded from value and return totals.</p>}
    <div className="cross-asset-strip"><span className="cross-asset-icon"><Icon name="funds" size={19} /></span><div><strong>Mutual funds</strong><small>{funds?.positions.length ?? '—'} schemes tracked · AMFI daily NAV</small></div><strong>{funds ? money(funds.value) : '—'}</strong><Link className="text-link" to="/funds">Open funds <Icon name="arrow" size={14} /></Link></div>
    <div className="portfolio-detail-grid">
      <section className="card holdings-card"><header className="section-heading"><div className="flex items-center gap-2"><h2>Holdings</h2><span className="count-badge">{pf?.positions.length ?? 0}</span></div><Link to="/home" className="text-link">Explore <Icon name="arrow" size={14} /></Link></header>{!!pf?.positions.length && <div className="holdings-search search-field"><Icon name="search" size={16} /><input aria-label="Search holdings" placeholder="Find a holding…" value={query} onChange={e => setQuery(e.target.value)} /></div>}
        {!pf ? <div className="p-5"><Skeleton className="h-32 w-full" /></div> : !pf.positions.length ? <div className="empty-state"><span className="empty-icon"><Icon name="portfolio" size={28} /></span><h3>No holdings yet.</h3><p>Add your first stock to start tracking.</p><button className="action-button" onClick={() => setEditing(null)}><Icon name="plus" size={16} />Add your first holding</button></div> : !positions.length ? <div className="empty-state"><h3>No matching holdings</h3></div> : <div className="holdings-list">{positions.map(p => <div key={p.stock_id} className="holding-entry"><PositionRow p={p} onOpen={setSelected} /><div className="holding-actions"><button onClick={() => { setEditing(p); window.scrollTo({ top: 0, behavior: 'smooth' }) }}>Edit</button><button onClick={() => setRemoving(p.ticker)} disabled={!!removing}>Remove</button>{removing === p.ticker && <div className="remove-confirm"><span>Remove {p.ticker}?</span><button disabled={deleting} onClick={() => void remove(p.ticker!)}>{deleting ? 'Removing…' : 'Confirm'}</button><button disabled={deleting} onClick={() => setRemoving(null)}>Cancel</button></div>}</div></div>)}</div>}
      </section>
      <NewsFeed compact />
    </div><details className="portfolio-insights"><summary><span><Icon name="markets" size={21} />Performance & allocation</span><span>View charts <Icon name="chevron" size={18} /></span></summary>    <div className="portfolio-charts">
      <Card><CardTitle aside={<div className="segmented" role="group" aria-label="Time range">{[30, 90, 180].map(d => <button key={d} aria-pressed={days === d} onClick={() => setDays(d)}>{d === 30 ? '1M' : d === 90 ? '3M' : '6M'}</button>)}</div>}>Portfolio performance</CardTitle><LineChart currency={currency} data={history} label="Portfolio value" /><p className="data-caption">Current quantities at historical closes · not transaction performance</p></Card>
      <Card><CardTitle aside={<span className="outline-badge">{alloc.length} sectors</span>}>Allocation</CardTitle><DonutChart currency={currency} data={alloc} total={pf?.total_value ?? null} /></Card>
    </div>
    </details><p className="app-footnote">Prices: Yahoo Finance · News: linked publishers · Explanation only, not investment advice</p>
    {selected && <StockPanel position={selected} onClose={() => setSelected(null)} />}
  </>
}
