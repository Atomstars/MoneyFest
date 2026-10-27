import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { Icon } from './Icon'

export function RefreshButton({ stockId }: { stockId?: number }) {
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const timer = useRef<ReturnType<typeof setInterval> | undefined>(undefined)
  useEffect(() => () => clearInterval(timer.current), [])
  async function refresh() {
    setBusy(true); setMessage('')
    try {
      const result = stockId ? await api.refreshStock(stockId) : await api.refresh()
      if (!result.enabled) { setMessage('Refresh is disabled on this server.'); setBusy(false); return }
      let polls = 0
      timer.current = setInterval(async () => {
        try {
          const status = await api.marketStatus()
          window.dispatchEvent(new Event('moneyfest-data-updated'))
          if (!status.refreshing || ++polls >= 40) { clearInterval(timer.current); setBusy(false); setMessage('Checked · cached for 15 min') }
        } catch { clearInterval(timer.current); setBusy(false); setMessage('Could not check refresh. Try again.') }
      }, 3000)
    } catch { setMessage('Refresh failed. Try again.'); setBusy(false) }
  }
  return <div className="refresh-control"><button className="secondary-button" disabled={busy} onClick={() => void refresh()}><Icon name="refresh" size={15} className={busy ? 'spin' : ''} />{busy ? 'Refreshing…' : 'Refresh data'}</button>{message && <span role="status">{message}</span>}</div>
}
