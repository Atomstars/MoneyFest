import { useEffect, useState, type FormEvent } from 'react'
import { api, type Position, type StockRow, type Currency } from '../lib/api'

export function HoldingEditor({ position, onSaved, onCancel, currency = 'INR' }: {
  currency?: Currency; position: Position | null; onSaved: () => void; onCancel: () => void
}) {
  const [stocks, setStocks] = useState<StockRow[]>([])
  const [ticker, setTicker] = useState(position?.ticker ?? '')
  const [query, setQuery] = useState(position?.ticker ?? '')
  const [searching, setSearching] = useState(false)
  const [quantity, setQuantity] = useState(position ? String(position.qty) : '')
  const [cost, setCost] = useState(position ? String(position.avg_cost) : '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let active = true
    const timer = setTimeout(() => {
      setSearching(true)
      api.stocks(query, 'all', 'ALL', 0, currency === 'USD' ? 'US' : 'IN').then(data => { if (active) { setStocks(data.slice(0, 40)); setError(null) } })
        .catch(e => { if (active) setError(e.message) }).finally(() => { if (active) setSearching(false) })
    }, 250)
    return () => { active = false; clearTimeout(timer) }
  }, [query, currency])
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(null)
    try { await api.putHolding(ticker, quantity, cost); onSaved() }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not save holding.') }
    finally { setBusy(false) }
  }
  return <form onSubmit={submit} className="holding-editor card p-5">
    <h3 className="mb-3 text-sm font-semibold">{position ? 'Edit holding' : 'Add a holding'}</h3>
    {!position && <label className="block text-xs font-medium mb-4">Find a stock
      <input autoFocus className="account-input mt-1.5" type="search" placeholder="Search companies or symbols…" maxLength={100} value={query} onChange={e => { setQuery(e.target.value); setTicker('') }} />
    </label>}
    <div className="grid gap-3 sm:grid-cols-3">
      <label className="text-xs font-medium">Stock
        <select required disabled={!!position || busy} value={ticker} onChange={(e) => setTicker(e.target.value)} className="account-input mt-1.5">
          <option value="">{searching ? 'Searching…' : stocks.length ? 'Select a stock' : 'No matching stocks'}</option>
          {position && !stocks.some(s => s.ticker === ticker) && <option value={ticker}>{ticker}</option>}
          {stocks.map((s) => <option key={s.stock_id} value={s.ticker ?? ''}>{s.ticker} · {s.name}</option>)}
        </select>
      </label>
      <label className="text-xs font-medium">Quantity
        <input required type="number" min="0.000001" max="99999999999999" step="0.000001" value={quantity} disabled={busy} onChange={(e) => setQuantity(e.target.value)} className="account-input mt-1.5" />
      </label>
      <label className="text-xs font-medium">Average purchase price ({currency === 'USD' ? '$' : '₹'})
        <input required type="number" min="0" max="99999999999999" step="0.000001" value={cost} disabled={busy} onChange={(e) => setCost(e.target.value)} className="account-input mt-1.5" />
      </label>
    </div>
    <p className="mt-3 text-xs" style={{ color: 'var(--text-muted)' }}>Current holdings · prices and news refresh after saving.</p>
    {error && <p role="alert" className="mt-3 text-sm" style={{ color: 'var(--down)' }}>{error}</p>}
    <div className="mt-3 flex gap-3">
      <button disabled={busy} type="submit" className="action-button">{busy ? 'Saving…' : 'Save holding'}</button>
      <button disabled={busy} type="button" onClick={onCancel} className="text-sm">Cancel</button>
    </div>
  </form>
}
