import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, type AssistantReply, type ThemeSignal } from '../lib/api'
import { PageHeader } from '../components/Shell'
import { Icon } from '../components/Icon'

const signalText: Record<ThemeSignal['signal'], string> = { POSITIVE: 'Positive headline tone', NEGATIVE: 'Negative headline tone', MIXED: 'Mixed headline tone', INSUFFICIENT: 'More evidence needed' }
const themesMeta: Record<string, {icon: string; name: string; term: string; color: string}> = {
  MACRO: {icon: 'globe', name: 'Macro & policy', term: '', color: 'blue'},
  BANKING: {icon: 'funds', name: 'Banking', term: 'banking', color: 'violet'},
  TECH: {icon: 'technology', name: 'Technology', term: 'technology', color: 'coral'},
  ENERGY: {icon: 'bolt', name: 'Energy', term: 'energy', color: 'lime'},
  PHARMA: {icon: 'health', name: 'Pharma', term: 'pharma', color: 'cyan'},
  AUTO: {icon: 'markets', name: 'Auto', term: 'auto', color: 'pink'},
}
type Tone = 'ALL' | 'POSITIVE' | 'NEGATIVE' | 'OTHER'
export function Research() {
  const [themes, setThemes] = useState<ThemeSignal[]>([])
  const [active, setActive] = useState('MACRO')
  const [tone, setTone] = useState<Tone>('ALL')
  const [available, setAvailable] = useState(false)
  const [question, setQuestion] = useState('')
  const [reply, setReply] = useState<AssistantReply | null>(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [aiError, setAiError] = useState('')
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let current = true
    setLoading(true)
    api.themes().then(data => { if (current) { setThemes(data); setError(''); setActive(previous => data.some(t => t.id === previous) ? previous : data[0]?.id ?? 'MACRO') } }).catch(e => { if (current) setError(e.message) }).finally(() => { if (current) setLoading(false) })
    api.assistantStatus().then(s => { if (current) setAvailable(s.available) }).catch(() => {})
    return () => { current = false }
  }, [revision])
  const selected = themes.find(t => t.id === active)
  const meta = themesMeta[active] ?? themesMeta.MACRO
  const events = selected?.events ?? []
  const visible = events.filter(e => tone === 'ALL' || (tone === 'OTHER' ? !['POSITIVE', 'NEGATIVE'].includes(e.sentiment) : e.sentiment === tone))
  const positive = events.filter(e => e.sentiment === 'POSITIVE').length
  const negative = events.filter(e => e.sentiment === 'NEGATIVE').length
  async function ask(e: FormEvent) {
    e.preventDefault(); if (question.trim().length < 3 || busy || !available) return
    setBusy(true); setAiError(''); setReply(null)
    try { setReply(await api.askAssistant(`Sector: ${selected?.label ?? meta.name}. ${question.trim()}`.slice(0, 400))) }
    catch (e) { setAiError(e instanceof Error ? e.message : 'Research assistant could not answer.') }
    finally { setBusy(false) }
  }
  function selectTheme(id: string) { setActive(id); setTone('ALL'); setReply(null); setAiError('') }
  return <div className="research-experience">
    <PageHeader title="Research desk" subtitle="Company, sector and macro headlines." aside={<span className="research-range"><span />Past 7 days</span>} />
    <section className="sector-switcher" aria-labelledby="sector-switcher-title"><div className="feature-section-heading"><h2 id="sector-switcher-title">Browse sectors</h2><Link className="text-link" to="/stock-research">Research a stock <Icon name="arrow" size={17} /></Link></div>
      <div className="research-sector-grid" role="group" aria-label="Select a research sector">{loading && !themes.length ? Object.entries(themesMeta).map(([id, m]) => <div className="research-sector-skeleton" key={id}><Icon name={m.icon} size={26} /><span>{m.name}</span></div>) : themes.map(t => { const m = themesMeta[t.id] ?? themesMeta.MACRO; return <button key={t.id} aria-pressed={active === t.id} onClick={() => selectTheme(t.id)} className={`research-sector sector-color-${m.color} ${active === t.id ? 'selected' : ''}`}><strong>{m.name}</strong><small>{t.events.length} {t.events.length === 1 ? 'story' : 'stories'}</small><span className="sector-select-indicator"><Icon name={active === t.id ? 'check' : 'arrow'} size={14} /></span></button> })}</div>
    </section>
    {error && <p className="status-note" role="alert">{error} <button onClick={() => setRevision(n => n + 1)}>Retry</button></p>}
    <div className="research-workbench">
      <div className="research-story-column">
        <section className={`market-lens lens-${meta.color}`} aria-labelledby="market-lens-title" key={active}>
          <div className="lens-topline"><span className="lens-eyebrow"><Icon name={meta.icon} size={18} />SECTOR SPOTLIGHT</span><span className="lens-source-label">News evidence</span></div>
          <div className="lens-heading"><div><h2 id="market-lens-title">{meta.name}</h2><p>{selected?.focus ?? (loading ? 'Loading headlines…' : selected ? signalText[selected.signal] : 'Select a sector to begin')}</p></div></div>
          <div className="lens-stats" role="group" aria-label="Filter selected sector headlines"><button aria-pressed={tone === 'ALL'} onClick={() => setTone('ALL')}><strong>{loading && !selected ? '—' : events.length}</strong><span>All stories <Icon name="arrow" size={14} /></span></button><button aria-pressed={tone === 'POSITIVE'} onClick={() => setTone('POSITIVE')}><strong>{loading && !selected ? '—' : positive}</strong><span><i className="tone-dot tone-positive" />Positive tone</span></button><button aria-pressed={tone === 'NEGATIVE'} onClick={() => setTone('NEGATIVE')}><strong>{loading && !selected ? '—' : negative}</strong><span><i className="tone-dot tone-negative" />Negative tone</span></button></div>
          <p className="lens-footnote"><Icon name="info" size={14} />Headline tone describes wording, not future price direction.</p>
        </section>
        <section className="card research-evidence research-story-feed"><header className="section-heading"><div><span className="evidence-eyebrow">THE READING LIST</span><h2>{meta.name} evidence</h2></div><Link className="text-link" to={`/funds?query=${encodeURIComponent(meta.term)}`}>Related funds <Icon name="arrow" size={15} /></Link></header>
          <div className="evidence-filters" role="group" aria-label="Headline tone">{([['ALL', 'All stories'], ['POSITIVE', 'Positive'], ['NEGATIVE', 'Negative'], ['OTHER', 'Neutral & mixed']] as const).map(([key, label]) => <button key={key} aria-pressed={tone === key} onClick={() => setTone(key)}>{label}</button>)}</div>
          <div className="evidence-story-list" aria-live="polite">{loading && !selected ? <div className="empty-state" role="status">Finding sector evidence…</div> : visible.length ? visible.map((e, i) => <a className="evidence-story" key={`${active}-${e.url}-${i}`} href={/^https:\/\//.test(e.url) ? e.url : undefined} target="_blank" rel="noopener noreferrer"><span className="evidence-story-number">{String(i + 1).padStart(2, '0')}</span><div><span className="evidence-story-meta">{e.source} <span>·</span> {new Date(e.published_at).toLocaleDateString('en-IN', {day: 'numeric', month: 'short', timeZone: 'Asia/Kolkata'})}</span><h3>{e.headline}</h3><span className={`sentiment sentiment-${e.sentiment.toLowerCase()}`}>{e.sentiment.toLowerCase()}</span></div><span className="story-open"><Icon name="external" size={17} /></span></a>) : <div className="empty-state"><span className="empty-icon"><Icon name="news" size={28} /></span><h3>{events.length ? 'No stories with this tone' : 'No recent evidence yet'}</h3><p>{events.length ? 'Choose another tone to explore the available headlines.' : 'Research feeds refresh while the server runs.'}</p>{tone !== 'ALL' && <button className="secondary-button" onClick={() => setTone('ALL')}>Show all stories</button>}</div>}</div>
          {selected?.sync.some(s => s.status === 'ERROR') && <p className="status-note">This sector feed could not refresh. Any saved headlines are shown above.</p>}
          <p className="feed-footnote">Linked publishers · Up to 12 recent headlines per sector · Price impact remains uncertain</p>
        </section>
      </div>
      <section className="card assistant-card research-assistant"><header className="research-assistant-cover"><span className="assistant-cover-label">RESEARCH ASSISTANT</span><h2>Ask Moneyfest</h2><p>Your portfolio and source-linked headlines.</p></header><div className="assistant-body"><div className="assistant-availability"><span className={available ? 'connected' : ''} />{available ? 'AI connected · source-linked answers' : 'AI research is not connected yet'}</div>
        {!available && <Link className="coach-shortcut" to="/portfolio-lab"><span className="coach-shortcut-icon"><Icon name="portfolio" size={22} /></span><span><strong>Try the portfolio coach</strong><small>Allocation checks are ready to use.</small></span><Icon name="arrow" size={17} /></Link>}
        <span className="prompt-section-label">START WITH A QUESTION</span><div className="assistant-prompts">{['What news matters to my portfolio?', `What should I watch in ${meta.name.toLowerCase()}?`, 'Which risks are visible in my holdings?'].map(q => <button key={q} onClick={() => { setQuestion(q); document.getElementById('assistant-question')?.focus() }}>{q}<Icon name="arrow" size={15} /></button>)}</div>
        {reply && <div className="assistant-answer" aria-live="polite"><strong>Research view</strong><div>{reply.answer}</div>{reply.sources.length > 0 && <div className="assistant-sources">{reply.sources.filter(s => /^https:\/\//.test(s.url)).map(s => <a href={s.url} target="_blank" rel="noopener noreferrer" key={s.id}>{s.id} · {s.headline} <Icon name="external" size={12} /></a>)}</div>}</div>}
        {aiError && <p className="status-note" role="alert">{aiError}</p>}
      </div><form className="assistant-form" onSubmit={e => void ask(e)}><label htmlFor="assistant-question">Your research question</label><textarea id="assistant-question" maxLength={350} rows={3} placeholder="What would you like to understand?" value={question} onChange={e => setQuestion(e.target.value)} /><button className="action-button" disabled={!available || busy || question.trim().length < 3}>{busy ? 'Thinking…' : 'Ask Moneyfest'} <Icon name="arrow" size={17} /></button>{!available && <small className="ai-connection-note">AI answers become available when a provider is connected.</small>}</form></section>
    </div>
    <p className="app-footnote">Research and scenarios are uncertain. Headlines do not establish why a price moved.</p>
  </div>
}
