/** Typed client for the FastAPI backend. Same-origin via the Vite proxy. */

export type Position = {
  stock_id: number
  ticker: string | null
  name: string
  sector: string | null
  qty: number
  avg_cost: number
  price: number | null
  prev_close: number | null
  invested: number
  market_value: number | null
  pnl: number | null
  pnl_pct: number | null
  day_change: number | null
  day_change_pct: number | null
  gate_result: string | null
  outcome: string | null
  weight: number | null
}

export type PortfolioSummary = {
  as_of: string | null
  positions: Position[]
  total_value: number
  total_invested: number
  total_pnl: number
  total_pnl_pct: number | null
  day_change: number
  day_change_pct: number | null
  priced_positions: number
  unpriced_positions: number
}

export type AllocationSlice = { sector: string; value: number; weight: number | null }
export type HistoryPoint = { date: string; value: number }
export type PricePoint = { date: string; close: number; ret: number | null; gate_result: string }

export type Driver = {
  rank: number
  factor_id: string | null
  chain_text: string | null
  direction: string | null
  confidence: string | null
  confidence_reason: string | null
  evidence_ids: number[]
}

export type StockDetail = {
  stock: { id: number; name: string; ticker_nse: string | null; sector: string | null }
  gate: Record<string, number | string | null>
  outcome_display: string
  rendered_text: string | null
  drivers: Driver[]
  evidence: Array<{
    id: number; tier: number; source: string; headline: string | null
    url: string | null; suspect_reactive?: boolean
  }>
}

class ApiError extends Error {
  // Explicit field + assignment: TS `erasableSyntaxOnly` forbids parameter properties.
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: 'application/json' } })
  if (!res.ok) {
    throw new ApiError(res.status, `${res.status} ${res.statusText} on ${path}`)
  }
  return res.json() as Promise<T>
}

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const j = await res.json()
      if (j?.detail) detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch { /* keep the status line */ }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export type StockRow = {
  stock_id: number
  ticker: string | null
  name: string
  sector: string | null
  held: boolean
  date: string | null
  close: number | null
  change_pct: number | null
  gate_result: string | null
}

export const api = {
  stocks: () => get<StockRow[]>('/stocks'),
  portfolio: () => get<PortfolioSummary>('/portfolio'),
  allocation: () => get<AllocationSlice[]>('/portfolio/allocation'),
  portfolioHistory: (days = 90) => get<HistoryPoint[]>(`/portfolio/history?days=${days}`),
  prices: (stockId: number, days = 90) =>
    get<PricePoint[]>(`/stocks/${stockId}/prices?days=${days}`),
  putHolding: (ticker: string, qty: number, avg_cost: number) =>
    send<{ holding_id: number }>('/portfolio/holding', 'PUT', { ticker, qty, avg_cost }),
  deleteHolding: (ticker: string) =>
    send<{ removed: string }>(`/portfolio/holding/${ticker}`, 'DELETE'),
}

export { ApiError }
