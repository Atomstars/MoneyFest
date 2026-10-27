import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api, type NewsItem } from '../lib/api'
import { PageHeader } from '../components/Shell'
import { Home } from './Home'

export function USStocks() {
  const { search } = useLocation()
  useEffect(() => { if (new URLSearchParams(search).has('query')) setTab('stocks') }, [search])
  const [tab, setTab] = useState('stocks')
  const [news, setNews] = useState<NewsItem[]>([])
  const [busy, setBusy] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    if (tab !== 'news') return
    let active = true
    async function load() {
      setBusy(true)
      try { const r = await api.marketNews(); if (active) { setNews(r.items); setRefreshing(r.refreshing); setError('') } }
      catch (e) { if (active) setError(e instanceof Error ? e.message : 'News unavailable') }
      finally { if (active) setBusy(false) }
    }
    void load(); const timer = setInterval(() => void load(), 30000)
    return () => { active = false; clearInterval(timer) }
  }, [tab])
  return <><PageHeader title="US stocks" aside={<span className="market-caption"><span className="country-dot us-dot" />United States · USD</span>} />
    <div className="segmented-nav" aria-label="US market view">{['stocks', 'news'].map(t => <button key={t} aria-pressed={tab === t} onClick={() => setTab(t)}>{t === 'stocks' ? 'Stocks & watchlist' : 'US stock news'}</button>)}</div>
    {tab === 'stocks' ? <Home market="US" /> : <section className="card"><header className="section-heading"><h2>US company headlines</h2><span className="data-caption">Past 7 days · {refreshing ? 'Refreshing' : 'Saved feed'}</span></header>{error && <p role="alert" className="status-note">{error}</p>}{!news.length ? <div className="empty-state"><h3>{busy || refreshing ? 'Checking US headlines…' : 'No US headlines yet'}</h3><p>Open a stock and refresh it to fetch company news.</p></div> : news.map(n => <article key={n.id} className="news-row"><div className="news-row-meta"><Link className="ticker-label" to={`/stock-research?stockId=${n.stock_id}`}>{n.ticker}</Link><span className={`sentiment sentiment-${n.sentiment.toLowerCase()}`}>{n.sentiment.toLowerCase()}</span></div><a className="news-headline" href={/^https:\/\//.test(n.url) ? n.url : undefined} target="_blank" rel="noopener noreferrer">{n.headline} ↗</a><p className="news-source">{n.source} · {new Date(n.published_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} IST</p></article>)}</section>}
    <p className="app-footnote">Best-effort closing data, not live quotes. Broker availability varies by stock. Headlines do not establish why a price moved.</p>
  </>
}
