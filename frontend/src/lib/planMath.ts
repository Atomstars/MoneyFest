import type { Currency, PlanStock, PortfolioPlan } from './api'

export type PlanDraft = Omit<PortfolioPlan, 'allocations'> & { stocks: PlanStock[] }
export const emptyDraft = (currency: Currency = 'INR'): PlanDraft => ({ currency, risk: 'BALANCED', horizon_years: 5, budget: currency === 'USD' ? 10000 : 100000, stocks: [] })
export const totalWeight = (stocks: PlanStock[]) => stocks.reduce((sum, stock) => sum + stock.weight, 0)
export const planPayload = (draft: PlanDraft): PortfolioPlan => ({currency: draft.currency, risk: draft.risk, horizon_years: draft.horizon_years, budget: draft.budget, allocations: draft.stocks.map(s => ({stock_id: s.stock_id, weight: s.weight}))})
export const planSignature = (draft: PlanDraft) => JSON.stringify({...planPayload(draft), allocations: planPayload(draft).allocations.sort((a, b) => a.stock_id - b.stock_id)})

/** Work in basis points so rounding never creates an overallocated plan. */
export function balanceWeights(stocks: PlanStock[], locked: ReadonlySet<number>, method: 'equal' | 'proportional'): PlanStock[] {
  const open = stocks.filter(s => !locked.has(s.stock_id))
  if (!open.length) throw new Error('Unlock at least one allocation to rebalance.')
  if (stocks.some(s => locked.has(s.stock_id) && (!Number.isFinite(s.weight) || s.weight < .01 || s.weight > 100 || Math.abs(s.weight * 100 - Math.round(s.weight * 100)) > .00001))) throw new Error('Correct the locked targets before rebalancing.')
  const lockedPoints = stocks.filter(s => locked.has(s.stock_id)).reduce((sum, s) => sum + Math.round(s.weight * 100), 0)
  const available = 10000 - lockedPoints
  if (available < open.length) throw new Error('Locked allocations leave too little room. Reduce or unlock a target first.')
  const basis = (stock: PlanStock) => Number.isFinite(stock.weight) ? Math.max(0, stock.weight) : 0
  const inputTotal = open.reduce((sum, s) => sum + basis(s), 0)
  const remaining = available - open.length
  const shares = open.map((stock, index) => {
    const proportion = method === 'equal' || inputTotal <= 0 ? 1 / open.length : basis(stock) / inputTotal
    const ideal = remaining * proportion
    return {id: stock.stock_id, index, points: 1 + Math.floor(ideal), fraction: ideal - Math.floor(ideal)}
  })
  let remainder = available - shares.reduce((sum, s) => sum + s.points, 0)
  // Largest remainders distribute rounding across companies rather than putting
  // the full residual into the final company in a long portfolio.
  const ranked = [...shares].sort((a, b) => b.fraction - a.fraction || b.index - a.index)
  for (const share of ranked) { if (remainder-- <= 0) break; share.points++ }
  const weights = new Map(shares.map(s => [s.id, s.points / 100]))
  return stocks.map(s => locked.has(s.stock_id) ? s : {...s, weight: weights.get(s.stock_id)!})
}

export function invalidPlan(draft: PlanDraft): boolean {
  return totalWeight(draft.stocks) > 100.00001 || !Number.isFinite(draft.budget) || draft.budget < 1 || draft.budget > 99999999999999
    || !Number.isInteger(draft.horizon_years) || draft.horizon_years < 1 || draft.horizon_years > 40
    || draft.stocks.some(s => !Number.isFinite(s.weight) || s.weight < .01 || s.weight > 100 || Math.abs(s.weight * 100 - Math.round(s.weight * 100)) > .00001)
}

export function scenarioValue(draft: PlanDraft, decline: number) {
  const loss = draft.budget * totalWeight(draft.stocks) / 100 * decline / 100
  return {loss, remaining: draft.budget - loss}
}

export function allocationColor(id: number) {
  return ['#3c60dd', '#7a6bc0', '#bd7869', '#71876c', '#548a9a', '#767b89'][Math.abs(id) % 6]
}
