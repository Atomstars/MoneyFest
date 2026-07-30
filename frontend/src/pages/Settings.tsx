import { useEffect, useState, type ReactNode } from 'react'
import { APP_NAME, PageHeader, SECTIONS } from '../components/Shell'
import { Card } from '../components/ui'

/** A titled settings section. Every group states what it governs. */
function Section({ title, description, children }: {
  title: string; description: string; children: ReactNode
}) {
  return (
    <Card className="rise">
      <header className="mb-4">
        <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
        <p className="mt-0.5 text-xs" style={{ color: 'var(--text-muted)' }}>{description}</p>
      </header>
      <div className="space-y-1">{children}</div>
    </Card>
  )
}

function Row({ label, hint, control }: { label: string; hint?: string; control: ReactNode }) {
  return (
    <div
      className="flex items-center justify-between gap-4 border-t py-3 first:border-t-0 first:pt-0"
      style={{ borderColor: 'var(--border)' }}
    >
      <div className="min-w-0">
        <div className="text-sm font-medium">{label}</div>
        {hint && <div className="mt-0.5 text-xs" style={{ color: 'var(--text-muted)' }}>{hint}</div>}
      </div>
      <div className="shrink-0">{control}</div>
    </div>
  )
}

function Toggle({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={() => onChange(!on)}
      className="relative h-6 w-11 rounded-full transition-colors"
      style={{
        background: on ? 'var(--series-1)' : 'color-mix(in srgb, var(--text-primary) 18%, transparent)',
      }}
    >
      <span
        className="absolute top-0.5 size-5 rounded-full bg-white transition-transform"
        style={{ transform: on ? 'translateX(22px)' : 'translateX(2px)' }}
      />
    </button>
  )
}

function Segmented<T extends string>({ value, options, onChange }: {
  value: T; options: readonly (readonly [T, string])[]; onChange: (v: T) => void
}) {
  return (
    <div className="flex gap-1">
      {options.map(([k, label]) => (
        <button
          key={k}
          onClick={() => onChange(k)}
          className="rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors"
          style={{
            background: value === k
              ? 'color-mix(in srgb, var(--text-primary) 8%, transparent)' : 'transparent',
            color: value === k ? 'var(--text-primary)' : 'var(--text-muted)',
            border: '1px solid var(--border)',
          }}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

const THEMES = [['system', 'System'], ['light', 'Light'], ['dark', 'Dark']] as const
const ALERTS = [['ALL', 'All'], ['EXPLAINED_ONLY', 'Explained'], ['HIGH_ONLY', 'High only']] as const

export function Settings() {
  const [theme, setTheme] = useState<'system' | 'light' | 'dark'>(
    () => (localStorage.getItem('theme') as 'light' | 'dark' | null) ?? 'system',
  )
  const [alertLevel, setAlertLevel] = useState<(typeof ALERTS)[number][0]>('ALL')
  const [quietMarket, setQuietMarket] = useState(false)
  const [digest, setDigest] = useState(false)
  const [health, setHealth] = useState<string>('checking…')

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') {
      root.removeAttribute('data-theme')
      localStorage.removeItem('theme')
    } else {
      root.setAttribute('data-theme', theme)
      localStorage.setItem('theme', theme)
    }
  }, [theme])

  useEffect(() => {
    fetch('/health')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((j) => setHealth(j.status === 'ok' ? 'Connected' : String(j.status)))
      .catch(() => setHealth('Unreachable'))
  }, [])

  return (
    <>
      <PageHeader title={SECTIONS['/settings'].title} subtitle={SECTIONS['/settings'].subtitle} />

      <div className="grid gap-5 lg:grid-cols-2">
        <Section title="Appearance" description="How the interface looks on this device.">
          <Row
            label="Theme"
            hint="System follows your OS setting."
            control={<Segmented value={theme} options={THEMES} onChange={setTheme} />}
          />
        </Section>

        <Section title="Alerts" description="What reaches you, and how noisy it is.">
          <Row
            label="Alert level"
            hint="Explained-only skips routine days."
            control={<Segmented value={alertLevel} options={ALERTS} onChange={setAlertLevel} />}
          />
          <Row
            label="Quiet market days"
            hint="Suppress alerts when the whole market moved."
            control={<Toggle on={quietMarket} onChange={setQuietMarket} label="Quiet market days" />}
          />
          <Row
            label="Daily digest"
            hint="One summary instead of per-stock alerts."
            control={<Toggle on={digest} onChange={setDigest} label="Daily digest" />}
          />
        </Section>

        <Section title="Data & engine" description="Where the numbers come from.">
          <Row label="API" hint="FastAPI backend on localhost:8000" control={
            <span className="text-xs font-medium"
                  style={{ color: health === 'Connected' ? 'var(--up)' : 'var(--down)' }}>
              {health}
            </span>
          } />
          <Row label="Prices" hint="yfinance adjusted closes, end-of-day"
               control={<span className="text-xs" style={{ color: 'var(--text-muted)' }}>EOD</span>} />
          <Row label="Filings" hint="NSE + BSE corporate announcements"
               control={<span className="text-xs" style={{ color: 'var(--text-muted)' }}>Tier 1</span>} />
        </Section>

        <Section title="About" description={`What ${APP_NAME} does, and deliberately does not do.`}>
          <Row label="Version" hint="Preview build"
               control={<span className="text-xs" style={{ color: 'var(--text-muted)' }}>0.5.0</span>} />
          <div className="border-t pt-3" style={{ borderColor: 'var(--border)' }}>
            <p className="text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
              {APP_NAME} explains why a stock moved, citing filings, macro data and news.
              It does <strong>not</strong> predict prices, score stocks, or recommend trades —
              those are deliberate omissions, not missing features. &ldquo;No clear
              driver&rdquo; is a valid answer and you will see it often.
            </p>
          </div>
        </Section>
      </div>

      <p className="mt-6 pb-2 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
        Explanation only — not investment advice.
      </p>

      <p className="pb-4 text-center text-[11px]" style={{ color: 'var(--text-muted)' }}>
        Alert preferences are local to this preview and aren&rsquo;t saved to the server yet.
      </p>
    </>
  )
}
