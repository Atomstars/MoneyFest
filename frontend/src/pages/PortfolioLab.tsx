import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { api, type AssistantReply, type Currency, type PlanStock, type StockRow } from '../lib/api'
import { money } from '../lib/format'
import { StockFinder } from '../components/StockFinder'
import { Icon } from '../components/Icon'
import { allocationColor, balanceWeights, emptyDraft, invalidPlan, planPayload, planSignature, scenarioValue, totalWeight, type PlanDraft } from '../lib/planMath'

export function PortfolioLab() {
  const [draft, setDraft] = useState<PlanDraft>(emptyDraft())
  const [baseline, setBaseline] = useState<PlanDraft | null>(null)
  const [past, setPast] = useState<PlanDraft[]>([])
  const [future, setFuture] = useState<PlanDraft[]>([])
  const [locked, setLocked] = useState<Set<number>>(new Set())
  const [loaded, setLoaded] = useState(false)
  const [available, setAvailable] = useState(false)
  const [busy, setBusy] = useState(false)
  const [asking, setAsking] = useState(false)
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [question, setQuestion] = useState('')
  const [reply, setReply] = useState<AssistantReply | null>(null)
  const [view, setView] = useState('build')
  const [decline, setDecline] = useState(20)
  const [lookup, setLookup] = useState('')
  const [revision, setRevision] = useState(0)
  const reviewDialog = useRef<HTMLDialogElement>(null)
  const gesture = useRef<PlanDraft | null>(null)
  const requestId = useRef(0)
  const marketDrafts = useRef<Partial<Record<Currency, PlanDraft>>>({})
  useEffect(() => {
    let active = true
    api.portfolioPlan().then(p => {
      if (!active) return
      if (p.saved) {
        const restored: PlanDraft = {currency: p.currency ?? 'INR', risk: p.risk ?? 'BALANCED', horizon_years: p.horizon_years ?? 5, budget: p.budget ?? 100000, stocks: p.stocks ?? []}
        setDraft(restored); setBaseline(restored)
      }
      setLoaded(true); setError('')
    }).catch(e => { if (active) setError(e.message) })
    api.assistantStatus().then(s => { if (active) setAvailable(s.available) }).catch(() => {})
    return () => { active = false; requestId.current++ }
  }, [revision])
  const total = totalWeight(draft.stocks)
  const cash = 100 - total
  const largest = [...draft.stocks].sort((a, b) => b.weight - a.weight)[0]
  const invalid = invalidPlan(draft)
  const changed = planSignature(draft) !== planSignature(baseline ?? emptyDraft())
  const editingDisabled = !loaded || busy || asking || importing
  const scenario = scenarioValue(draft, decline)
  const knownSectors = draft.stocks.filter(s => s.sector).reduce((sum, s) => sum + s.weight, 0)
  const missingSectors = draft.stocks.filter(s => !s.sector).length
  function invalidateReview() { requestId.current++; setReply(null); setError(''); setMessage('') }
  function edit(next: PlanDraft) {
    if (planSignature(next) === planSignature(draft)) return
    setPast(history => [...history, draft].slice(-40)); setFuture([]); setDraft(next); invalidateReview()
  }
  function patch(values: Partial<PlanDraft>) { edit({...draft, ...values}) }
  function undo() {
    const previous = past.at(-1); if (!previous || editingDisabled) return
    setPast(past.slice(0, -1)); setFuture([draft, ...future]); setDraft(previous); invalidateReview()
  }
  function redo() {
    const next = future[0]; if (!next || editingDisabled) return
    setPast([...past, draft]); setFuture(future.slice(1)); setDraft(next); invalidateReview()
  }
  function finishGesture() {
    const before = gesture.current
    if (before && planSignature(before) !== planSignature(draft)) { setPast(p => [...p, before].slice(-40)); setFuture([]) }
    gesture.current = null
  }
  function weight(id: number, value: number) {
    const next = {...draft, stocks: draft.stocks.map(s => s.stock_id === id ? {...s, weight: Number.isFinite(value) ? value : 0} : s)}
    if (gesture.current) { setDraft(next); invalidateReview() } else edit(next)
  }
  function changeMarket(currency: Currency) {
    if (currency === draft.currency) return
    marketDrafts.current[draft.currency] = draft
    edit(marketDrafts.current[currency] ?? emptyDraft(currency)); setLocked(new Set()); setLookup(''); setView('build')
  }
  function balance(method: 'equal' | 'proportional') {
    try { patch({stocks: balanceWeights(draft.stocks, locked, method)}) }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not rebalance.') }
  }
  function add(stock: StockRow) {
    if (draft.stocks.some(s => s.stock_id === stock.stock_id)) { setMessage('That company is already in your plan.'); return }
    if (draft.stocks.length >= 30) { setError('A draft supports up to 30 companies.'); return }
    patch({stocks: [...draft.stocks, {...stock, weight: Math.max(.01, Math.min(10, Math.round(cash * 100) / 100))}]})
  }
  function remove(stock: PlanStock) {
    patch({stocks: draft.stocks.filter(s => s.stock_id !== stock.stock_id)})
    setLocked(current => new Set([...current].filter(id => id !== stock.stock_id)))
    setMessage(`${stock.symbol ?? stock.ticker} removed. Undo restores it.`)
  }
  async function persist() {
    const snapshot = draft
    const result = await api.savePortfolioPlan(planPayload(snapshot))
    const saved = {...snapshot, stocks: snapshot.stocks.map(s => {
      const quote = result.stocks?.find(r => r.stock_id === s.stock_id)
      return quote ? {...s, close: quote.close, date: quote.date} : s
    })}
    setDraft(saved); setBaseline(saved); setMessage('Draft saved to your account.')
  }
  async function save() {
    if (invalid || editingDisabled) return
    setBusy(true); setError('')
    try { await persist() } catch (e) { setError(e instanceof Error ? e.message : 'Could not save this draft.') }
    finally { setBusy(false) }
  }
  async function importHoldings() {
    if (draft.stocks.length) return
    setImporting(true); setError('')
    try {
      const portfolio = await api.portfolio(draft.currency)
      if (!portfolio.positions.length) { setMessage(`No ${draft.currency} holdings to import. Search for a company instead.`); return }
      if (portfolio.positions.length > 30) { setError('This account has more than 30 holdings. Choose up to 30 companies using search.'); return }
      const stocks: PlanStock[] = portfolio.positions.map(p => ({stock_id: p.stock_id, ticker: p.ticker, symbol: p.ticker?.replace(/\.(US|BSE)$/, '') ?? p.name, name: p.name, sector: p.sector, exchange: p.exchange ?? (draft.currency === 'USD' ? 'US' : 'NSE'), currency: draft.currency, isin: null, held: true, watched: false, close: p.price, date: portfolio.as_of, change_pct: p.day_change_pct, gate_result: p.gate_result, weight: p.invested > 0 ? p.invested : .01}))
      patch({stocks: balanceWeights(stocks, new Set(), 'proportional')})
      setMessage('Imported holdings, weighted by recorded cost. Your actual holdings have not changed.')
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not import holdings.') }
    finally { setImporting(false) }
  }
  async function ask() {
    if (invalid || question.trim().length < 3 || asking) return
    const currentRequest = ++requestId.current
    setAsking(true); setError(''); setReply(null)
    try {
      await persist()
      const answer = await (available ? api.askAssistant(`Review my saved hypothetical portfolio plan. ${question.trim()}`.slice(0, 400)) : api.reviewPortfolioPlan(question.trim()))
      if (currentRequest === requestId.current) setReply(answer)
    } catch (e) { if (currentRequest === requestId.current) setError(e instanceof Error ? e.message : 'Review is unavailable.') }
    finally { if (currentRequest === requestId.current) setAsking(false) }
  }
  function focusStock(stock: PlanStock) {
    setView('build')
    requestAnimationFrame(() => document.getElementById(`weight-${stock.stock_id}`)?.focus())
  }
  return <div className="allocation-studio">
    <header className="studio-heading"><div><div className="studio-kicker">PORTFOLIO / WORKING DRAFT</div><h1>Portfolio builder</h1></div><div className="studio-heading-actions"><span className={`draft-state ${changed ? 'is-dirty' : ''}`} role="status">{!loaded ? 'Loading draft' : changed ? 'Unsaved changes' : baseline ? 'Saved' : 'Not saved yet'}</span><button className="studio-button" disabled={!loaded || invalid || busy || asking} onClick={() => void save()}>{busy ? 'Saving…' : 'Save draft'}</button></div></header>
    <div className="studio-description">Build a target allocation without changing your recorded holdings.</div>
    {error && <div className="studio-notice is-error" role="alert">{error}{!loaded && <button onClick={() => setRevision(n => n + 1)}>Retry</button>}</div>}
    {message && <div className="studio-notice" role="status">{message}</div>}
    <fieldset disabled={editingDisabled} className="studio-controls">
      <div><label htmlFor="plan-market">Market & currency</label><select id="plan-market" value={draft.currency} onChange={e => changeMarket(e.target.value as Currency)}><option value="INR">India / INR</option><option value="USD">United States / USD</option></select></div>
      <div className="budget-control"><label htmlFor="plan-budget">Investment budget</label><div><span>{draft.currency === 'USD' ? '$' : '₹'}</span><input id="plan-budget" type="number" min="1" max="99999999999999" step="0.01" value={Number.isFinite(draft.budget) ? draft.budget : ''} onChange={e => patch({budget: Number(e.target.value)})} /></div></div>
      <div><label htmlFor="plan-risk">Risk preference</label><select id="plan-risk" value={draft.risk} onChange={e => patch({risk: e.target.value as PlanDraft['risk']})}><option value="CAUTIOUS">Cautious</option><option value="BALANCED">Balanced</option><option value="GROWTH">Growth</option></select></div>
      <div className="horizon-control"><label htmlFor="plan-horizon">Horizon (years)</label><div><input id="plan-horizon" type="number" min="1" max="40" step="1" value={draft.horizon_years} onChange={e => patch({horizon_years: Number(e.target.value)})} /><span>years</span></div></div>
    </fieldset>
    <div className="studio-toolbar"><div className="studio-view-tabs" role="group" aria-label="Portfolio workspace"><button aria-pressed={view === 'build'} onClick={() => setView('build')}>Build allocation</button><button aria-pressed={view === 'compare'} disabled={!baseline || baseline.currency !== draft.currency} title={!baseline ? 'Save a draft to create a comparison baseline' : baseline.currency !== draft.currency ? 'Compare plans in the same currency' : 'Compare changes against your saved draft'} onClick={() => setView('compare')}>Compare with saved</button></div><div className="history-controls"><button disabled={!past.length || editingDisabled} onClick={undo}><Icon name="undo" size={16} />Undo</button><button disabled={!future.length || editingDisabled} onClick={redo}><Icon name="redo" size={16} />Redo</button></div></div>
    <div className="studio-layout"><section className="studio-editor">
      {view === 'build' ? <>
        <header className="studio-section-heading"><div><h2>Choose your companies <span>{String(draft.stocks.length).padStart(2, '0')}</span></h2><p>Search the catalog or start from your recorded holdings.</p></div><button className="studio-text-button" disabled={editingDisabled || !!draft.stocks.length} title={draft.stocks.length ? 'Start with an empty selection to import holdings' : 'Import recorded holdings, weighted by cost'} onClick={() => void importHoldings()}>{importing ? 'Importing…' : 'Import holdings'}</button></header>
        <fieldset className="studio-search" disabled={editingDisabled}><StockFinder key={draft.currency} initialQuery={lookup} market={draft.currency === 'USD' ? 'US' : 'IN'} label="Search portfolio stocks" onSelect={stock => { setLookup(''); add(stock) }} />{!draft.stocks.length && <div className="studio-quick-lookup"><span>Quick lookup</span>{(draft.currency === 'USD' ? ['AAPL', 'MSFT', 'NVDA'] : ['TCS', 'RELIANCE', 'HDFCBANK']).map(symbol => <button key={symbol} onClick={() => setLookup(symbol)}>{symbol}</button>)}</div>}</fieldset>
        {!draft.stocks.length ? <div className="studio-empty"><span className="empty-number">00</span><div><h3>Add the first company.</h3><p>Add it above, then use the sliders to shape your allocation. Unallocated money stays as cash in the plan.</p></div><div className="studio-empty-line"><span>Equities</span><div /><strong>0%</strong></div><div className="studio-empty-line"><span>Cash</span><div className="cash-line" /><strong>100%</strong></div></div> : <>
          <div className="allocation-actions"><span>{total.toFixed(2)}% allocated <span className="allocation-actions-cash">/ {Math.max(0, cash).toFixed(2)}% cash</span></span><div><button disabled={editingDisabled} onClick={() => balance('equal')}>Equal weights</button><button disabled={editingDisabled} onClick={() => balance('proportional')}>{total > 100 ? 'Normalize to 100%' : 'Distribute cash'}</button><button disabled={editingDisabled} onClick={() => { patch({stocks: []}); setLocked(new Set()) }}>Clear</button></div></div>
          <div className="allocation-column-head"><span>Company / target weight</span><span>Allocation</span><span>Whole shares*</span><span /></div>
          <fieldset className="allocation-rows" disabled={editingDisabled}>{draft.stocks.map(stock => {
            const symbol = stock.symbol ?? stock.ticker ?? stock.name
            const amount = draft.budget * stock.weight / 100
            const shares = stock.close && stock.close > 0 ? Math.floor(amount / stock.close) : null
            const isLocked = locked.has(stock.stock_id)
            return <article className={`allocation-row ${isLocked ? 'is-locked' : ''}`} key={stock.stock_id} id={`allocation-${stock.stock_id}`}>
              <div className="allocation-company"><div className="allocation-company-title"><span className="allocation-swatch" style={{background: allocationColor(stock.stock_id)}} /><Link to={`/stock-research?stockId=${stock.stock_id}`} aria-label={`${symbol} ↗`}>{symbol}</Link><span className="listing-exchange">{stock.exchange}</span></div><span className="allocation-company-name">{stock.name}</span><div className="weight-editor"><input className="weight-slider" type="range" min="0.01" max="100" step="0.01" aria-label={`Adjust target for ${symbol}`} disabled={isLocked} value={Math.max(.01, stock.weight)} onPointerDown={() => { gesture.current = draft }} onChange={e => weight(stock.stock_id, Number(e.target.value))} onPointerUp={finishGesture} onPointerCancel={finishGesture} onBlur={finishGesture} style={{'--weight-color': allocationColor(stock.stock_id)} as CSSProperties} /><div className="weight-number"><input id={`weight-${stock.stock_id}`} aria-label={`Target weight for ${symbol}`} type="number" min="0.01" max="100" step="0.01" disabled={isLocked} value={stock.weight} onChange={e => weight(stock.stock_id, Number(e.target.value))} /><span>%</span></div><button className={`lock-weight ${isLocked ? 'active' : ''}`} aria-label={`${isLocked ? 'Unlock' : 'Lock'} target for ${symbol}`} aria-pressed={isLocked} title="Locked targets stay unchanged when rebalancing" onClick={() => setLocked(current => { const next = new Set(current); if (next.has(stock.stock_id)) next.delete(stock.stock_id); else next.add(stock.stock_id); return next })}><Icon name={isLocked ? 'lock' : 'unlock'} size={15} /></button></div></div>
              <div className="allocation-money"><strong>{money(amount, true, draft.currency)}</strong><small>{stock.weight.toFixed(2)}% of budget</small></div>
              <div className="allocation-shares"><strong>{shares == null ? '—' : shares.toLocaleString('en-IN')}</strong><small>{stock.close == null ? 'Price unavailable' : `at ${money(stock.close, true, draft.currency)}`}</small><small>{stock.date ?? ''}</small></div>
              <button className="remove-allocation" aria-label={`Remove ${symbol} from plan`} onClick={() => remove(stock)} title={`Remove ${symbol}`}><Icon name="close" size={16} /></button>
            </article>
          })}</fieldset>
          <p className="studio-table-note">* Whole-share estimates use saved closing prices. Fees, FX and taxes are excluded. These are planning targets; no orders are placed. Weight locks apply to this editing session.</p>
        </>}
      </> : baseline && <PlanComparison draft={draft} baseline={baseline} />}
      {invalid && <p className="studio-notice is-error" role="alert">Use positive targets with at most two decimals and a total of 100% or less. Budget must be positive; horizon must be 1–40 years.</p>}
      <footer className="studio-editor-footer"><span>A draft, separate from your actual holdings.</span><button className="studio-text-button" disabled={!loaded || invalid || asking || busy} onClick={() => reviewDialog.current?.showModal()}>Discuss this plan <Icon name="arrow" size={16} /></button></footer>
    </section>
    <aside className="studio-inspector" aria-label="Portfolio plan inspector"><section className="allocation-inspector"><header><span className="studio-kicker">YOUR ALLOCATION</span><span>{draft.currency}</span></header><div className="allocation-summary-value"><strong>{money(draft.budget, false, draft.currency)}</strong><span>{draft.stocks.length} companies + cash</span></div>
      <div className={`allocation-composition ${total > 100 ? 'overallocated' : ''}`} aria-label={`${total.toFixed(2)} percent equities, ${Math.max(0, cash).toFixed(2)} percent cash`}>{draft.stocks.map(stock => <button key={stock.stock_id} style={{width: `${stock.weight}%`, background: allocationColor(stock.stock_id)}} title={`${stock.symbol}: ${stock.weight.toFixed(2)}%`} aria-label={`Edit ${stock.symbol ?? stock.ticker} allocation`} onClick={() => focusStock(stock)} />)}{cash > 0 && <span className="cash-composition" style={{width: `${cash}%`}} />}</div>
      <div className="allocation-composition-labels"><span>Equities <strong>{total.toFixed(2)}%</strong></span><span>Cash <strong>{Math.max(0, cash).toFixed(2)}%</strong></span></div>
      <div className="inspector-facts"><div><span>Largest position</span><strong>{largest ? `${largest.symbol ?? largest.ticker} / ${largest.weight.toFixed(2)}%` : 'No positions'}</strong></div><div><span>Unallocated budget</span><strong>{money(draft.budget * Math.max(0, cash) / 100, true, draft.currency)}</strong></div><div><span>Sector labels available</span><strong>{total > 0 ? `${(knownSectors / total * 100).toFixed(0)}% of stock allocation` : '—'}</strong></div></div>
      {largest && <div className="inspector-observation"><span>{largest.weight > 25 ? 'CONCENTRATION CHECK' : 'POSITION CHECK'}</span><p>{largest.weight > 25 ? `${largest.symbol ?? largest.ticker} exceeds the 25% single-company check. This threshold is a prompt to review, not an optimal weight.` : 'No single company exceeds 25%. Shared business and sector exposures can still concentrate risk.'}</p></div>}
      {!!missingSectors && <p className="inspector-footnote">{missingSectors} {missingSectors === 1 ? 'company has' : 'companies have'} no sector label. Sector coverage does not establish diversification.</p>}
    </section>
    <section className="stress-test"><header><span className="studio-kicker">EXPLORE A DOWNSIDE</span><span>Hypothetical</span></header><h2>If equities fall <strong>{decline}%</strong></h2><label className="sr-only" htmlFor="market-decline">Market decline scenario</label><input id="market-decline" type="range" min="0" max="60" step="1" value={decline} onChange={e => setDecline(Number(e.target.value))} /><div className="stress-range-labels"><span>0%</span><span>60%</span></div><div className="stress-results" aria-live="polite"><div><span>Portfolio change</span><strong className="stress-loss">{invalid ? '—' : `${scenario.loss > 0 ? '−' : ''}${money(scenario.loss, false, draft.currency)}`}</strong></div><div><span>Budget remaining</span><strong>{invalid ? '—' : money(scenario.remaining, false, draft.currency)}</strong></div></div><p>Assumes every selected stock falls by the same percentage and cash stays unchanged. No forecast or probability is implied.</p></section>
    <section className="studio-next-step"><div><span className="studio-kicker">ANOTHER PERSPECTIVE</span><h3>Portfolio review</h3><p>{available ? 'Ask about this allocation with your linked news as context.' : 'Use the rules-based coach to check concentration and gaps.'}</p></div><button disabled={!loaded || invalid || asking || busy} onClick={() => reviewDialog.current?.showModal()}>Discuss plan <Icon name="arrow" size={17} /></button></section>
    </aside></div>
    <p className="studio-save-note">One saved draft per account. Saving a different market replaces that draft. Market switches keep your current selections in this editing session; no currency conversion is applied.</p>
    <dialog ref={reviewDialog} className="plan-review-dialog plan-assistant" aria-labelledby="plan-review-title" onClick={e => { if (e.target === e.currentTarget) reviewDialog.current?.close() }}><header><div><span className="studio-kicker">PORTFOLIO REVIEW</span><h2 id="plan-review-title">Discuss your allocation</h2></div><button aria-label="Close portfolio review" onClick={() => reviewDialog.current?.close()}><Icon name="close" /></button></header><div className="plan-review-context"><strong>{draft.stocks.length} companies / {draft.currency}</strong><span>{available ? 'AI research · saved plan & linked headlines' : 'Rules-based allocation coach · no AI connection'}</span></div><div className="plan-review-body"><p>What would make this allocation work for your goal?</p><div className="review-question-list">{['Check concentration and gaps in this plan.', 'How do these weights fit my time horizon?', 'What should I research before choosing these stocks?'].map(q => <button key={q} onClick={() => setQuestion(q)}>{q}<Icon name="arrow" size={15} /></button>)}</div>{reply && <div className="assistant-answer" aria-live="polite"><strong>Review of your saved draft</strong><div>{reply.answer}</div><div className="assistant-sources">{reply.sources.filter(s => /^https:\/\//.test(s.url)).map(s => <a key={s.id} href={s.url} target="_blank" rel="noopener noreferrer">{s.id} · {s.headline} ↗</a>)}</div></div>}{error && <p className="studio-notice is-error" role="alert">{error}</p>}</div><form onSubmit={e => { e.preventDefault(); void ask() }}><label htmlFor="portfolio-question">Discuss this portfolio</label><textarea id="portfolio-question" maxLength={320} value={question} onChange={e => setQuestion(e.target.value)} placeholder="My goal is… What am I missing?" /><button className="studio-button" disabled={invalid || asking || question.trim().length < 3}>{asking ? 'Reviewing…' : 'Save & ask agent'}</button><small>The current allocation is saved before the review.</small></form></dialog>
  </div>
}

function PlanComparison({draft, baseline}: {draft: PlanDraft; baseline: PlanDraft}) {
  const rows = [...new Map([...baseline.stocks, ...draft.stocks].map(s => [s.stock_id, s])).values()]
  return <div className="plan-comparison"><header className="studio-section-heading"><div><h2>Allocation changes</h2><p>Saved targets compared with the working draft. No trades are made.</p></div></header><div className="comparison-budget"><div><span>Saved budget</span><strong>{money(baseline.budget, false, baseline.currency)}</strong></div><div><span>Working budget</span><strong>{money(draft.budget, false, draft.currency)}</strong></div></div><div className="comparison-table"><div className="comparison-head"><span>Company</span><span>Saved</span><span>Working</span><span>Change</span></div>{rows.map(stock => { const before = baseline.stocks.find(s => s.stock_id === stock.stock_id)?.weight ?? 0; const after = draft.stocks.find(s => s.stock_id === stock.stock_id)?.weight ?? 0; const delta = after - before; return <div className="comparison-row" key={stock.stock_id}><strong>{stock.symbol ?? stock.ticker}</strong><span>{before.toFixed(2)}%</span><span>{after.toFixed(2)}%</span><strong className={delta !== 0 ? 'has-change' : ''}>{delta > 0 ? '+' : ''}{delta.toFixed(2)} pp</strong></div> })}<div className="comparison-row comparison-cash"><strong>Cash</strong><span>{(100 - totalWeight(baseline.stocks)).toFixed(2)}%</span><span>{(100 - totalWeight(draft.stocks)).toFixed(2)}%</span><span>—</span></div></div><p className="studio-table-note">pp = percentage points. Review changes before saving; Save draft replaces the comparison baseline.</p></div>
}
