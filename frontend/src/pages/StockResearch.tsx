import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, type StockResearch, type Currency } from '../lib/api'
import { money, signedPct } from '../lib/format'
import { PageHeader } from '../components/Shell'
import { StockFinder } from '../components/StockFinder'
import { LineChart } from '../components/charts/LineChart'

export function StockResearchPage() {
  const [params, setParams] = useSearchParams()
  const id = Number(params.get('stockId'))
  const [data, setData] = useState<StockResearch | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const [revision, setRevision] = useState(0)
  const [market, setMarket] = useState('ALL')
  const [view, setView] = useState('overview')
  const [sessions, setSessions] = useState(60)
  useEffect(() => {
    setData(null); setError(''); setNotice(''); setView('overview')
    if (!Number.isInteger(id) || id <= 0) return
    let active = true
    setLoading(true)
    api.stockResearch(id).then(r => { if (active) setData(r) }).catch(e => { if (active) setError(e.message) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [id, revision])
  useEffect(() => {
    if (!id) return
    let active = true
    api.refreshStock(id).then(r => { if (active && !r.enabled) setNotice('Market refresh is disabled on this server.') }).catch(() => {})
    const timer = setInterval(() => { api.stockResearch(id).then(r => { if (active) setData(r) }).catch(() => {}) }, 15000)
    return () => { active = false; clearInterval(timer) }
  }, [id])
  async function refresh() {
    setRefreshing(true); setError('')
    try { const r = await api.refreshStock(id); setNotice(!r.enabled ? 'Market refresh is disabled on this server.' : r.queued ? 'Refresh queued. Prices and headlines update here automatically.' : 'Refresh already queued. Recent data is cached for 15 minutes.') }
    catch (e) { setError(e instanceof Error ? e.message : 'Refresh failed') }
    finally { setRefreshing(false) }
  }
  return <><PageHeader title="Stock research" subtitle="Search a stock · inspect the evidence · plan your risk" aside={<Link className="text-link" to="/portfolio-lab">Portfolio builder →</Link>} />
    <section className="card research-search"><select aria-label="Research market" className="account-input" value={market} onChange={e => setMarket(e.target.value)}><option value="ALL">India & US</option><option value="IN">India</option><option value="US">United States</option></select><StockFinder market={market} initialQuery={params.get('query') ?? ''} label="Search stock research" onSelect={s => setParams({stockId: String(s.stock_id)})} /></section>
    {error && <p role="alert" className="status-note">{error} <button onClick={() => setRevision(n => n + 1)}>Retry</button></p>}
    {notice && <p role="status" className="status-note">{notice}</p>}
    {loading && <p role="status">Loading research…</p>}
    {!id && <div className="empty-state card"><h3>Choose a company to start</h3><p>Search any supported Indian or US stock.</p></div>}
    {data && <><header className="stock-research-heading"><div><span className="eyebrow">{data.stock.exchange} · {data.stock.currency}</span><h2>{data.stock.symbol} <span>{data.stock.name}</span></h2></div><button className="secondary-button" disabled={refreshing} onClick={() => void refresh()}>{refreshing ? 'Queuing…' : 'Refresh prices & news'}</button></header>
      <div className="stock-view-tabs research-view-tabs" role="group" aria-label="Stock details view">{[['overview', 'Overview'], ['news', `News · ${data.news.length}`], ['trade', 'Trade planner']].map(([key, label]) => <button key={key} aria-pressed={view === key} onClick={() => setView(key)}>{label}</button>)}</div>
      {view === 'overview' && <><div className="research-metrics">{[['Last close', money(data.close, true, data.stock.currency)], ['Day change', signedPct(data.change_pct)], ['20-session average', money(data.sma20, true, data.stock.currency)], ['50-session average', money(data.sma50, true, data.stock.currency)]].map(([label, value]) => <section className="stat-card" key={label}><span className="stat-label">{label}</span><strong>{value}</strong></section>)}</div>
      <div className="stock-research-grid research-overview"><section className="card padded-card"><header className="section-heading"><h2>Price direction</h2><span className={`trend-badge trend-${data.trend.toLowerCase()}`}>{({UPTREND: 'Observed uptrend', DOWNTREND: 'Observed downtrend', MIXED: 'Mixed trend', INSUFFICIENT: 'Insufficient data'})[data.trend]}</span></header><div className="segmented chart-periods" aria-label="Price history range">{[[22, '1M'], [60, '3M']].map(([count, label]) => <button key={label} aria-pressed={sessions === count} onClick={() => setSessions(count as number)}>{label}</button>)}</div><LineChart currency={data.stock.currency} data={[...data.bars].slice(0, sessions).reverse().map(b => ({date: b.date, value: b.close}))} label={`${data.stock.symbol} closing price`} /><p className="data-caption">{data.as_of ? `Through ${data.as_of} · ${data.observations} saved sessions` : 'No closing prices yet · refresh this stock'}</p><details className="trend-method"><summary>How is direction calculated?</summary><p className="feed-footnote">Uptrend: close &gt; 20-session average &gt; 50-session average. Downtrend reverses those comparisons. Needs 50 saved sessions; describes past prices, not a forecast.</p></details></section></div></>}
      {data.sync.filter(s => s.status === 'ERROR').map(s => <p key={s.scope} className="status-note" role="status">{s.scope.startsWith('news:') ? 'News' : 'Prices'}: {s.detail} · last successful refresh {s.succeeded_at ? new Date(s.succeeded_at).toLocaleString('en-IN') : 'not available'}</p>)}
      {view === 'trade' && <TradePlanner key={data.stock.id} currency={data.stock.currency} />}
      {view !== 'trade' && <section className="card"><header className="section-heading"><h2>News & possible catalysts</h2><span className="data-caption">Past 7 days · headline tone</span></header>{!data.news.length ? <div className="empty-state"><h3>No recent headlines saved</h3><p>Refresh this stock to check the news feed.</p></div> : data.news.slice(0, view === 'overview' ? 3 : 15).map(n => <article className="news-row" key={n.id}><span className={`sentiment sentiment-${n.sentiment.toLowerCase()}`}>{n.sentiment.toLowerCase()}</span><a className="news-headline" href={/^https:\/\//.test(n.url) ? n.url : undefined} target="_blank" rel="noopener noreferrer">{n.headline} ↗</a><p className="news-source">{n.source} · {new Date(n.published_at).toLocaleString('en-IN', {timeZone: 'Asia/Kolkata'})} IST</p></article>)}{view === 'overview' && data.news.length > 3 && <button className="news-view-all text-link" onClick={() => setView('news')}>View all {data.news.length} headlines →</button>}<p className="feed-footnote">Headline wording is assessed by rules. It neither confirms causation nor predicts the next move.</p></section>}
    </>}
  </>
}

function TradePlanner({ currency }: { currency: Currency }) {
  const [entry, setEntry] = useState('')
  const [stop, setStop] = useState('')
  const [target, setTarget] = useState('')
  const [risk, setRisk] = useState('')
  const e = Number(entry), s = Number(stop), t = Number(target), r = Number(risk)
  const valid = [e, s, t, r].every(Number.isFinite) && e > 0 && s > 0 && s < e && t > e && r > 0
  const qty = valid ? Math.floor(r / (e - s)) : 0
  return <section className="card padded-card trade-planner"><h2>Trade mechanism</h2><details className="order-types"><summary>Understand market, limit & stop orders</summary><div className="order-explainer"><p><strong>Market</strong> executes at the next available price; the price can change.</p><p><strong>Limit</strong> sets your price boundary; execution is not guaranteed.</p><p><strong>Stop</strong> triggers an order; gaps and slippage can increase loss.</p><a href="https://www.investor.gov/introduction-investing/investing-basics/how-stock-markets-work/types-orders" target="_blank" rel="noopener noreferrer" className="text-link">Order types · Investor.gov ↗</a></div></details><h3>Long-position risk calculator · {currency}</h3><div className="trade-inputs">{[['Entry price', entry, setEntry], ['Stop price', stop, setStop], ['Target price', target, setTarget], ['Risk budget', risk, setRisk]].map(([label, value, setter]) => <label key={label as string}>{label as string}<input className="account-input" type="number" min="0.01" step="0.01" value={value as string} onChange={event => (setter as (v: string) => void)(event.target.value)} /></label>)}</div>{valid ? <div className="risk-result" aria-live="polite"><strong>{qty.toLocaleString()} whole shares</strong><span>Position cost {money(qty * e, true, currency)}</span><span>Planned loss {money(qty * (e - s), true, currency)} · reward/risk {((t - e) / (e - s)).toFixed(2)}×</span></div> : <p className="data-caption">Enter stop &lt; entry &lt; target and a positive risk budget.</p>}<p className="feed-footnote">Hypothetical calculation. Excludes fees, FX, taxes and slippage; a stop cannot guarantee the loss amount. No orders are placed.</p></section>
}
