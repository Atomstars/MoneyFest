import { useEffect, useState, type ReactNode } from 'react'
import { OUTCOME_HELP, OUTCOME_LABEL } from '../lib/format'

/** Outcome chip. Neutral by default -- an outcome is a category, not a verdict,
 *  so it never borrows the status palette or the up/down money colours. The one
 *  exception is DATA_ISSUE, which is a genuine warning about our own data. */
export function OutcomeChip({ outcome }: { outcome: string | null }) {
  if (!outcome) return null
  const isWarn = outcome === 'DATA_ISSUE'
  return (
    <span
      title={`${outcome} — ${OUTCOME_HELP[outcome] ?? ''}`}
      className="inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[11px] font-medium whitespace-nowrap"
      style={{
        background: isWarn
          ? 'color-mix(in srgb, var(--warning) 16%, transparent)'
          : 'color-mix(in srgb, var(--text-primary) 6%, transparent)',
        color: isWarn ? 'var(--text-primary)' : 'var(--text-secondary)',
        border: '1px solid var(--border)',
      }}
    >
      {OUTCOME_LABEL[outcome] ?? outcome}
    </span>
  )
}

/** Confidence is rendered with weight and a label, never colour alone. */
export function ConfidenceBadge({ level }: { level: string | null }) {
  if (!level) return null
  const weight = level === 'HIGH' ? 700 : level === 'MEDIUM' ? 600 : 500
  const opacity = level === 'LOW' ? 0.75 : 1
  return (
    <span
      className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] tracking-wide uppercase"
      style={{
        fontWeight: weight, opacity,
        border: '1px solid var(--border)',
        color: 'var(--text-secondary)',
      }}
    >
      {level} confidence
    </span>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`card p-5 ${className}`}>{children}</section>
}

export function CardTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <header className="mb-4 flex items-baseline justify-between gap-3">
      <h2 className="text-sm font-semibold tracking-tight">{children}</h2>
      {aside && <div className="text-xs" style={{ color: 'var(--text-muted)' }}>{aside}</div>}
    </header>
  )
}

export function Delta({ value, children }: { value: number | null | undefined; children: ReactNode }) {
  const dir = value == null || !Number.isFinite(value) || value === 0 ? 'flat' : value > 0 ? 'up' : 'down'
  return (
    <span
      className="tnum font-semibold"
      style={{ color: dir === 'up' ? 'var(--up)' : dir === 'down' ? 'var(--down)' : 'var(--text-muted)' }}
    >
      {children}
    </span>
  )
}

export function Skeleton({ className = '' }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-md ${className}`}
      style={{ background: 'color-mix(in srgb, var(--text-primary) 8%, transparent)' }}
    />
  )
}

export function ErrorNote({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <Card>
      <p className="text-sm font-medium">Couldn't load this</p>
      <p className="mt-1 text-sm" style={{ color: 'var(--text-secondary)' }}>{error}</p>
      <p className="mt-2 text-xs" style={{ color: 'var(--text-muted)' }}>
        Please check your connection and try again.
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-3 rounded-lg px-3 py-1.5 text-sm font-medium"
          style={{ background: 'var(--series-1)', color: '#fff' }}
        >
          Retry
        </button>
      )}
    </Card>
  )
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<'light' | 'dark' | null>(
    () => (localStorage.getItem('theme') as 'light' | 'dark' | null) ?? null,
  )

  useEffect(() => {
    const root = document.documentElement
    if (theme) {
      root.setAttribute('data-theme', theme)
      localStorage.setItem('theme', theme)
    } else {
      root.removeAttribute('data-theme')
      localStorage.removeItem('theme')
    }
  }, [theme])

  const isDark =
    theme === 'dark' ||
    (theme === null && window.matchMedia?.('(prefers-color-scheme: dark)').matches)

  return (
    <button
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
      aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
      title={isDark ? 'Light theme' : 'Dark theme'}
      className="grid size-9 place-items-center rounded-lg transition-colors"
      style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
    >
      {isDark ? (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19" strokeLinecap="round" />
        </svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" strokeLinejoin="round" />
        </svg>
      )}
    </button>
  )
}
