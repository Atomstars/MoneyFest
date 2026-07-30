import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { APP_NAME } from '../components/Shell'
import { ThemeToggle } from '../components/ui'

/**
 * Title page.
 *
 * IMPORTANT: the sign-in form here is a DESIGN PLACEHOLDER. It authenticates
 * nothing, stores nothing, and sends nothing anywhere -- "Continue" just routes to
 * /home. It deliberately does not accept a password: collecting one would imply a
 * security guarantee that does not exist yet. The real auth pass replaces this
 * whole component, and the backend's existing WEB_TOKEN seatbelt is what actually
 * gates the API today.
 */
export function Landing() {
  const nav = useNavigate()
  const [email, setEmail] = useState('')

  return (
    <div className="relative min-h-full overflow-hidden">
      {/* Ambient wash -- decorative, sits behind everything */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(60rem 30rem at 15% -10%, color-mix(in srgb, var(--series-1) 22%, transparent), transparent 60%),' +
            'radial-gradient(45rem 26rem at 95% 10%, color-mix(in srgb, var(--series-3) 16%, transparent), transparent 60%)',
        }}
      />

      <div className="relative mx-auto flex min-h-screen max-w-6xl flex-col px-5">
        {/* Brand bar */}
        <header className="flex items-center justify-between py-5">
          <div className="flex items-center gap-2">
            <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
              <rect x="2" y="2" width="20" height="20" rx="6" fill="var(--series-1)" />
              <path d="M7 16.5V8.2l5 5.4 5-5.4v8.3" fill="none" stroke="#fff"
                    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span className="text-base font-semibold tracking-tight">{APP_NAME}</span>
          </div>
          <ThemeToggle />
        </header>

        <div className="grid flex-1 items-center gap-12 py-10 lg:grid-cols-[1.1fr_0.9fr]">
          {/* Pitch */}
          <section className="rise">
            <p
              className="mb-4 inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium"
              style={{
                background: 'color-mix(in srgb, var(--series-1) 12%, transparent)',
                color: 'var(--text-secondary)',
                border: '1px solid var(--border)',
              }}
            >
              NSE &amp; BSE · explanation engine
            </p>

            <h1 className="text-4xl leading-[1.08] font-semibold tracking-tight sm:text-6xl">
              Your portfolio,
              <br />
              <span style={{ color: 'var(--series-1)' }}>explained.</span>
            </h1>

            <p className="mt-5 max-w-lg text-base leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
              Every broker shows you that a stock fell 4%. {APP_NAME} tells you
              <em> why</em> — traced to a filing, a macro move, or an honest
              &ldquo;no clear driver&rdquo;. Every claim is cited. Nothing is invented.
            </p>

            <ul className="mt-7 grid max-w-lg gap-3 sm:grid-cols-3">
              {[
                ['Cited, not guessed', 'Each driver links to the filing or data behind it'],
                ['Knows when to shut up', 'Most days are noise — and it says so'],
                ['Direction per stock', 'The same news is good for one holding, bad for another'],
              ].map(([t, d]) => (
                <li key={t} className="card p-3">
                  <div className="text-[13px] font-semibold">{t}</div>
                  <div className="mt-1 text-xs leading-snug" style={{ color: 'var(--text-muted)' }}>{d}</div>
                </li>
              ))}
            </ul>
          </section>

          {/* Sign-in — visual only */}
          <section className="rise">
            <div className="card mx-auto w-full max-w-sm p-6">
              <h2 className="text-lg font-semibold tracking-tight">Sign in</h2>
              <p className="mt-1 text-sm" style={{ color: 'var(--text-muted)' }}>
                Continue to your dashboard.
              </p>

              <form
                className="mt-5 space-y-3"
                onSubmit={(e) => { e.preventDefault(); nav('/home') }}
              >
                <label className="block">
                  <span className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                    Email
                  </span>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    autoComplete="off"
                    className="w-full rounded-lg px-3 py-2.5 text-sm outline-none"
                    style={{
                      background: 'var(--plane)',
                      border: '1px solid var(--border)',
                      color: 'var(--text-primary)',
                    }}
                  />
                </label>

                <button
                  type="submit"
                  className="w-full rounded-lg py-2.5 text-sm font-semibold transition-opacity hover:opacity-92"
                  style={{ background: 'var(--series-1)', color: '#fff' }}
                >
                  Continue
                </button>
              </form>

              <p
                className="mt-4 rounded-lg px-3 py-2 text-[11px] leading-snug"
                style={{
                  background: 'color-mix(in srgb, var(--warning) 15%, transparent)',
                  color: 'var(--text-secondary)',
                }}
              >
                <strong>Preview build.</strong> This form is a design placeholder — it
                doesn&rsquo;t authenticate, store, or send anything. Real sign-in comes later.
              </p>

              <button
                onClick={() => nav('/home')}
                className="mt-3 w-full text-xs underline underline-offset-2"
                style={{ color: 'var(--text-muted)' }}
              >
                Skip and explore
              </button>
            </div>
          </section>
        </div>

        <footer className="py-6 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
          Explanation only — not investment advice.
        </footer>
      </div>
    </div>
  )
}
