import { useCallback, useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api, type Fund, type FundDiscovery, type RankedFund, type FundPortfolio } from '../lib/api'
import { money, signedMoney } from '../lib/format'
import { PageHeader } from '../components/Shell'
import { Icon } from '../components/Icon'

const fundGroups = [['', 'All'], ['large', 'Large cap'], ['mid', 'Mid cap'], ['small', 'Small cap'], ['flexi', 'Flexi cap'], ['large-mid', 'Large & mid cap'], ['multi', 'Multi cap'], ['index', 'Index'], ['elss', 'ELSS'], ['debt', 'Debt'], ['hybrid', 'Hybrid'], ['sector', 'Sectoral'], ['other', 'Other']]
const navMoney = (n: number | null) => n == null ? 'Awaiting NAV' : `₹${n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`
export function Funds() {
  const location = useLocation()
  const [tab, setTab] = useState('discover')
  const [portfolio, setPortfolio] = useState<FundPortfolio | null>(null)
  const [rows, setRows] = useState<RankedFund[]>([])
  const [discovery, setDiscovery] = useState<FundDiscovery | null>(null)
  const [period, setPeriod] = useState(3)
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('')
  const [offset, setOffset] = useState(0)
  const [more, setMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<Fund | null>(null)
  const [units, setUnits] = useState('')
  const [cost, setCost] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [revision, setRevision] = useState(0)
  const refresh = useCallback(() => setRevision(x => x + 1), [])
  useEffect(() => {
    if (tab !== 'discover' || discovery?.sync[0]?.status === 'OK') return
    const timer = setInterval(refresh, discovery?.sync[0]?.status === 'ERROR' ? 60000 : 15000)
    return () => clearInterval(timer)
  }, [tab, discovery?.sync, refresh])
  useEffect(() => { setQuery(new URLSearchParams(location.search).get('query') ?? ''); setOffset(0) }, [location.search])
  useEffect(() => { api.fundPortfolio().then(setPortfolio).catch(e => setError(e.message)) }, [revision])
  useEffect(() => {
    let active = true
    setLoading(true)
    const timer = setTimeout(() => { api.discoverFunds(query, category, period, offset).then(data => { if (active) { setDiscovery(data); setRows(data.items); setMore(data.has_more); setError('') } }).catch(e => { if (active) { setRows([]); setError(e.message) } }).finally(() => { if (active) setLoading(false) }) }, 250)
    return () => { active = false; clearTimeout(timer) }
  }, [query, category, period, offset, revision])
  function open(fund: Fund) {
    const holding = portfolio?.positions.find(p => p.code === fund.code)
    setSelected(fund); setUnits(holding ? String(holding.units) : ''); setCost(holding ? String(holding.avg_nav) : ''); setError('')
  }
  async function save() {
    if (!selected || !Number.isFinite(Number(units)) || Number(units) <= 0 || !Number.isFinite(Number(cost)) || Number(cost) < 0 || cost === '') { setError('Enter valid units and average purchase NAV.'); return }
    setSaving(true); setError('')
    try { await api.putFund(selected.code, Number(units), Number(cost)); setSelected(null); refresh() }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not save fund.') }
    finally { setSaving(false) }
  }
  async function remove(code: string) {
    try { await api.deleteFund(code); refresh() } catch (e) { setError(e instanceof Error ? e.message : 'Could not remove fund.') }
  }
  return <>
    <PageHeader title="Mutual funds" subtitle="Find funds by category. Compare their long-term performance." aside={<span className="outline-badge">AMFI daily NAV</span>} />
    {error && <p className="status-note" role="alert">{error}</p>}
    <div className="segmented-nav" role="group" aria-label="Fund workspace"><button aria-pressed={tab === 'discover'} onClick={() => setTab('discover')}>Discover funds</button><button aria-pressed={tab === 'holdings'} onClick={() => setTab('holdings')}>My funds · {portfolio?.positions.length ?? 0}</button></div>
    {tab === 'holdings' && <><div className="portfolio-stats fund-stats">
      <section className="stat-card primary-stat"><span className="stat-label">Fund value</span><strong className="stat-value">{portfolio ? money(portfolio.value) : '—'}</strong><span className="stat-detail">Latest available NAV per scheme</span></section>
      <section className="stat-card"><span className="stat-label">Invested</span><strong className="stat-value">{portfolio ? money(portfolio.invested) : '—'}</strong><span className="stat-detail">Cost basis entered by you</span></section>
      <section className="stat-card"><span className="stat-label">Return</span><strong className="stat-value" style={{ color: (portfolio?.pnl ?? 0) >= 0 ? 'var(--up)' : 'var(--down)' }}>{portfolio ? signedMoney(portfolio.pnl) : '—'}</strong><span className="stat-detail">NAV less cost basis</span></section>
      <section className="stat-card"><span className="stat-label">Schemes</span><strong className="stat-value">{portfolio?.positions.length ?? '—'}</strong><span className="stat-detail">{portfolio?.unpriced ?? 0} awaiting NAV</span></section>
    </div>
    {portfolio?.sync[0]?.status === 'ERROR' && <p className="status-note">AMFI refresh is unavailable. Saved NAV is shown.</p>}
    <section className="card fund-held"><header className="section-heading"><h2>Your funds</h2><span className="count-badge">{portfolio?.positions.length ?? 0}</span></header>
      {!portfolio?.positions.length ? <div className="empty-state"><span className="empty-icon"><Icon name="funds" size={28} /></span><h3>No funds tracked</h3><p>Choose Discover funds to find a scheme and add your units.</p></div> : <div className="fund-list">{portfolio.positions.map(p => <div className="fund-row" key={p.code}><div className="fund-row-main"><strong>{p.name}</strong><span>{p.plan} · {p.option_name} · {p.category}</span><small>{p.units.toLocaleString('en-IN')} units · NAV {navMoney(p.nav)} · {p.date ?? 'Date pending'}</small></div><div className="fund-row-value"><strong>{money(p.value)}</strong><small>{signedMoney(p.value == null ? null : p.value - p.invested)}</small><button onClick={() => void remove(p.code)} aria-label={`Remove ${p.name}`}>Remove</button></div></div>)}</div>}
    </section>
    </>}
    {tab === 'discover' && <>
    <section className="fund-discovery">
      <div className="fund-discovery-heading"><div><span className="eyebrow">FUND EXPLORER</span><h2>Start with a category.</h2><p>Top historical returns, with the same plan and time period.</p></div><span className="outline-badge">Direct plan · Growth</span></div>
      <div className="fund-category-tabs" role="group" aria-label="Fund categories">{fundGroups.map(([id, label]) => <button key={id} aria-pressed={category === id} onClick={() => { setCategory(id); setOffset(0) }}>{label}</button>)}</div>
      <div className="fund-ranking-controls"><label className="search-field"><Icon name="search" size={16} /><input aria-label="Search mutual funds" placeholder="Search fund or fund house" maxLength={100} value={query} onChange={e => { setQuery(e.target.value); setOffset(0) }} />{query && <button aria-label="Clear fund search" onClick={() => { setQuery(''); setOffset(0) }}>×</button>}</label><div className="fund-return-picker"><span>Rank by returns</span><div role="group" aria-label="Return period">{[1,3].map(year => <button key={year} aria-pressed={period === year} onClick={() => { setPeriod(year); setOffset(0) }}>{year}Y</button>)}</div></div></div>
      <section className="card fund-ranking-list" aria-busy={loading}>
        <header className="fund-ranking-header"><div><h3>{fundGroups.find(([id]) => id === category)?.[1]} funds</h3><p>{loading ? 'Updating results…' : `${discovery?.summary.ranked ?? 0} ranked · ${discovery?.summary.total ?? 0} schemes`}</p></div><strong>{period}Y {period === 1 ? 'return' : 'annualised'} <span aria-hidden="true">↓</span><small>Highest first</small></strong></header>
        {discovery?.sync[0]?.status === 'ERROR' && <p className="status-note">Return refresh is unavailable. Current verified returns are retained; schemes without verified history remain unranked.</p>}
        {discovery?.sync[0]?.status === 'UPDATING' && <p className="status-note" role="status">Updating historical returns from AMFI… This list refreshes automatically.</p>}
        {!discovery?.sync.length && !loading && <p className="status-note">Historical returns are being prepared. Schemes without verified history remain unranked.</p>}
        {loading ? <div className="empty-state" role="status">Comparing funds…</div> : rows.length ? <div className="fund-list">{rows.map((f, index) => {
          const result = period === 1 ? f.return_1y : f.return_3y
          const groupName = fundGroups.find(([id]) => id === f.group_id)?.[1] ?? 'Other'
          return <button className="fund-result fund-ranked-result" key={f.code} onClick={() => open(f)}>
            <span className="fund-rank">{result == null ? '—' : String(offset + index + 1).padStart(2, '0')}</span>
            <span className="fund-row-main"><strong>{f.name}</strong><span>{groupName} · Direct · Growth{f.held ? ' · Tracked' : ''}</span><small>NAV {navMoney(f.nav)} · {f.date ?? 'Date pending'}</small></span>
            <span className="fund-return-value" style={{ color: result == null ? 'var(--text-muted)' : result >= 0 ? 'var(--up)' : 'var(--down)' }}><strong>{result == null ? '—' : `${result > 0 ? '+' : ''}${result.toFixed(2)}%`}</strong><small>{result == null ? 'History unavailable' : period === 1 ? 'Absolute return' : 'per year'}</small></span><span className="fund-track-action">{f.held ? 'Edit' : 'Track'} <Icon name="plus" size={14} /></span>
          </button>
        })}</div> : <div className="empty-state"><h3>{query ? 'No matching funds' : 'No schemes available yet'}</h3><p>{query ? 'Try a fund house or clear your search.' : 'Funds appear after the AMFI catalog refresh.'}</p>{query && <button className="secondary-button" onClick={() => { setQuery(''); setOffset(0) }}>Clear search</button>}</div>}
        {!loading && <div className="pagination"><span>Showing {rows.length ? offset + 1 : 0}–{offset + rows.length}</span><div><button className="secondary-button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 40))}>Previous</button> <button className="secondary-button" disabled={!more} onClick={() => setOffset(offset + 40)}>Next</button></div></div>}
      </section>
      <p className="fund-methodology">{period === 1 ? '1-year returns are absolute.' : `${period}-year returns are annualised (CAGR).`} Calculated from AMFI NAV; latest NAV {discovery?.summary.as_of ?? 'pending'}. {discovery && discovery.summary.total > discovery.summary.ranked ? `${discovery.summary.total - discovery.summary.ranked} schemes lack verified history for this period and appear last, unranked.` : ''} Regular and IDCW plans are excluded for a consistent comparison.</p>
    </section></>}
    <p className="app-footnote">AMFI NAV is published after market close. Past returns do not predict future performance.</p>
    {selected && <div className="fund-overlay" role="presentation" onMouseDown={e => { if (e.target === e.currentTarget) setSelected(null) }}><section className="fund-dialog card" role="dialog" aria-modal="true" aria-labelledby="fund-dialog-title"><div className="section-heading"><div><h2 id="fund-dialog-title">Track fund</h2><p className="data-caption">{selected.name} · {selected.plan} · {selected.option_name}</p></div><button aria-label="Close" onClick={() => setSelected(null)}>×</button></div><div className="fund-dialog-body"><p>Latest NAV <strong>{navMoney(selected.nav)}</strong> <span className="muted">{selected.date}</span></p><label>Units<input className="account-input" type="number" min="0.000001" step="any" value={units} onChange={e => setUnits(e.target.value)} placeholder="e.g. 24.5" /></label><label>Average purchase NAV<input className="account-input" type="number" min="0" step="any" value={cost} onChange={e => setCost(e.target.value)} placeholder="e.g. 125.40" /></label><button className="action-button" disabled={saving} onClick={() => void save()}>{saving ? 'Saving…' : 'Save to portfolio'}</button></div></section></div>}
  </>
}
