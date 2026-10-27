import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api, type StockRow } from '../lib/api'
import { money, signedPct } from '../lib/format'
import { PageHeader } from '../components/Shell'
import { Sparkline } from '../components/charts/Sparkline'
import { Icon } from '../components/Icon'

const SHORTCUTS = { IN: ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY'], US: ['AAPL', 'MSFT', 'NVDA', 'AMZN'] }
export function Home({ market = 'IN' }: { market?: 'IN' | 'US' }) {
  const us = market === 'US'
  const location = useLocation()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [browse, setBrowse] = useState(false)
  const [exchange, setExchange] = useState('ALL')
  const [offset, setOffset] = useState(0)
  const [rows, setRows] = useState<StockRow[]>([])
  const requested = useRef(new Set<number>())
  const [featured, setFeatured] = useState<StockRow[]>([])
  const [featuredLoading, setFeaturedLoading] = useState(true)
  const [featuredError, setFeaturedError] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const [busy, setBusy] = useState<number | null>(null)
  const exploring = browse || !!query.trim() || filter !== 'all' || exchange !== 'ALL'
  useEffect(() => { setQuery(new URLSearchParams(location.search).get('query') ?? ''); setOffset(0) }, [location.search])
  useEffect(() => {
    let active = true
    setFeaturedLoading(true)
    Promise.allSettled(SHORTCUTS[market].map(symbol => api.stocks(symbol, 'all', 'ALL', 0, market).then(rows => rows.find(s => s.symbol === symbol)))).then(results => {
      if (!active) return
      setFeatured(results.flatMap(r => r.status === 'fulfilled' && r.value ? [r.value] : []))
      setFeaturedError(results.some(r => r.status === 'rejected') ? 'Some companies could not be loaded.' : '')
      setFeaturedLoading(false)
    })
    return () => { active = false }
  }, [market, revision])
  useEffect(() => {
    for (const stock of featured) {
      if (requested.current.has(stock.stock_id)) continue
      requested.current.add(stock.stock_id)
      void api.refreshStock(stock.stock_id).catch(() => {})
    }
  }, [featured])
  useEffect(() => {
    if (!exploring) return
    let active = true
    setLoading(true)
    const timer = setTimeout(() => { api.stocks(query, filter, exchange, offset, market).then(data => { if (active) { setRows(data); setError('') } }).catch(e => { if (active) setError(e.message) }).finally(() => { if (active) setLoading(false) }) }, 250)
    return () => { active = false; clearTimeout(timer) }
  }, [query, filter, exchange, offset, revision, exploring, market])
  useEffect(() => {
    const update = () => setRevision(n => n + 1)
    window.addEventListener('moneyfest-data-updated', update)
    const timer = setInterval(update, 30000)
    return () => { clearInterval(timer); window.removeEventListener('moneyfest-data-updated', update) }
  }, [])
  function reset() { setQuery(''); setFilter('all'); setBrowse(false); setOffset(0); setExchange('ALL') }
  async function watch(s: StockRow) {
    setBusy(s.stock_id)
    try { if (s.watched) await api.unwatch(s.stock_id); else await api.watch(s.stock_id); setRevision(n => n + 1) }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not update watchlist.') }
    finally { setBusy(null) }
  }
  const sectors = us ? [['Technology', 'Technology', 'technology'], ['Financials', 'Financials', 'funds'], ['Healthcare', 'Healthcare', 'health'], ['Energy', 'Energy', 'bolt']] : [['Banking', 'Bank', 'funds'], ['IT & technology', 'Technology', 'technology'], ['Energy', 'Energy', 'bolt'], ['Pharma', 'Pharma', 'health']]
  return <>{!us && <PageHeader title="Explore stocks" aside={<span className="market-caption"><span className="country-dot india-dot" />India · INR</span>} />}
    <div className="stock-explore-layout"><div className="stock-explore-main">
      <div className="explore-toolbar"><label className="search-field"><Icon name="search" size={22} /><input aria-label="Search stocks" placeholder={us ? 'Search US companies or symbols' : 'Search any company or stock'} maxLength={100} value={query} onChange={e => { setQuery(e.target.value); setOffset(0) }} />{query && <button aria-label="Clear search" onClick={() => { setQuery(''); setOffset(0) }}>×</button>}</label><details className="filter-dropdown"><summary><Icon name="filter" size={18} /><span>Filters</span></summary><select className="exchange-select" aria-label="Exchange" value={exchange} onChange={e => { setExchange(e.target.value); setOffset(0) }}><option value="ALL">All exchanges</option>{us ? <><option>NASDAQ</option><option>NYSE</option><option>AMEX</option><option>ARCA</option><option>BATS</option><option>IEX</option></> : <><option value="NSE">NSE</option><option value="BSE">BSE</option></>}</select></details></div>
      <div className="stock-view-tabs" role="group" aria-label="Filter">{[['all', 'Explore'], ['watched', 'Watchlist'], ['held', 'Holdings']].map(([value, label]) => <button key={value} aria-pressed={filter === value} onClick={() => { reset(); setFilter(value) }}><Icon name={value === 'all' ? 'compass' : value === 'watched' ? 'star' : 'portfolio'} size={18} />{label}</button>)}</div>
      {error && <p role="alert" className="status-note">{error} <button onClick={() => setRevision(n => n + 1)}>Retry</button></p>}
      {!exploring && <>
        <div className="feature-section-heading"><h2>Companies to explore</h2><button className="text-link" onClick={() => setBrowse(true)}>View all <Icon name="arrow" size={16} /></button></div>
        <div className="company-card-grid" aria-busy={featuredLoading}>{featuredLoading && !featured.length ? SHORTCUTS[market].map(symbol => <div key={symbol} className="company-card company-skeleton"><span /><strong>{symbol}</strong><small>Loading company…</small></div>) : featured.map(s => <CompanyCard key={s.stock_id} stock={s} busy={busy === s.stock_id} onOpen={() => navigate(`/stock-research?stockId=${s.stock_id}`)} onWatch={() => void watch(s)} />)}</div>
        {featuredError && <p className="status-note">{featuredError} <button onClick={() => setRevision(n => n + 1)}>Retry</button></p>}
        {!featuredLoading && !featured.length && <div className="empty-state"><h3>Your next company starts with a search</h3><p>Search above or open the full stock catalog.</p><button className="secondary-button" onClick={() => setBrowse(true)}>Browse stocks</button></div>}
        <div className="feature-section-heading"><h2>Explore by sector</h2></div>
        <div className="sector-tiles">{sectors.map(([label, term, icon], i) => <button className={`sector-tile sector-${i}`} key={label} onClick={() => { setQuery(term); setOffset(0) }}><span><Icon name={icon} size={26} /></span><strong>{label}</strong><Icon name="arrow" size={17} /></button>)}</div>
        <div className="explore-next"><Link to="/stock-research"><span className="next-icon"><Icon name="search" size={24} /></span><span><strong>Go deeper on a stock</strong><small>Price direction, news & a trade planner</small></span><Icon name="arrow" /></Link><Link to="/portfolio-lab"><span className="next-icon"><Icon name="portfolio" size={24} /></span><span><strong>Build your portfolio</strong><small>Pick stocks. Compare your allocation.</small></span><Icon name="arrow" /></Link></div>
      </>}
      {exploring && <section className="card stock-table" aria-busy={loading}><header className="section-heading"><div><h2>{query ? `Results for “${query}”` : filter === 'watched' ? 'Your watchlist' : filter === 'held' ? 'Your holdings' : 'All stocks'}</h2><p className="data-caption">Saved closing prices</p></div><button className="text-link" onClick={reset}>Explore</button></header>
        {loading ? <div className="empty-state" role="status">Finding stocks…</div> : !rows.length ? <div className="empty-state"><span className="empty-icon"><Icon name={filter === 'watched' ? 'star' : 'search'} size={30} /></span><h3>{filter === 'watched' ? 'Make it your watchlist' : filter === 'held' ? 'Your holdings will appear here' : 'No stocks found'}</h3><p>{filter === 'watched' ? 'Tap the star on any company to follow it here.' : filter === 'held' ? 'Record a holding from your portfolio.' : 'Try a different company name or symbol.'}</p>{filter !== 'all' && <button className="secondary-button" onClick={reset}>Explore companies</button>}</div> : rows.slice(0, 40).map(s => <article key={s.stock_id} className="stock-table-row"><button className="stock-identity" onClick={() => navigate(`/stock-research?stockId=${s.stock_id}`)}><ListingCode stock={s} /><span className="stock-name"><strong>{s.symbol ?? s.ticker}{s.held && <span className="held-label">Held</span>}</strong><span>{s.name}</span><small>{s.exchange}</small></span></button><div className="stock-price"><strong>{money(s.close, true, s.currency)}</strong><span className="stock-change" style={{color: s.change_pct == null ? 'var(--text-muted)' : s.change_pct >= 0 ? 'var(--up)' : 'var(--down)'}}>{signedPct(s.change_pct)}</span><small>{s.date ?? 'Price pending'}</small></div><button className={`watch-button ${s.watched ? 'watched' : ''}`} disabled={busy === s.stock_id} aria-label={`${s.watched ? 'Remove from' : 'Add to'} watchlist: ${s.ticker}`} aria-pressed={s.watched} onClick={() => void watch(s)}><Icon name="star" size={21} /></button></article>)}
        {!loading && (offset > 0 || rows.length > 40) && <div className="pagination"><button className="secondary-button" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 40))}>Previous</button><span>Page {offset / 40 + 1}</span><button className="secondary-button" disabled={rows.length <= 40} onClick={() => setOffset(offset + 40)}>Next</button></div>}
      </section>}
      <p className="app-footnote">{us ? 'Nasdaq Trader' : 'Upstox'} catalog · Closing data, not live quotes.</p>
    </div><aside className="explore-sidekick"><h2>Watchlist</h2><p>The companies you choose to follow, collected in one place.</p><button className="action-button" onClick={() => { reset(); setFilter('watched') }}>Open watchlist <Icon name="arrow" size={17} /></button><div className="sidekick-divider" /><Link to={us ? '/home' : '/us-stocks'}><Icon name="globe" size={24} /><span><strong>{us ? 'Indian stocks' : 'Explore US stocks'}</strong><small>{us ? 'NSE & BSE · INR' : 'US companies · USD'}</small></span><Icon name="arrow" size={17} /></Link></aside></div>
  </>
}
function ListingCode({ stock }: { stock: StockRow }) { return <span className="listing-code">{stock.exchange}</span> }

