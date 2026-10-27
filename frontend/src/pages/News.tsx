import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import { api, type NewsFeed, type NewsItem, type User } from '../lib/api'
import { PageHeader } from '../components/Shell'
import { RefreshButton } from '../components/RefreshButton'
import { Icon } from '../components/Icon'

const toneLabels = { POSITIVE: 'Positive', NEGATIVE: 'Negative', MIXED: 'Mixed', NEUTRAL: 'Neutral' }
function published(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Date unavailable' : new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit', timeZone: 'Asia/Kolkata' }).format(date)
}
function loadSaved(key: string): NewsItem[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) ?? '[]')
    return Array.isArray(value) ? value.filter((x): x is NewsItem => x && typeof x.id === 'number' && typeof x.summary === 'string' && typeof x.headline === 'string' && typeof x.ticker === 'string' && typeof x.url === 'string' && typeof x.published_at === 'string' && x.sentiment in toneLabels).slice(0, 200) : []
  } catch { return [] }
}

export function News() {
  const { user } = useOutletContext<{ user: User | null }>()
  const [feed, setFeed] = useState<NewsFeed | null>(null)
  const [view, setView] = useState('all')
  const [scope, setScope] = useState('all')
  const [sentiment, setSentiment] = useState('ALL')
  const [query, setQuery] = useState('')
  const [offset, setOffset] = useState(0)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [saved, setSaved] = useState<NewsItem[]>([])
  const [savedOwner, setSavedOwner] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [reading, setReading] = useState(false)
  const [revision, setRevision] = useState(0)
  const readerHeading = useRef<HTMLHeadingElement>(null)
  const refresh = useCallback(() => setRevision(x => x + 1), [])
  const saveKey = user ? `moneyfest-saved-news:${user.id}` : null
  useEffect(() => {
    setSaved(saveKey ? loadSaved(saveKey) : []); setSavedOwner(user?.id ?? null)
  }, [saveKey, user?.id])
  useEffect(() => {
    const timer = setInterval(refresh, 30000)
    window.addEventListener('moneyfest-data-updated', refresh)
    return () => { clearInterval(timer); window.removeEventListener('moneyfest-data-updated', refresh) }
  }, [refresh])
  useEffect(() => {
    if (view === 'saved') { setLoading(false); return }
    let active = true
    setLoading(true)
    api.news({ scope, sentiment, unread: String(view === 'unread'), offset: String(offset) }).then(data => {
      if (active) { setFeed(data); setError('') }
    }).catch(() => { if (active) setError('News could not be refreshed. Your last loaded headlines are still available.') }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [scope, sentiment, view, offset, revision])
  const items = useMemo(() => {
    const source = view === 'saved' ? saved : feed?.items ?? []
    const needle = query.trim().toLowerCase()
    return source.filter(x => (sentiment === 'ALL' || sentiment === x.sentiment) && (!needle || `${x.ticker} ${x.name} ${x.headline} ${x.source}`.toLowerCase().includes(needle)))
  }, [view, saved, feed, query, sentiment])
  const selected = items.find(x => x.id === selectedId) ?? items[0] ?? null
  const closeReader = useCallback(() => {
    setDetailOpen(false)
    requestAnimationFrame(() => document.getElementById(`headline-${selectedId}`)?.focus())
  }, [selectedId])
  useEffect(() => { setDetailOpen(false); setSelectedId(null) }, [view, scope, sentiment, offset])
  useEffect(() => {
    const escape = (e: KeyboardEvent) => { if (e.key === 'Escape' && detailOpen) closeReader() }
    window.addEventListener('keydown', escape)
    return () => window.removeEventListener('keydown', escape)
  }, [detailOpen, closeReader])
  function choose(item: NewsItem) {
    setSelectedId(item.id); setDetailOpen(true)
    if (window.matchMedia('(max-width: 800px)').matches) requestAnimationFrame(() => readerHeading.current?.focus())
  }
  function changeView(next: string) { setView(next); setOffset(0); setQuery(''); setFeed(null) }
  function storeSaved(next: NewsItem[]) {
    if (!saveKey || savedOwner !== user?.id) return
    try { localStorage.setItem(saveKey, JSON.stringify(next)); setSaved(next); setError('') }
    catch { setError('This browser could not save the headline. Free some browser storage and try again.') }
  }
  function toggleSaved(item: NewsItem) {
    const exists = saved.some(x => x.id === item.id)
    if (!exists && saved.length >= 200) { setError('You have 200 saved headlines. Remove one to save another.'); return }
    storeSaved(exists ? saved.filter(x => x.id !== item.id) : [item, ...saved])
  }
  async function markRead(item: NewsItem) {
    setReading(true)
    try {
      await api.readNews(item.id)
      setFeed(current => current ? { ...current, total: view === 'unread' ? Math.max(0, current.total - 1) : current.total, items: view === 'unread' ? current.items.filter(x => x.id !== item.id) : current.items.map(x => x.id === item.id ? { ...x, read: true } : x) } : current)
      if (saved.some(x => x.id === item.id)) storeSaved(saved.map(x => x.id === item.id ? { ...x, read: true } : x))
      setError('')
    } catch { setError('Could not mark this headline as read. Try again.') }
    finally { setReading(false) }
  }
  const savedSelected = selected ? saved.some(x => x.id === selected.id) : false
  const failed = feed?.sync.filter(x => x.status === 'ERROR') ?? []
  return <div className="news-workspace">
    <PageHeader title="News & alerts" subtitle="Your stocks. One focused inbox." aside={<RefreshButton />} />
    {error && <div className="inbox-error" role="alert">{error}<button onClick={refresh}>Retry</button></div>}
    <div className="inbox-navigation">
      <div role="group" aria-label="News inbox" className="inbox-tabs">{[['all', 'All news', 'news'], ['unread', 'Unread', 'bell'], ['saved', 'Saved', 'bookmark']].map(([id, label, icon]) => <button key={id} aria-pressed={view === id} onClick={() => changeView(id)}><Icon name={icon} size={17} />{label}{id === 'saved' && <span>{saved.length}</span>}</button>)}</div>
      {view === 'saved' ? <span className="inbox-storage-note">Saved on this device</span> : <select aria-label="News scope" value={scope} onChange={e => { setScope(e.target.value); setOffset(0); setFeed(null) }}><option value="all">My stocks</option><option value="held">Holdings</option><option value="watched">Watchlist</option></select>}
    </div>
    <section className={`news-inbox ${detailOpen ? 'reader-open' : ''}`} aria-label="News workspace">
      <div className="inbox-feed-pane">
        <div className="inbox-list-tools"><label className="inbox-search"><Icon name="search" size={16} /><input aria-label={view === 'saved' ? 'Search saved headlines' : 'Search headlines on this page'} placeholder={view === 'saved' ? 'Search saved headlines' : 'Search this page'} value={query} onChange={e => setQuery(e.target.value)} />{query && <button aria-label="Clear headline search" onClick={() => setQuery('')}><Icon name="close" size={14} /></button>}</label>
          <div role="group" aria-label="News sentiment" className="inbox-tones">{['ALL', 'POSITIVE', 'NEGATIVE', 'MIXED', 'NEUTRAL'].map(value => <button key={value} aria-pressed={sentiment === value} onClick={() => { setSentiment(value); setOffset(0); setFeed(null) }}>{value === 'ALL' ? 'All tones' : toneLabels[value as keyof typeof toneLabels]}</button>)}</div>
          <div className="inbox-list-caption"><span>{view === 'saved' ? `${items.length} saved headlines` : query ? `${items.length} matches on this page` : `${feed?.total ?? 0} headlines · Last 7 days`}</span><span role="status">{loading ? 'Updating…' : view === 'saved' ? 'Recently saved' : feed?.refreshing ? 'Checking sources…' : 'Latest first'}</span></div>
        </div>
        <div className="inbox-headlines" aria-label="Headlines" aria-busy={loading}>
          {loading && !feed && view !== 'saved' ? <div className="inbox-loading" role="status">Loading your headlines…</div> : !items.length ? <div className="inbox-empty"><Icon name={view === 'saved' ? 'bookmark' : 'news'} size={28} /><h2>{query ? 'No matching headlines' : view === 'saved' ? 'Keep the stories that matter' : view === 'unread' ? 'You’re all caught up' : 'No matching news yet'}</h2><p>{query ? 'Try a different search on this page.' : view === 'saved' ? 'Save a headline from your inbox to return to it here.' : feed?.sync.length ? 'Change your filters or refresh to check for updates.' : 'Follow a company or add a holding to start your personal news feed.'}</p>{query ? <button onClick={() => setQuery('')}>Clear search</button> : view === 'saved' ? <button onClick={() => changeView('all')}>Back to all news</button> : <Link to="/home?filter=watched">Explore stocks <Icon name="arrow" size={14} /></Link>}</div> : items.map((item, index) => <button key={item.id} id={`headline-${item.id}`} className={`inbox-headline ${selected?.id === item.id ? 'selected' : ''} ${item.read ? 'is-read' : ''}`} aria-pressed={selected?.id === item.id} onClick={() => choose(item)} onKeyDown={e => {
            if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
            e.preventDefault(); const next = items[Math.max(0, Math.min(items.length - 1, index + (e.key === 'ArrowDown' ? 1 : -1)))]; setSelectedId(next.id); document.getElementById(`headline-${next.id}`)?.focus()
          }}><span className="inbox-headline-top"><span className="inbox-ticker">{item.ticker.replace(/\.US$/, '')}</span><span className={`inbox-tone tone-${item.sentiment.toLowerCase()}`}>{toneLabels[item.sentiment]}</span>{!item.read && <span className="inbox-unread" aria-label="Unread headline" />}{saved.some(x => x.id === item.id) && <Icon name="bookmark" size={12} />}</span><strong>{item.headline || item.summary}</strong><span className="inbox-headline-source">{item.source}<time dateTime={item.published_at}>{published(item.published_at)}</time></span></button>)}
        </div>
        <div className="inbox-list-footer">{view !== 'saved' && feed && feed.total > 30 ? <><button aria-label="Previous headlines" disabled={offset === 0} onClick={() => { setOffset(Math.max(0, offset - 30)); setFeed(null) }}><Icon name="back" size={15} /></button><span>{offset + 1}–{Math.min(offset + 30, feed.total)} of {feed.total}</span><button aria-label="Next headlines" disabled={offset + 30 >= feed.total} onClick={() => { setOffset(offset + 30); setFeed(null) }}><Icon name="arrow" size={15} /></button></> : <span>{view === 'saved' ? 'Only you can see your saved headlines' : 'Headlines from the companies you follow'}</span>}</div>
      </div>
      <section className="inbox-reader" aria-label="Headline detail">
        <div className="reader-toolbar"><button className="reader-back" onClick={closeReader}><Icon name="back" size={17} />Inbox</button><span className="reader-label">HEADLINE BRIEF</span>{selected && <div className="reader-actions"><button disabled={!user || savedOwner !== user.id} aria-pressed={savedSelected} onClick={() => toggleSaved(selected)}><Icon name="bookmark" size={17} />{savedSelected ? 'Saved' : 'Save'}</button><button disabled={selected.read || reading} onClick={() => void markRead(selected)}><Icon name="check" size={17} />{selected.read ? 'Read' : reading ? 'Saving…' : 'Mark read'}</button></div>}</div>
        {selected ? <div className="reader-scroll"><div className="reader-article"><div className="reader-kicker"><span>{selected.source}</span><span>·</span><time dateTime={selected.published_at}>{published(selected.published_at)} IST</time></div><h2 tabIndex={-1} ref={readerHeading}>{selected.headline || selected.summary}</h2><Link className="reader-company" to={`/stock-research?stockId=${selected.stock_id}`}><span className="reader-company-symbol">{selected.ticker.replace(/\.US$/, '')}</span><span><strong>{selected.name}</strong><small>{selected.exchange} · Open stock research</small></span><Icon name="arrow" size={17} /></Link>
          {selected.summary && selected.summary !== selected.headline && <p className="reader-summary">{selected.summary}</p>}
          <div className="reader-source-note"><Icon name="news" size={18} /><p>This is a headline brief. Read the publisher’s article for full reporting and context.</p></div>
          {/^https:\/\//.test(selected.url) ? <a className="reader-publisher" href={selected.url} target="_blank" rel="noopener noreferrer">Read at {selected.source}<Icon name="external" size={16} /></a> : <p className="status-note">Publisher link unavailable.</p>}
          <div className="reader-tone-note"><div><span className={`inbox-tone tone-${selected.sentiment.toLowerCase()}`}>{toneLabels[selected.sentiment]} wording</span><span>Headline tone</span></div><p>{selected.sentiment === 'NEUTRAL' ? 'No clear positive or negative wording was detected.' : selected.sentiment === 'MIXED' ? 'The headline contains a mix of positive and negative wording.' : `The headline uses ${toneLabels[selected.sentiment].toLowerCase()} wording.`} Check the company’s price history and the original source before drawing a conclusion about market impact.</p></div>
        </div><div className="reader-footer"><Icon name="info" size={14} />Headline sentiment is not a price forecast.</div></div> : <div className="reader-placeholder"><div className="reader-placeholder-icon"><Icon name="news" size={30} /></div><h2>Your reading space</h2><p>Select a headline to read its brief, save it for later, or continue to the company’s research.</p><div><span><Icon name="bookmark" size={16} />Save for later</span><span><Icon name="search" size={16} />Research the stock</span></div></div>}
      </section>
    </section>
    {failed.length > 0 && <details className="inbox-sync-note"><summary>{failed.length} source{failed.length === 1 ? '' : 's'} unavailable · saved data shown</summary>{failed.map(x => <p key={x.scope}>{x.ticker ?? x.scope}: {x.detail}</p>)}</details>}
  </div>
}
