import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type NewsFeed as Feed } from '../lib/api'
import { Icon } from './Icon'
import { Skeleton } from './ui'

const labels = { POSITIVE: 'Positive', NEGATIVE: 'Negative', MIXED: 'Mixed', NEUTRAL: 'Neutral' }
function timestamp(value: string) { return new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit', timeZone: 'Asia/Kolkata' }).format(new Date(value)) }
export function NewsFeed({ compact = false, stockId }: { compact?: boolean; stockId?: number }) {
  const [feed, setFeed] = useState<Feed | null>(null)
  const [sentiment, setSentiment] = useState('ALL')
  const [scope, setScope] = useState('all')
  const [unread, setUnread] = useState(false)
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const refresh = useCallback(() => setRevision(n => n + 1), [])
  useEffect(() => {
    window.addEventListener('moneyfest-data-updated', refresh)
    const timer = setInterval(refresh, 30000)
    return () => { clearInterval(timer); window.removeEventListener('moneyfest-data-updated', refresh) }
  }, [refresh])
  useEffect(() => {
    let active = true
    api.news({ sentiment, scope, unread: String(unread), offset: String(offset), ...(stockId ? { stockId: String(stockId) } : {}) })
      .then(data => { if (active) { setFeed(data); setError('') } })
      .catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [sentiment, scope, unread, offset, stockId, revision])
  const items = compact ? feed?.items.slice(0, 4) : feed?.items
  const failures = feed?.sync.filter(s => s.status === 'ERROR') ?? []
  const newsSync = feed?.sync.filter(s => s.scope.startsWith('news:')) ?? []
  const latest = newsSync.map(s => s.succeeded_at).filter((s): s is string => !!s).sort().at(-1)
  return <section className={`card news-feed ${compact ? 'compact-feed' : ''}`}>
    <header className="section-heading"><div className="flex items-center gap-2"><span className="section-icon"><Icon name="news" size={17} /></span><h2>{stockId ? 'Company news' : compact ? 'Your news brief' : 'Your feed'}</h2>{feed && <span className="count-badge">{feed.total}</span>}</div>{compact ? <Link className="text-link" to="/news">View all <Icon name="arrow" size={14} /></Link> : <span className="muted text-xs">Last 7 days</span>}</header>
    {!compact && <div className="feed-toolbar"><div className="segmented" role="group" aria-label="News sentiment">{(['ALL', 'POSITIVE', 'NEGATIVE', 'MIXED', 'NEUTRAL'] as const).map(v => <button key={v} aria-pressed={sentiment === v} onClick={() => { setSentiment(v); setOffset(0); setFeed(null) }}>{v === 'ALL' ? 'All news' : labels[v]}</button>)}</div>{!stockId && <div className="feed-options"><select aria-label="News scope" value={scope} onChange={e => { setScope(e.target.value); setOffset(0); setFeed(null) }}><option value="all">My stocks</option><option value="held">Holdings</option><option value="watched">Watchlist</option></select><label><input type="checkbox" checked={unread} onChange={e => { setUnread(e.target.checked); setOffset(0); setFeed(null) }} /> Unread only</label></div>}</div>}
    {error && <p className="status-note" role="alert">Could not load news. <button className="text-link" onClick={refresh}>Retry</button></p>}
    {failures.length > 0 && <details className="status-note"><summary>{failures.length} data source{failures.length === 1 ? '' : 's'} unavailable · showing saved data</summary>{failures.map(s => <p key={s.scope}>{s.ticker} · {s.scope.startsWith('news:') ? 'News' : 'Prices'}: {s.detail}</p>)}</details>}
    {!feed && !error ? <div className="p-5 space-y-3"><Skeleton className="h-16 w-full" /><Skeleton className="h-16 w-full" /></div> : items?.length === 0 ? <div className="empty-state"><span className="empty-icon"><Icon name="news" size={26} /></span><h3>{feed?.refreshing ? 'Checking your stocks…' : unread ? 'You’re all caught up' : 'No matching news yet'}</h3><p>{feed?.sync.length ? 'Refresh or change filters to check for updates.' : stockId ? 'Refresh this stock to fetch company headlines.' : 'Add a holding or watch a stock to start your feed.'}</p>{!stockId && !feed?.sync.length && <Link to="/home" className="text-link">Explore stocks <Icon name="arrow" size={14} /></Link>}</div> : <div className="news-list">{items?.map(item => <article className={`news-row ${item.read ? 'is-read' : ''}`} key={item.id}>
      <div className="news-row-meta"><span className="ticker-label">{item.ticker}</span><span className={`sentiment sentiment-${item.sentiment.toLowerCase()}`}>{item.sentiment === 'POSITIVE' ? '↗' : item.sentiment === 'NEGATIVE' ? '↘' : '•'} {labels[item.sentiment]}</span>{!item.read && <span className="unread-dot" aria-label="Unread" />}</div>
      <a className="news-headline" href={/^https:\/\//.test(item.url) ? item.url : undefined} target="_blank" rel="noopener noreferrer">{item.summary}<Icon name="external" size={13} /></a>
      <div className="news-source"><span>{item.source}</span><span>·</span><time dateTime={item.published_at}>{timestamp(item.published_at)} IST</time>{!stockId && !item.read && <button title="Mark as read" aria-label={`Mark ${item.ticker} headline as read`} onClick={async () => { try { await api.readNews(item.id); refresh() } catch { setError('Could not mark headline as read.') } }}><Icon name="check" size={14} /> Mark read</button>}</div>
    </article>)}</div>}
    {!compact && feed && feed.total > 30 && <div className="pagination"><button className="secondary-button" disabled={!offset} onClick={() => { setOffset(Math.max(0, offset - 30)); setFeed(null) }}>Previous</button><span>{offset + 1}–{Math.min(offset + 30, feed.total)} of {feed.total}</span><button className="secondary-button" disabled={offset + 30 >= feed.total} onClick={() => { setOffset(offset + 30); setFeed(null) }}>Next</button></div>}
    <footer className="feed-footnote"><span>Headline sentiment · price impact unverified</span>{latest && !compact && <span>Checked {timestamp(latest)} IST</span>}</footer>
  </section>
}
