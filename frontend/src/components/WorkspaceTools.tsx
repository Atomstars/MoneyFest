import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api, type AssistantReply, type StockRow, type Fund } from '../lib/api'
import { Icon } from './Icon'

export function WorkspaceSearch() {
  const [query, setQuery] = useState('')
  const [stocks, setStocks] = useState<StockRow[]>([])
  const [funds, setFunds] = useState<Fund[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState(false)
  const location = useLocation()
  useEffect(() => { setExpanded(false); setQuery('') }, [location])
  useEffect(() => {
    if (!query.trim()) { setStocks([]); setFunds([]); return }
    let active = true
    setLoading(true); setError('')
    const timer = setTimeout(async () => {
      const results = await Promise.allSettled([api.stocks(query), api.funds(query)])
      if (!active) return
      setStocks(results[0].status === 'fulfilled' ? results[0].value.slice(0, 4) : [])
      setFunds(results[1].status === 'fulfilled' ? results[1].value.items.slice(0, 4) : [])
      if (results.some(r => r.status === 'rejected')) setError('Some results are unavailable. Try again shortly.')
      setLoading(false)
    }, 250)
    return () => { active = false; clearTimeout(timer) }
  }, [query])
  return <div className="workspace-search" onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget)) setExpanded(false) }}><label><Icon name="search" size={17} /><input aria-label="Search workspace" placeholder="Search stocks, funds, sectors…" maxLength={100} value={query} onFocus={() => setExpanded(true)} onKeyDown={e => { if (e.key === 'Escape') setExpanded(false) }} onChange={e => { setQuery(e.target.value); setExpanded(true) }} /></label>
    {expanded && query.trim() && <div className="workspace-results" aria-label="Search results"><span className="eyebrow">QUICK FIND</span>{loading ? <p role="status">Searching both catalogs…</p> : <>{error && <p role="alert">{error}</p>}<h3>Stocks</h3>{stocks.map(s => <Link key={s.stock_id} to={`${s.currency === 'USD' ? '/us-stocks' : '/home'}?query=${encodeURIComponent(s.symbol ?? s.ticker ?? s.name)}`}><strong>{s.symbol ?? s.ticker}</strong><span>{s.name}</span></Link>)}{!stocks.length && <p>No matching stocks</p>}<h3>Mutual funds</h3>{funds.map(f => <Link key={f.code} to={`/funds?query=${encodeURIComponent(f.code)}`}><strong>{f.name}</strong><span>{f.category}</span></Link>)}{!funds.length && <p>No matching funds</p>}</>}</div>}
  </div>
}

const prompts: Record<string, string[]> = {
  '/home': ['How should I research a stock?', 'What news matters to my tracked stocks?'],
  '/us-stocks': ['What currency risks matter for US stocks?', 'What news matters to my tracked US stocks?'],
  '/stock-research': ['How do market and limit orders differ?', 'How should I interpret a moving average?'],
  '/portfolio-lab': ['Review my saved portfolio plan.', 'Which concentration risks are visible in my plan?'],
  '/funds': ['Explain index funds and active funds.', 'What risks should I compare across funds?'],
  '/dashboard': ['Which risks are visible in my holdings?', 'Explain portfolio diversification.'],
  '/news': ['What news matters to my portfolio?', 'How do I distinguish news from speculation?'],
  '/research': ['How could rate news affect banking funds?', 'Explain the uncertainty in sector signals.'],
  '/settings': ['How can I use this research assistant?', 'What is a watchlist?'],
}
export function WorkspaceAssistant({ section }: { section: string }) {
  const { pathname, search } = useLocation()
  const dialog = useRef<HTMLDialogElement>(null)
  const [available, setAvailable] = useState<boolean | null>(null)
  const [question, setQuestion] = useState('')
  const [reply, setReply] = useState<AssistantReply | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const requestId = useRef(0)
  useEffect(() => { requestId.current++; setQuestion(''); setReply(null); setError(''); setBusy(false); dialog.current?.close() }, [pathname, search])
  function open() {
    dialog.current?.showModal()
    api.assistantStatus().then(s => setAvailable(s.available)).catch(() => { setAvailable(null); setError('Assistant status is unavailable. Close and reopen to retry.') })
  }
  async function ask() {
    const id = ++requestId.current
    setBusy(true); setError('')
    const term = new URLSearchParams(search).get('query')
    const context = `Section: ${section}.${term ? ` Search: ${term.slice(0, 50)}.` : ''} Question: `
    try { const answer = await api.askAssistant((context + question.trim()).slice(0, 400)); if (id === requestId.current) setReply(answer) }
    catch (e) { if (id === requestId.current) setError(e instanceof Error ? e.message : 'Could not answer. Please retry.') }
    finally { if (id === requestId.current) setBusy(false) }
  }
  return <><button className="assistant-launcher" onClick={open}><Icon name="message" size={19} /><span>Ask Moneyfest</span><span className="assistant-launcher-dot" /></button><dialog ref={dialog} className="workspace-assistant" onClick={e => { if (e.target === e.currentTarget) dialog.current?.close() }} aria-labelledby="workspace-assistant-title"><div className="assistant-head"><span className="assistant-mark"><Icon name="message" /></span><div><h2 id="workspace-assistant-title">Ask Moneyfest</h2><small>Exploring · {section}</small></div><button className="assistant-close" aria-label="Close assistant" onClick={() => dialog.current?.close()}>×</button></div><div className="assistant-body"><div className="assistant-intro"><strong>A clearer perspective.</strong><span>Ask a question about this section or your portfolio.</span></div>{available === false && <p className="status-note">AI answers are not enabled for this workspace yet.</p>}<div className="assistant-prompts">{(prompts[pathname] ?? prompts['/home']).map(q => <button key={q} onClick={() => setQuestion(q)}>{q}<Icon name="arrow" size={14} /></button>)}</div>{reply && <div className="assistant-answer" aria-live="polite"><strong>Research view</strong><div>{reply.answer}</div><div className="assistant-sources">{reply.sources.filter(s => /^https?:\/\//.test(s.url)).map(s => <a key={s.id} href={s.url} target="_blank" rel="noopener noreferrer">{s.id} · {s.headline} ↗</a>)}</div></div>}{error && <p className="status-note" role="alert">{error}</p>}</div><form className="assistant-form" onSubmit={e => { e.preventDefault(); void ask() }}><label htmlFor="workspace-question">Your question</label><textarea id="workspace-question" placeholder="What would you like to understand?" maxLength={280} value={question} onChange={e => setQuestion(e.target.value)} /><button className="action-button" disabled={!available || busy || question.trim().length < 3}>{busy ? 'Thinking…' : 'Ask Moneyfest'} <Icon name="arrow" size={14} /></button></form></dialog></>
}
