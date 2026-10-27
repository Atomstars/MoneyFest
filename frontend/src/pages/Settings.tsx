import { useEffect, useState, type ReactNode } from 'react'
import { PageHeader } from '../components/Shell'
import { APP_NAME, SECTIONS } from '../lib/app'
import { Card } from '../components/ui'
import { api } from '../lib/api'

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
  const [saving, setSaving] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)

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
    api.health()
      .then((j) => setHealth(j.status === 'ok' ? 'Connected' : String(j.status)))
      .catch(() => setHealth('Unreachable'))
  }, [])
  useEffect(() => {
    let active = true
    api.preferences().then((prefs) => {
      if (!active) return
      setAlertLevel(prefs.alert_level); setQuietMarket(prefs.quiet_market); setDigest(prefs.daily_digest); setLoaded(true)
    }).catch((e) => { if (active) setError(e.message) })
    return () => { active = false }
  }, [retry])
  async function save() {
    setSaving(true); setStatus(null); setError(null)
    try { await api.savePreferences({ alert_level: alertLevel, quiet_market: quietMarket, daily_digest: digest }); setStatus('Preferences saved.') }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not save preferences.') }
    finally { setSaving(false) }
  }

  return (
    <>
      <PageHeader title={SECTIONS['/settings'].title}  />

      <div className="grid gap-5 lg:grid-cols-2">
        <Section title="Appearance" description="">
          <Row
            label="Theme"
            hint="System follows your OS setting."
            control={<Segmented value={theme} options={THEMES} onChange={setTheme} />}
          />
        </Section>

        <Section title="Delivery preferences" description="Saved preferences for future verified-driver delivery.">
          <fieldset disabled={!loaded || saving}>
          <Row
            label="Alert level"
            hint="Explained-only skips routine days."
            control={<Segmented value={alertLevel} options={ALERTS} onChange={(v) => { setAlertLevel(v); setStatus(null) }} />}
          />
          <Row
            label="Quiet market days"
            hint="Suppress alerts when the whole market moved."
            control={<Toggle on={quietMarket} onChange={(v) => { setQuietMarket(v); setStatus(null) }} label="Quiet market days" />}
          />
          <Row
            label="Daily digest"
            hint="One summary instead of per-stock alerts."
            control={<Toggle on={digest} onChange={(v) => { setDigest(v); setStatus(null) }} label="Daily digest" />}
          />
          </fieldset>
          <button className="action-button mt-3" disabled={!loaded || saving} onClick={() => void save()}>{saving ? 'Saving…' : 'Save preferences'}</button>
          {status && <p role="status" className="mt-2 text-xs">{status}</p>}
          {error && <p role="alert" className="mt-2 text-xs">{error} {!loaded && <button onClick={() => { setError(null); setRetry((n) => n + 1) }}>Retry</button>}</p>}
          <p className="mt-3 text-xs" style={{ color: 'var(--text-muted)' }}>Company news updates appear in News & alerts every 15 minutes while the server runs. Email, push and verified-driver delivery are not connected; these preferences are saved for later.</p>
        </Section>

        <Section title="Data & engine" description="">
          <Row label="Connection" hint="Your account and portfolio server" control={
            <span className="text-xs font-medium"
                  style={{ color: health === 'Connected' ? 'var(--up)' : 'var(--down)' }}>
              {health}
            </span>
          } />
          <Row label="Prices" hint="Yahoo Finance · completed daily closes"
               control={<span className="text-xs" style={{ color: 'var(--text-muted)' }}>Best effort</span>} />
          <Row label="News" hint="Google News · publisher links"
               control={<span className="text-xs" style={{ color: 'var(--text-muted)' }}>Every 15 min</span>} />
        </Section>

        <Section title="About" description="">
          <Row label={APP_NAME} hint="Portfolio & news workspace" control={<span className="outline-badge">Preview</span>} />
          <Row label="Coverage" hint="Upstox NSE & BSE equity catalog" control={<span className="text-xs muted">India</span>} />
          <p className="text-xs muted pt-3">Headline sentiment is a quick signal. A cause for a price move requires verified evidence.</p>
        </Section>
      </div>

      <p className="mt-6 pb-2 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
        Explanation only — not investment advice.
      </p>

    </>
  )
}
