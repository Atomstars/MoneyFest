import { useEffect, useState } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import { api, ApiError } from '../lib/api'
import { ErrorNote } from './ui'

export function SessionGate() {
  const [state, setState] = useState<'loading' | 'signed-in' | 'signed-out'>('loading')
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const expired = () => setState('signed-out')
    window.addEventListener('moneyfest-session-expired', expired)
    return () => window.removeEventListener('moneyfest-session-expired', expired)
  }, [])
  useEffect(() => {
    let alive = true
    api.me().then(() => { if (alive) setState('signed-in') }).catch((e: unknown) => {
      if (!alive) return
      if (e instanceof ApiError && e.status === 401) setState('signed-out')
      else setError(e instanceof Error ? e.message : 'Cannot connect to the server.')
    })
    return () => { alive = false }
  }, [attempt])
  if (error) return <ErrorNote error={error} onRetry={() => { setError(null); setAttempt((n) => n + 1) }} />
  if (state === 'loading') return <p className="p-8 text-center">Opening your workspace…</p>
  if (state === 'signed-out') return <Navigate to="/" replace />
  return <Outlet />
}
