import { NavLink, Outlet, useLocation, useNavigate, Link } from 'react-router-dom'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { api, type User } from '../lib/api'
import { ThemeToggle } from './ui'
import { Icon } from './Icon'
import { WorkspaceAssistant, WorkspaceSearch } from './WorkspaceTools'

const NAV = [
  { to: '/home', label: 'Explore stocks', icon: 'markets' },
  { to: '/us-stocks', label: 'US stocks', icon: 'globe' },
  { to: '/dashboard', label: 'Portfolio', icon: 'portfolio' },
  { to: '/portfolio-lab', label: 'Portfolio builder', icon: 'search' },
  { to: '/funds', label: 'Mutual funds', icon: 'funds' },
  { to: '/stock-research', label: 'Stock research', icon: 'search' },
  { to: '/research', label: 'Research desk', icon: 'search' },
  { to: '/news', label: 'News & alerts', icon: 'news' },
  { to: '/settings', label: 'Settings', icon: 'settings' },
]
const PRIMARY = [
  { to: '/home', label: 'Stocks', icon: 'markets', paths: ['/home', '/us-stocks'] },
  { to: '/funds', label: 'Mutual funds', icon: 'funds', paths: ['/funds'] },
  { to: '/dashboard', label: 'Portfolio', icon: 'portfolio', paths: ['/dashboard', '/portfolio-lab'] },
  { to: '/stock-research', label: 'Research', icon: 'search', paths: ['/stock-research', '/research'] },
  { to: '/news', label: 'News & alerts', icon: 'news', paths: ['/news'] },
]
export function Brand() {
  return <span className="brand wordmark">money<span>fest</span></span>
}
export function PageHeader({ title, subtitle, aside }: { title: string; subtitle?: string; aside?: ReactNode }) {
  return <header className="page-heading"><div><h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div><div className="heading-actions">{aside}</div></header>
}
export function Shell() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [user, setUser] = useState<User | null>(null)
  const [searchOpen, setSearchOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(() => { try { return localStorage.getItem('moneyfest-navigation') === 'collapsed' } catch { return false } })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const more = useRef<HTMLDialogElement>(null)
  const account = useRef<HTMLDetailsElement>(null)
  useEffect(() => { api.me().then(setUser).catch(() => {}) }, [])
  useEffect(() => { setSearchOpen(false); more.current?.close(); account.current?.removeAttribute('open') }, [pathname])
  useEffect(() => {
    function shortcut(e: KeyboardEvent) {
      if (e.key === 'Escape') setSearchOpen(false)
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault(); setSearchOpen(true)
        requestAnimationFrame(() => document.querySelector<HTMLInputElement>('[aria-label="Search workspace"]')?.focus())
      }
    }
    window.addEventListener('keydown', shortcut)
    return () => window.removeEventListener('keydown', shortcut)
  }, [])
  useEffect(() => {
    if (!searchOpen) return
    function dismissSearch(e: PointerEvent) {
      if (e.target instanceof Element && !e.target.closest('.workspace-search,.mobile-search-toggle')) setSearchOpen(false)
    }
    document.addEventListener('pointerdown', dismissSearch)
    return () => document.removeEventListener('pointerdown', dismissSearch)
  }, [searchOpen])
  function toggleNavigation() {
    setCollapsed(value => { try { localStorage.setItem('moneyfest-navigation', value ? 'expanded' : 'collapsed') } catch { /* Storage can be disabled. */ } return !value })
  }
  async function logout() {
    setBusy(true); setError('')
    try { await api.logout(); navigate('/', { replace: true }) }
    catch { setError('Sign out failed. Try again.') }
    finally { setBusy(false) }
  }
  const section = NAV.find(n => n.to === pathname)?.label ?? 'Moneyfest'
  const related = ['/home', '/us-stocks'].includes(pathname) ? NAV.filter(n => ['/home', '/us-stocks', '/stock-research'].includes(n.to))
    : ['/dashboard', '/portfolio-lab'].includes(pathname) ? NAV.filter(n => ['/dashboard', '/portfolio-lab'].includes(n.to))
    : ['/stock-research', '/research'].includes(pathname) ? NAV.filter(n => ['/stock-research', '/research'].includes(n.to)) : []
  return <div className={`app-layout consumer-app studio-app native-app ${collapsed ? 'navigation-collapsed' : ''}`}>
    <a href="#main-content" className="skip-link">Skip to content</a>
    <aside className="app-rail" aria-label="Workspace navigation">
      <Link className="rail-brand" to="/home" aria-label="Moneyfest home"><Brand /><span className="rail-monogram" aria-hidden="true">mf</span></Link>
      <span className="rail-section-label">YOUR WORKSPACE</span>
      <nav className="product-nav" aria-label="Main">{PRIMARY.map(n => <Link key={n.to} to={n.to} title={n.label} className={n.paths.includes(pathname) ? 'active' : ''} aria-current={n.paths.includes(pathname) ? 'page' : undefined}><Icon name={n.icon} size={20} /><span>{n.label}</span>{n.paths.includes(pathname) && <i aria-hidden="true" />}</Link>)}</nav>
      <div className="rail-tools"><span className="rail-section-label">RESEARCH TOOLS</span>{NAV.filter(n => ['/us-stocks', '/portfolio-lab', '/research'].includes(n.to)).map(n => <NavLink key={n.to} to={n.to} title={n.label}><Icon name={n.icon} size={18} /><span>{n.label}</span></NavLink>)}</div>
      <div className="rail-bottom"><NavLink to="/settings" title="Settings"><Icon name="settings" size={19} /><span>Settings</span></NavLink><button onClick={toggleNavigation} aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'} aria-expanded={!collapsed}><Icon name="panel" size={19} /><span>Collapse navigation</span></button><div className="rail-person"><span className="rail-avatar">{user?.display_name.charAt(0).toUpperCase() ?? 'M'}</span><div><strong>{user?.display_name ?? 'Your account'}</strong><small>Personal workspace</small></div></div></div>
    </aside>
    <header className="app-masthead"><div className={`masthead-inner ${searchOpen ? 'search-open' : ''}`}>
      <div className="app-location"><button className="icon-button app-back" aria-label="Go back" disabled={!(window.history.state?.idx > 0)} onClick={() => navigate(-1)}><Icon name="back" size={18} /></button><Link className="mobile-app-brand" to="/home" aria-label="Moneyfest home"><Brand /></Link><span className="app-location-root">Workspace <span>/</span></span><strong>{section}</strong></div><WorkspaceSearch /><kbd className="search-key">Ctrl K</kbd>
      <div className="masthead-actions"><button className="mobile-search-toggle icon-button" aria-label="Search all stocks and funds" aria-expanded={searchOpen} onClick={() => setSearchOpen(x => !x)}><Icon name="search" size={21} /></button><ThemeToggle /><NavLink className="icon-button" to="/news" aria-label="Open news and alerts"><Icon name="bell" size={21} /></NavLink>
        <details ref={account} className="account-menu"><summary aria-label="Account menu"><span className="avatar">{user?.display_name.charAt(0).toUpperCase() ?? 'M'}</span></summary><div className="account-popover"><strong>{user?.display_name ?? 'Your account'}</strong><Link to="/settings"><Icon name="settings" />Settings</Link><button disabled={busy} onClick={() => void logout()}><Icon name="logout" />{busy ? 'Signing out…' : 'Sign out'}</button></div></details>
      </div>
    </div></header>
    <div className="app-body">
      {!!related.length && <nav className="context-nav" aria-label="Section navigation">{related.map(n => <NavLink key={n.to} to={n.to}>{n.label}</NavLink>)}</nav>}
      <main id="main-content" className="app-content">{error && <p role="alert">{error}</p>}<Outlet context={{ user }} /></main>
    </div>
    {!['/research', '/portfolio-lab'].includes(pathname) && <WorkspaceAssistant section={section} />}
    <nav className="mobile-nav" aria-label="Mobile navigation">{[PRIMARY[0], PRIMARY[2], PRIMARY[1], PRIMARY[4]].map(n => <Link key={n.to} to={n.to} className={n.paths.includes(pathname) ? 'active' : ''}><Icon name={n.icon} /><span>{n.label === 'Mutual funds' ? 'Funds' : n.label === 'News & alerts' ? 'News' : n.label}</span></Link>)}<button className={['/stock-research', '/research', '/settings'].includes(pathname) ? 'active' : ''} aria-label="More sections" onClick={() => more.current?.showModal()}><Icon name="more" /><span>More</span></button></nav>
    <dialog ref={more} className="more-sheet" aria-labelledby="more-title" onClick={e => { if (e.target === e.currentTarget) more.current?.close() }}><header><h2 id="more-title">Explore Moneyfest</h2><button aria-label="Close sections" onClick={() => more.current?.close()}>×</button></header><nav>{NAV.map(n => <Link key={n.to} to={n.to} onClick={() => more.current?.close()}><span><Icon name={n.icon} />{n.label}</span><Icon name="arrow" size={18} /></Link>)}</nav></dialog>
  </div>
}
