import { NavLink, Outlet, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import { ThemeToggle } from './ui'

export const APP_NAME = 'Moneyfest'

/** Every route declares its own title, so the header is never guessing. */
export const SECTIONS: Record<string, { title: string; subtitle: string }> = {
  '/home': { title: 'Home', subtitle: 'Every stock being tracked' },
  '/dashboard': { title: 'Dashboard', subtitle: 'Your holdings, valued and explained' },
  '/settings': { title: 'Settings', subtitle: 'Preferences, data and delivery' },
}

const NAV = [
  {
    to: '/home',
    label: 'Home',
    icon: (
      <path d="M3 10.5 12 3l9 7.5M5.5 9.5V20h13V9.5" strokeLinecap="round" strokeLinejoin="round" />
    ),
  },
  {
    to: '/dashboard',
    label: 'Dashboard',
    icon: (
      <path d="M4 19V10M10 19V5M16 19v-6M21 19H3" strokeLinecap="round" strokeLinejoin="round" />
    ),
  },
  {
    to: '/settings',
    label: 'Settings',
    icon: (
      <>
        <circle cx="12" cy="12" r="3.2" />
        <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.2 5.2l1.4 1.4M17.4 17.4l1.4 1.4M18.8 5.2l-1.4 1.4M6.6 17.4l-1.4 1.4"
              strokeLinecap="round" />
      </>
    ),
  },
]

function Wordmark() {
  return (
    <NavLink to="/home" className="flex items-center gap-2" aria-label={`${APP_NAME} home`}>
      <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
        <rect x="2" y="2" width="20" height="20" rx="6" fill="var(--series-1)" />
        <path d="M7 16.5V8.2l5 5.4 5-5.4v8.3" fill="none" stroke="#fff"
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="text-[15px] font-semibold tracking-tight">{APP_NAME}</span>
    </NavLink>
  )
}

/** Page header. Each section states its own title and one line of purpose. */
export function PageHeader({ title, subtitle, aside }: {
  title: string; subtitle?: string; aside?: ReactNode
}) {
  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{title}</h1>
        {subtitle && (
          <p className="mt-0.5 text-sm" style={{ color: 'var(--text-muted)' }}>{subtitle}</p>
        )}
      </div>
      {aside}
    </header>
  )
}

export function Shell() {
  const { pathname } = useLocation()
  const section = SECTIONS[pathname]

  return (
    <div className="min-h-full">
      {/* ---- Top bar: brand left, nav centre (desktop), theme right ---- */}
      <header
        className="sticky top-0 z-30 backdrop-blur-xl"
        style={{
          background: 'color-mix(in srgb, var(--plane) 85%, transparent)',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-5 py-3">
          <Wordmark />

          <nav className="ml-4 hidden gap-1 sm:flex" aria-label="Main">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                className="rounded-lg px-3 py-1.5 text-sm font-medium transition-colors"
                style={({ isActive }) => ({
                  background: isActive
                    ? 'color-mix(in srgb, var(--text-primary) 7%, transparent)'
                    : 'transparent',
                  color: isActive ? 'var(--text-primary)' : 'var(--text-muted)',
                })}
              >
                {n.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            {section && (
              <span className="hidden text-xs md:inline" style={{ color: 'var(--text-muted)' }}>
                {section.title}
              </span>
            )}
            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* pb-24 leaves room for the mobile bottom bar */}
      <main className="mx-auto max-w-6xl px-5 py-6 pb-24 sm:pb-6">
        <Outlet />
      </main>

      {/* ---- Bottom bar: mobile only, thumb-reachable ---- */}
      <nav
        className="fixed inset-x-0 bottom-0 z-30 backdrop-blur-xl sm:hidden"
        aria-label="Main"
        style={{
          background: 'color-mix(in srgb, var(--plane) 92%, transparent)',
          borderTop: '1px solid var(--border)',
          paddingBottom: 'env(safe-area-inset-bottom)',
        }}
      >
        <div className="flex">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className="flex flex-1 flex-col items-center gap-1 py-2.5 text-[11px] font-medium"
              style={({ isActive }) => ({
                color: isActive ? 'var(--series-1)' : 'var(--text-muted)',
              })}
            >
              {({ isActive }) => (
                <>
                  <svg width="21" height="21" viewBox="0 0 24 24" fill="none"
                       stroke="currentColor" strokeWidth={isActive ? 2.2 : 1.8} aria-hidden="true">
                    {n.icon}
                  </svg>
                  {n.label}
                </>
              )}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  )
}
