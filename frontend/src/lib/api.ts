/** Java API client. Sessions and CSRF protection use the same origin. */

export type Currency = 'INR' | 'USD'
export type Position = {
  currency?: Currency
  exchange?: string
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
  currency?: Currency
  as_of: string | null
  positions: Position[]
  total_value: number | null
  total_invested: number
  total_pnl: number | null
  total_pnl_pct: number | null
  day_change: number | null
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
  const res = await fetch(`/api/v1${path}`, { headers: { Accept: 'application/json' } })
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event('moneyfest-session-expired'))
    throw new ApiError(res.status, `${res.status} ${res.statusText} on ${path}`)
  }
  return res.json() as Promise<T>
}

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  const csrf = await get<{ token: string; headerName: string }>('/auth/csrf')
  const res = await fetch(`/api/v1${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', [csrf.headerName]: csrf.token },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event('moneyfest-session-expired'))
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
  exchange: string
  currency?: Currency
  symbol: string
  isin: string | null
  held: boolean
  watched: boolean
  date: string | null
  close: number | null
  change_pct: number | null
  gate_result: string | null
}

export type User = { id: number; email: string; display_name: string }
export type Preferences = { alert_level: 'ALL' | 'EXPLAINED_ONLY' | 'HIGH_ONLY'; quiet_market: boolean; daily_digest: boolean }
export type Assessment = { date?: string; outcome: string; rendered_text: string; drivers_json?: string; evidence_json?: string }
export type SyncState = { scope: string; status: string; detail: string | null; attempted_at: string; succeeded_at: string | null; ticker?: string }
export type MarketStatus = { enabled: boolean; refreshing: boolean; catalog_count: number; catalog: SyncState[] }
export type NewsItem = { id: number; stock_id: number; ticker: string; name: string; exchange: string; headline: string; summary: string; source: string; url: string; published_at: string; sentiment: 'POSITIVE' | 'NEGATIVE' | 'MIXED' | 'NEUTRAL'; read: boolean }
export type NewsFeed = { items: NewsItem[]; total: number; sync: SyncState[]; refreshing: boolean }
export type Fund = { code: string; name: string; amc: string; category: string; plan: string; option_name: string; isin: string | null; date: string | null; nav: number | null; previous_nav: number | null; held: boolean }
export type RankedFund = Fund & { group_id: string; return_1y: number | null; return_3y: number | null; return_5y: number | null; anchor_1y: string | null; anchor_3y: string | null; anchor_5y: string | null }
export type FundDiscovery = { items: RankedFund[]; has_more: boolean; summary: { total: number; ranked: number; as_of: string | null }; groups: { group_id: string; schemes: number }[]; period: number; sync: { status: string; detail: string | null; succeeded_at: string | null }[] }
export type FundPosition = { code: string; name: string; amc: string; category: string; plan: string; option_name: string; units: number; avg_nav: number; date: string | null; nav: number | null; invested: number; value: number | null }
export type FundPortfolio = { positions: FundPosition[]; invested: number; value: number | null; pnl: number | null; unpriced: number; nav_source: string; sync: { status: string; detail: string | null; succeeded_at: string | null }[] }
export type ResearchEvent = { headline: string; source: string; url: string; published_at: string; sentiment: string }
export type ThemeSignal = { id: string; label: string; signal: 'POSITIVE' | 'NEGATIVE' | 'MIXED' | 'INSUFFICIENT'; focus: string | null; positive: number; negative: number; events: ResearchEvent[]; sync: { status: string; succeeded_at: string | null; detail: string | null }[] }
export type AssistantReply = { answer: string; model: string; as_of: string; sources: { id: string; headline: string; source: string; url: string; published_at: string }[] }

export const api = {
  me: () => get<User>('/auth/me'),
  login: (email: string, password: string) => send<User>('/auth/login', 'POST', { email, password }),
  register: (email: string, password: string, displayName: string) => send<User>('/auth/register', 'POST', { email, password, displayName }),
  logout: () => send('/auth/logout', 'POST'),
  health: () => get<{ status: string; market_data: string }>('/health'),
  preferences: () => get<Preferences>('/me/preferences'),
  savePreferences: (prefs: Preferences) => send<Preferences>('/me/preferences', 'PUT', prefs),
  watch: (id: number) => send(`/me/watchlist/${id}`, 'PUT'),
  unwatch: (id: number) => send(`/me/watchlist/${id}`, 'DELETE'),
  assessment: (id: number) => get<Assessment>(`/stocks/${id}/assessment`),
  stocks: (query = '', filter = 'all', exchange = 'ALL', offset = 0, market = 'ALL') => get<StockRow[]>(`/stocks?${new URLSearchParams({ query, filter, exchange, market, offset: String(offset) })}`),
  marketStatus: () => get<MarketStatus>('/market/status'),
  refresh: () => send<{ queued: number; enabled: boolean }>('/me/refresh', 'POST'),
  refreshStock: (id: number) => send<{ queued: boolean; enabled: boolean }>(`/stocks/${id}/refresh`, 'POST'),
  news: (params: Record<string, string> = {}) => get<NewsFeed>(`/me/news?${new URLSearchParams(params)}`),
  readNews: (id: number) => send<{ ok: boolean }>(`/me/news/${id}/read`, 'PUT'),
  portfolio: (currency: Currency = 'INR') => get<PortfolioSummary>(`/me/portfolio?currency=${currency}`),
  allocation: (currency: Currency = 'INR') => get<AllocationSlice[]>(`/me/portfolio/allocation?currency=${currency}`),
  portfolioHistory: (days = 90, currency: Currency = 'INR') => get<HistoryPoint[]>(`/me/portfolio/history?days=${days}&currency=${currency}`),
  prices: (stockId: number, days = 90) =>
    get<PricePoint[]>(`/stocks/${stockId}/prices?days=${days}`),
  putHolding: (ticker: string, qty: number | string, avg_cost: number | string) =>
    send<{ holding_id: number }>('/me/portfolio/positions', 'PUT', { ticker, qty, avg_cost }),
  deleteHolding: (ticker: string) =>
    send<{ removed: string }>(`/me/portfolio/positions/${encodeURIComponent(ticker)}`, 'DELETE'),
  funds: (query = '', category = '', offset = 0) => get<{ items: Fund[]; has_more: boolean }>(`/funds?${new URLSearchParams({ query, category, offset: String(offset) })}`),
  discoverFunds: (query = '', group = '', period = 3, offset = 0) => get<FundDiscovery>(`/funds/discover?${new URLSearchParams({ query, group, period: String(period), offset: String(offset) })}`),
  fundCategories: () => get<{ category: string; schemes: number }[]>('/funds/categories'),
  fundPortfolio: () => get<FundPortfolio>('/me/funds'),
  putFund: (code: string, units: number, avg_nav: number) => send<{ code: string }>('/me/funds/positions', 'PUT', { code, units, avg_nav }),
  deleteFund: (code: string) => send<{ removed: boolean }>(`/me/funds/positions/${code}`, 'DELETE'),
  fundNav: (code: string) => get<{ date: string; nav: number }[]>(`/funds/${code}/nav`),
  stockResearch: (id: number) => get<StockResearch>(`/stocks/${id}/research`),
  marketNews: () => get<{ items: NewsItem[]; refreshing: boolean }>('/market/news?market=US'),
  reviewPortfolioPlan: (question: string) => send<AssistantReply>('/me/portfolio-plan/review', 'POST', { question }),
  portfolioPlan: () => get<SavedPlan>('/me/portfolio-plan'),
  savePortfolioPlan: (plan: PortfolioPlan) => send<SavedPlan>('/me/portfolio-plan', 'PUT', plan),
  themes: () => get<ThemeSignal[]>('/research/themes'),
  assistantStatus: () => get<{ available: boolean; model: string }>('/me/assistant/status'),
  askAssistant: (question: string) => send<AssistantReply>('/me/assistant', 'POST', { question }),
}

export { ApiError }

export type StockResearch = {
  stock: { id: number; ticker: string; symbol: string; name: string; exchange: string; currency: Currency }
  close: number | null; as_of: string | null; sma20: number | null; sma50: number | null
  change_pct: number | null; observations: number; trend: 'UPTREND' | 'DOWNTREND' | 'MIXED' | 'INSUFFICIENT'
  bars: { date: string; close: number }[]
  news: { id: number; headline: string; source: string; url: string; published_at: string; sentiment: string }[]
  sync: SyncState[]
}
export type PlanStock = StockRow & { weight: number }
export type PortfolioPlan = { currency: Currency; risk: 'CAUTIOUS' | 'BALANCED' | 'GROWTH'; horizon_years: number; budget: number; allocations: { stock_id: number; weight: number }[] }
export type SavedPlan = { saved: boolean; currency?: Currency; risk?: PortfolioPlan['risk']; horizon_years?: number; budget?: number; stocks?: PlanStock[]; updated_at?: string }
