import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type SecurityRow } from '../lib/api'

/**
 * Global ticker search, in the top bar on every screen.
 *
 * This is the main way into the ~5,000-name universe, so it behaves the way a
 * broker app's search does: type anywhere, arrow keys to move, Enter to open,
 * Escape to dismiss, and `/` from anywhere on the page to focus it.
 *
 * Picking a result that is not yet tracked routes to the stock page by ISIN. The
 * promotion and price warm-up happen there, behind a visible warming state, rather
 * than making the user wait inside this dropdown with nothing to look at.
 */
export function SearchBar() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SecurityRow[]>([])
  const [open, setOpen] = useState(false)
  const [cursor, setCursor] = useState(0)
  const [loading, setLoading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const boxRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  // `/` focuses search from anywhere, unless the user is already typing somewhere.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement
      const typing = el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement
      if (e.key === '/' && !typing) {
        e.preventDefault()
        inputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  // Debounced so a fast typist fires one request, not eight.
  useEffect(() => {
    const term = query.trim()
    if (term.length < 1) {
      setResults([])
      setLoading(false)
      return
    }
    setLoading(true)
    let alive = true
    const timer = setTimeout(() => {
      api.universeSearch(term, undefined, 8)
        .then((r) => {
          if (!alive) return
          setResults(r.results)
          setCursor(0)
          setOpen(true)
        })
        .catch(() => alive && setResults([]))
        .finally(() => alive && setLoading(false))
    }, 180)
    return () => { alive = false; clearTimeout(timer) }
  }, [query])

  const choose = (row: SecurityRow) => {
    setOpen(false)
    setQuery('')
    // Tracked names route by stock id; the rest by ISIN, which the stock page
    // resolves (promoting and warming up as needed).
    navigate(row.stock_id ? `/stock/${row.stock_id}` : `/stock/isin/${row.isin}`)
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { setOpen(false); inputRef.current?.blur(); return }
    if (!open || results.length === 0) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setCursor((c) => (c + 1) % results.length) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setCursor((c) => (c - 1 + results.length) % results.length) }
    if (e.key === 'Enter') { e.preventDefault(); choose(results[cursor]) }
  }

  return (
    <div ref={boxRef} className="relative min-w-0 flex-1 sm:max-w-sm">
      <div className="relative">
        <svg
          className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2"
          width="15" height="15" viewBox="0 0 24 24" fill="none"
          stroke="var(--text-muted)" strokeWidth="2" aria-hidden="true"
        >
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" strokeLinecap="round" />
        </svg>
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => results.length && setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder="Search any NSE or BSE stock"
          aria-label="Search all listed stocks"
          role="combobox"
          aria-expanded={open}
          aria-controls="search-results"
          className="w-full rounded-lg py-1.5 pr-8 pl-8 text-sm outline-none"
          style={{
            background: 'var(--surface-1)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
          }}
        />
        {!query && (
          <kbd
            className="pointer-events-none absolute top-1/2 right-2.5 hidden -translate-y-1/2 rounded px-1.5 text-[10px] sm:block"
            style={{ border: '1px solid var(--border)', color: 'var(--text-muted)' }}
          >
            /
          </kbd>
        )}
      </div>

      {open && (
        <div
          id="search-results"
          role="listbox"
          className="absolute top-full right-0 left-0 z-50 mt-1.5 overflow-hidden rounded-xl shadow-lg"
          style={{ background: 'var(--plane)', border: '1px solid var(--border)' }}
        >
          {results.length === 0 ? (
            <p className="px-3 py-3 text-xs" style={{ color: 'var(--text-muted)' }}>
              {loading ? 'Searching…' : `No listed stock matches “${query}”.`}
            </p>
          ) : (
            results.map((row, i) => (
              <button
                key={row.isin}
                role="option"
                aria-selected={i === cursor}
                onMouseEnter={() => setCursor(i)}
                onClick={() => choose(row)}
                className="flex w-full items-center gap-2 px-3 py-2 text-left"
                style={{
                  background: i === cursor
                    ? 'color-mix(in srgb, var(--text-primary) 6%, transparent)'
                    : 'transparent',
                }}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate text-sm font-medium">
                      {row.symbol_nse ?? row.scrip_bse}
                    </span>
                    {row.stock_id && (
                      <span
                        className="rounded px-1 text-[9px] font-medium"
                        style={{
                          background: 'color-mix(in srgb, var(--series-1) 18%, transparent)',
                          color: 'var(--text-secondary)',
                        }}
                      >
                        tracked
                      </span>
                    )}
                  </div>
                  <p className="truncate text-[11px]" style={{ color: 'var(--text-muted)' }}>
                    {row.name}
                  </p>
                </div>
                <span className="shrink-0 text-[10px]" style={{ color: 'var(--text-muted)' }}>
                  {row.exchanges}
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}