function CompanyCard({ stock, busy, onOpen, onWatch }: { stock: StockRow; busy: boolean; onOpen: () => void; onWatch: () => void }) {
  const [values, setValues] = useState<number[]>([])
  useEffect(() => { let active = true; api.prices(stock.stock_id, 30).then(points => { if (active) setValues(points.map(p => p.close)) }).catch(() => {}); return () => { active = false } }, [stock.stock_id, stock.date])
  return <article className="company-card"><button className={`watch-button ${stock.watched ? 'watched' : ''}`} aria-label={`${stock.watched ? 'Remove from' : 'Add to'} watchlist: ${stock.ticker}`} aria-pressed={stock.watched} disabled={busy} onClick={onWatch}><Icon name="star" size={20} /></button><button className="company-card-open" onClick={onOpen}><strong>{stock.symbol ?? stock.ticker}</strong><span className="company-card-name">{stock.name}</span><div className="company-chart">{values.length > 1 ? <Sparkline values={values} width={150} height={48} direction={stock.change_pct == null ? 'flat' : stock.change_pct >= 0 ? 'up' : 'down'} /> : <span>History not available</span>}</div><span className="company-card-price">{money(stock.close, true, stock.currency)}</span><span className="company-card-change" style={{color: stock.change_pct == null ? 'var(--text-muted)' : stock.change_pct >= 0 ? 'var(--up)' : 'var(--down)'}}>{stock.change_pct == null ? 'Price pending' : signedPct(stock.change_pct)} <small>{stock.change_pct != null ? 'last close' : ''}</small></span></button></article>
}
