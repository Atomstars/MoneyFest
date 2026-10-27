import { test, expect } from '@playwright/test'
import { balanceWeights, emptyDraft, invalidPlan, scenarioValue } from '../src/lib/planMath'
import type { PlanStock } from '../src/lib/api'

const stocks = (weights: number[]): PlanStock[] => weights.map((weight, i) => ({stock_id: i + 1, ticker: `FIXTURE${i}`, symbol: `FIXTURE${i}`, name: 'Test company', sector: null, exchange: 'NASDAQ', currency: 'USD', isin: null, held: false, watched: false, date: null, close: null, change_pct: null, gate_result: null, weight}))

test('equal allocations for thirty companies sum to 100% and differ by at most one basis point', () => {
  const result = balanceWeights(stocks(Array(30).fill(1)), new Set(), 'equal')
  const points = result.map(s => Math.round(s.weight * 100))
  expect(points.reduce((sum, n) => sum + n, 0)).toBe(10000)
  expect(Math.max(...points) - Math.min(...points)).toBeLessThanOrEqual(1)
})

test('locked targets are preserved and invalid locked budgets cannot silently be redistributed', () => {
  const result = balanceWeights(stocks([61.37, 1, 1, 1]), new Set([1]), 'equal')
  expect(result[0].weight).toBe(61.37)
  expect(result.reduce((sum, s) => sum + Math.round(s.weight * 100), 0)).toBe(10000)
  expect(() => balanceWeights(stocks([100, 1]), new Set([1]), 'equal')).toThrow('Locked allocations')
  expect(() => balanceWeights(stocks([20.001, 1]), new Set([1]), 'equal')).toThrow('Correct the locked')
})

test('cash is preserved in a decline scenario and overallocated drafts cannot be saved', () => {
  const draft = {...emptyDraft('USD'), budget: 10000, stocks: stocks([50, 30, 10])}
  expect(scenarioValue(draft, 25)).toEqual({loss: 2250, remaining: 7750})
  expect(invalidPlan(draft)).toBe(false)
  expect(invalidPlan({...draft, stocks: stocks([60, 30, 20])})).toBe(true)
  expect(scenarioValue({...draft, stocks: []}, 60)).toEqual({loss: 0, remaining: 10000})
})
