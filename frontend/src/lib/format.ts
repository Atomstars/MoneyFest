/** Formatting helpers. Indian numbering (lakh/crore) throughout -- this is an NSE/BSE product. */

const inr = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
const inr2 = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

/** A rupee amount. `null` renders as an em dash, never as 0 -- a missing price
 *  must never be readable as a real value. */
export function money(v: number | null | undefined, decimals = false): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—'
  return `₹${(decimals ? inr2 : inr).format(v)}`
}

/** Signed rupee amount, for P&L and day change. */
export function signedMoney(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—'
  const sign = v > 0 ? '+' : v < 0 ? '−' : ''
  return `${sign}₹${inr.format(Math.abs(v))}`
}

export function pct(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—'
  return `${(v * 100).toFixed(digits)}%`
}

export function signedPct(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—'
  const sign = v > 0 ? '+' : v < 0 ? '−' : ''
  return `${sign}${(Math.abs(v) * 100).toFixed(digits)}%`
}

/** Compact form for axis ticks: ₹1.2L, ₹3.4Cr. */
export function compactMoney(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—'
  const a = Math.abs(v)
  if (a >= 1e7) return `₹${(v / 1e7).toFixed(1)}Cr`
  if (a >= 1e5) return `₹${(v / 1e5).toFixed(1)}L`
  if (a >= 1e3) return `₹${(v / 1e3).toFixed(0)}k`
  return `₹${v.toFixed(0)}`
}

export function shortDate(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}

export function longDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-IN', {
    weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
  })
}

export function directionOf(v: number | null | undefined): 'up' | 'down' | 'flat' {
  if (v === null || v === undefined || !Number.isFinite(v) || v === 0) return 'flat'
  return v > 0 ? 'up' : 'down'
}

/** Plain-language label for a gate outcome. The engine's vocabulary is precise but
 *  internal; users get the meaning, with the raw code available on hover. */
export const OUTCOME_LABEL: Record<string, string> = {
  NOISE: 'Normal range',
  MARKET: 'Market move',
  MIXED: 'Mostly market',
  INVESTIGATE: 'Stock-specific',
  ATTRIBUTED: 'Explained',
  NO_DRIVER: 'No clear driver',
  EVENT_NO_MOVE: 'News, no move',
  PENDING_ATTRIBUTION: 'Analysing',
  WARMING_UP: 'Warming up',
  DATA_ISSUE: 'Data issue',
}

export const OUTCOME_HELP: Record<string, string> = {
  NOISE: 'Moved within its normal daily range. Nothing to explain.',
  MARKET: 'The whole market moved; this stock followed it.',
  MIXED: 'Mostly a market move, with a smaller stock-specific part.',
  INVESTIGATE: 'Moved more than the market explains — being investigated.',
  ATTRIBUTED: 'A specific, cited driver was found and verified.',
  NO_DRIVER: 'Moved on its own, but no evidence explains it. Honest answer.',
  EVENT_NO_MOVE: 'Material news filed, but the price barely reacted.',
  PENDING_ATTRIBUTION: 'Queued for the reasoning layer.',
  WARMING_UP: 'Not enough price history yet to judge.',
  DATA_ISSUE: 'Price data looked unreliable; nothing was concluded.',
}
