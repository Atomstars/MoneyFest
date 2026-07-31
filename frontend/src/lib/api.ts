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
  /** Date this row was actually priced at — older than `as_of` when its history lags. */
  priced_on: string | null
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

// --- Universe: the browsable NSE+BSE catalogue ------------------------------

export type SecurityRow = {
  isin: string
  symbol_nse: string | null
  scrip_bse: string | null
  name: string
  industry: string | null
  exchanges: string
  market_cap: number | null
  stock_id: number | null
  rank?: number
}

export type UniverseStats = {
  total: number
  nse: number
  bse: number
  tracked: number
  synced_at: string | null
}

// --- Stock detail -----------------------------------------------------------

/** A trailing return window. `null` means there is no basis close that far back --
 *  rendered as a dash, never as 0%. */
export type Window = {
  pct: number
  from_date: string
  from_close: number
  to_date: string
  to_close: number
} | null

export type Quote = {
  price: number | null
  prev_close: number | null
  change: number | null
  change_pct: number | null
  open: number | null
  high: number | null
  low: number | null
  /** 'BSE' | 'yfinance' | 'stored_close' | 'none' -- shown so the number is attributable. */
  source: string
  delayed?: boolean
  disclaimer?: string
  stale?: boolean
  as_of_date?: string
  fetched_at?: string
}

export type HistoryStatus = {
  days: number
  first_date: string | null
  last_date: string | null
  min_required: number
  warm: boolean
  status?: string
  written?: number
  message?: string
}

export type Overview = {
  stock: { id: number; name: string; ticker_nse: string | null; ticker_bse: string | null; sector: string | null }
  security: SecurityRow | null
  quote: Quote
  windows: Record<string, Window>
  range: { high_52w: number | null; low_52w: number | null; band_position: number | null; covers_days: number }
  history: HistoryStatus
  gate_result: string | null
  gate_date: string | null
  holding: { qty: number; avg_cost: number } | null
  watched: boolean
}

export type KeyStats = {
  stats: Record<string, number | null>
  /** Per-field provenance. BSE and yfinance disagree, so the UI attributes each number. */
  sources: Record<string, string>
  meta: Record<string, string | number | null>
  fetched_at: string
  stale: boolean
  source: string
}

export type StatementPeriod = {
  period: string
  revenue: number | null
  net_income: number | null
  ebitda: number | null
  net_margin: number | null
}

export type Financials = {
  annual: StatementPeriod[]
  quarterly: StatementPeriod[]
  currency: string
  stale: boolean
  source: string
}

export type Profile = {
  summary: string | null
  website: string | null
  employees: number | null
  industry: string | null
  sector: string | null
  city: string | null
  isin: string | null
  listing_date: string | null
  exchanges: string | null
  bse_group: string | null
  stale: boolean
  source: string
}

export type Fundamentals = {
  key_stats: KeyStats | null
  financials: Financials | null
  profile: Profile | null
}

export type ShareholdingQuarter = {
  period: string
  promoter_pct: number | null
  public_pct: number | null
  employee_trusts_pct: number | null
  revised: boolean
}

export type Shareholding = {
  latest: ShareholdingQuarter | null
  promoter_change_qoq: number | null
  quarters: ShareholdingQuarter[]
  institutions: {
    institutions_pct: number | null
    institutions_count: number | null
    insiders_pct: number | null
  } | null
  institutions_note: string | null
  stale: boolean
  source: string
}

// --- Market context ---------------------------------------------------------

export type IndexQuote = {
  symbol: string
  name: string
  value: number
  prev_close: number | null
  change: number | null
  change_pct: number | null
}

export type Mover = {
  symbol: string
  stock_id: number | null
  name: string
  price: number
  change: number
  change_pct: number
}

export type Movers = {
  gainers: Mover[]
  losers: Mover[]
  universe: number
  as_of: string | null
  stale: boolean
  source: string | null
}

export const api = {
  stocks: () => get<StockRow[]>('/stocks'),
  indices: () => get<{ indices: IndexQuote[]; stale: boolean; source: string | null }>(
    '/market/indices'),
  movers: () => get<Movers>('/market/movers'),
  portfolio: () => get<PortfolioSummary>('/portfolio'),
  allocation: () => get<AllocationSlice[]>('/portfolio/allocation'),
  portfolioHistory: (days = 90) => get<HistoryPoint[]>(`/portfolio/history?days=${days}`),
  prices: (stockId: number, days = 90) =>
    get<PricePoint[]>(`/stocks/${stockId}/prices?days=${days}`),
  putHolding: (ticker: string, qty: number, avg_cost: number) =>
    send<{ holding_id: number }>('/portfolio/holding', 'PUT', { ticker, qty, avg_cost }),
  deleteHolding: (ticker: string) =>
    send<{ removed: string }>(`/portfolio/holding/${ticker}`, 'DELETE'),

  universeSearch: (q: string, exchange?: string, limit = 25) =>
    get<{ query: string; results: SecurityRow[] }>(
      `/universe/search?q=${encodeURIComponent(q)}&limit=${limit}` +
        (exchange ? `&exchange=${exchange}` : ''),
    ),
  universeStats: () => get<UniverseStats>('/universe/stats'),
  track: (isin: string) =>
    send<{ stock_id: number; history: HistoryStatus }>('/universe/track', 'POST', { isin }),
  untrack: (stockId: number) =>
    send<{ untracked: number }>(`/universe/track/${stockId}`, 'DELETE'),

  overview: (stockId: number) => get<Overview>(`/stocks/${stockId}/overview`),
  quote: (stockId: number) => get<Quote>(`/stocks/${stockId}/quote`),
  fundamentals: (stockId: number) => get<Fundamentals>(`/stocks/${stockId}/fundamentals`),
  shareholding: (stockId: number) => get<Shareholding>(`/stocks/${stockId}/shareholding`),
  backfill: (stockId: number) =>
    send<HistoryStatus>(`/stocks/${stockId}/backfill`, 'POST'),
  attribution: (stockId: number) => get<StockDetail>(`/stocks/${stockId}/attribution`),
}

export { ApiError }
