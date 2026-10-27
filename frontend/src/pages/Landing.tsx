import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ThemeToggle } from '../components/ui'
import { api } from '../lib/api'

export function Landing() {
  const nav = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function submit() {
    setBusy(true); setError(null)
    try {
      if (mode === 'register') await api.register(email, password, name)
      else await api.login(email, password)
      nav('/dashboard', { replace: true })
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to sign in.') }
    finally { setBusy(false) }
  }

  return <div className="auth-layout">
    <section className="auth-identity">
      <div className="auth-brand">moneyfest<span>.</span></div>
      <div className="auth-intro"><span className="auth-eyebrow">YOUR PORTFOLIO. A CLEARER PICTURE.</span><h1>Stay invested.<br />Stay informed.</h1><p>Your stocks. Their stories. One workspace.</p>
        <div className="auth-art" aria-hidden="true"><div className="auth-orbit orbit-one" /><div className="auth-orbit orbit-two" /><div className="auth-art-center">m.</div><span className="auth-art-tag tag-one">↗ Portfolio</span><span className="auth-art-tag tag-two">◎ Daily perspective</span><span className="auth-art-tag tag-three">≋ Company news</span></div>
      </div><div className="auth-footer">NSE & BSE <span>•</span> Built for your daily check-in</div>
    </section>
    <section className="auth-access"><div className="auth-theme"><ThemeToggle /></div><div className="auth-form">
      <span className="auth-eyebrow">YOUR WORKSPACE AWAITS</span><h2>{mode === 'login' ? 'Welcome back' : 'Create your account'}</h2><p>{mode === 'login' ? 'Sign in to your portfolio.' : 'Start with the stocks you own.'}</p>
      <form onSubmit={e => { e.preventDefault(); void submit() }} className="space-y-5 mt-8">
        {mode === 'register' && <label className="block text-xs font-medium">Your name<input required maxLength={80} value={name} onChange={e => setName(e.target.value)} autoComplete="name" className="account-input mt-2" /></label>}
        <label className="block text-xs font-medium">Email<input required type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" autoComplete="email" className="account-input mt-2" /></label>
        <label className="block text-xs font-medium">Password<input aria-label="Password" required type="password" minLength={10} maxLength={72} value={password} onChange={e => setPassword(e.target.value)} autoComplete={mode === 'register' ? 'new-password' : 'current-password'} className="account-input mt-2" />{mode === 'register' && <span className="muted block mt-2 text-[11px]">At least 10 characters</span>}</label>
        {error && <p role="alert" className="text-xs" style={{ color: 'var(--down)' }}>{error}</p>}
        <button type="submit" disabled={busy} className="action-button w-full">{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'} <span aria-hidden="true">→</span></button>
      </form>
      <button disabled={busy} onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(null) }} className="auth-switch">{mode === 'login' ? 'New here? Create an account' : 'Already have an account? Sign in'}</button>
      <p className="auth-privacy">Your portfolio stays in your personal workspace.</p>
    </div><span className="auth-disclaimer">Explanation only. Not investment advice.</span></section>
  </div>
}
