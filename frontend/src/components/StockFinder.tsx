import { useEffect, useState } from 'react'
import { api, type StockRow } from '../lib/api'
import { Icon } from './Icon'

export function StockFinder({ market = 'ALL', onSelect, initialQuery = '', label = 'Find a stock' }: { market?: string; onSelect: (stock: StockRow) => void; initialQuery?: string; label?: string }) {
  const [query, setQuery] = useState(initialQuery)
  const [rows, setRows] = useState<StockRow[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { setQuery(initialQuery) }, [initialQuery])
  useEffect(() => {
    let active = true
    setRows([]); setError(''); setBusy(!!query.trim())
    if (!query.trim()) return
    const timer = setTimeout(() => {
      api.stocks(query, 'all', 'ALL', 0, market).then(r => { if (active) setRows(r.slice(0, 8)) }).catch(e => { if (active) setError(e.message) }).finally(() => { if (active) setBusy(false) })
    }, 250)
    return () => { active = false; clearTimeout(timer) }
  }, [query, market])
  return <div className="stock-finder"><label className="search-field"><Icon name="search" /><input type="search" aria-label={label} placeholder="Company name or ticker…" maxLength={100} value={query} onChange={e => setQuery(e.target.value)} /></label>
    {busy && <p className="data-caption" role="status">Searching catalog…</p>}{error && <p role="alert" className="status-note">{error}</p>}
    {!!query.trim() && !busy && !error && <div className="finder-results">{rows.map(s => <button key={s.stock_id} onClick={() => { onSelect(s); setQuery('') }}><span><strong>{s.symbol ?? s.ticker}</strong><small>{s.name}</small></span><span className="outline-badge">{s.exchange} · {s.currency ?? 'INR'}</span><Icon name="plus" size={16} /></button>)}{!rows.length && <p className="data-caption">No matching stocks. Try another company or symbol.</p>}</div>}
  </div>
}
