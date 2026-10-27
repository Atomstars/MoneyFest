import { test, expect } from '@playwright/test'

const apple = { stock_id: 31, ticker: 'AAPL.US', symbol: 'AAPL', name: 'Apple Inc.', exchange: 'NASDAQ', currency: 'USD', sector: 'Technology', close: 110, date: '2026-10-23', watched: false, held: false }
const microsoft = { ...apple, stock_id: 32, ticker: 'MSFT.US', symbol: 'MSFT', name: 'Microsoft Corporation' }
const research = { stock: { ...apple, id: 31 }, close: 110, change_pct: .01, as_of: '2026-10-23', sma20: 105, sma50: 100, observations: 60, trend: 'UPTREND', bars: [{date: '2026-10-23', close: 110}, {date: '2026-10-22', close: 100}], news: [{id: 1, headline: 'Apple earnings rise', source: 'Example source', url: 'https://example.com/apple', published_at: '2026-10-23T12:00:00Z', sentiment: 'POSITIVE'}], sync: [] }

test('US stocks, sourced research and risk calculator work across desktop and mobile', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname
    let data: unknown = {}
    if (path.endsWith('/auth/me')) data = { id: 1, display_name: 'Test', email: 'test@example.com' }
    else if (path.endsWith('/auth/csrf')) data = { token: 'fixture', headerName: 'X-CSRF-TOKEN' }
    else if (path.endsWith('/assistant/status')) data = { available: false }
    else if (path.endsWith('/stocks')) { expect(['US', 'ALL']).toContain(url.searchParams.get('market')); data = [apple] }
    else if (path.endsWith('/funds')) data = { items: [], has_more: false }
    else if (path.endsWith('/research')) data = research
    else if (path.endsWith('/refresh')) data = { queued: true, enabled: true }
    else if (path.endsWith('/market/news')) data = { items: [{...research.news[0], ...apple}], refreshing: false }
    await route.fulfill({ json: data })
  })
  await page.goto('/us-stocks')
  await expect(page.getByRole('heading', { name: 'US stocks', exact: true })).toBeVisible()
  await expect(page.getByText('$110.00', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'US stock news', exact: true }).click()
  await expect(page.getByText('Apple earnings rise')).toBeVisible()
  await page.getByLabel('Search workspace').fill('AAPL')
  await page.locator('.workspace-results').getByRole('link').first().click()
  await expect(page.getByRole('button', {name: 'Stocks & watchlist'})).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByLabel('Search stocks', {exact: true})).toHaveValue('AAPL')
  await page.goto('/stock-research?stockId=31')
  await expect(page.getByText('Observed uptrend', { exact: true })).toBeVisible()
  await expect(page.getByText('$105.00', { exact: true })).toBeVisible()
  await page.getByRole('button', {name: 'Trade planner', exact: true}).click()
  await page.getByLabel('Entry price', { exact: true }).fill('100')
  await page.getByLabel('Stop price', { exact: true }).fill('90')
  await page.getByLabel('Target price', { exact: true }).fill('120')
  await page.getByLabel('Risk budget', { exact: true }).fill('100')
  await expect(page.getByText('10 whole shares', { exact: true })).toBeVisible()
  await expect(page.getByText(/reward\/risk 2.00×/)).toBeVisible()
  await page.getByLabel('Stop price', { exact: true }).fill('110')
  await expect(page.getByText('10 whole shares', { exact: true })).toHaveCount(0)
  await page.getByRole('button', {name: 'Refresh prices & news'}).click()
  await expect(page.getByRole('status').filter({hasText: 'Refresh queued'})).toBeVisible()
  await page.screenshot({ path: '../.local/global-research-desktop.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: '../.local/global-research-mobile.png', fullPage: true })
  expect(errors).toEqual([])
})

test('portfolio search saves exact allocations, restores them and supports the rules coach', async ({ page }) => {
  let saved: Record<string, unknown> | null = null
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url()), path = url.pathname
    let data: unknown = {}
    if (path.endsWith('/auth/me')) data = { id: 1, display_name: 'Test' }
    else if (path.endsWith('/auth/csrf')) data = { token: 'fixture', headerName: 'X-CSRF-TOKEN' }
    else if (path.endsWith('/assistant/status')) data = { available: false }
    else if (path.endsWith('/stocks')) data = url.searchParams.get('query') === 'MSFT' ? [microsoft] : [apple]
    else if (path.endsWith('/portfolio-plan/review')) { expect(saved).not.toBeNull(); data = { answer: 'Rules-based review: AAPL and MSFT each have 50%. Compare shared technology risk.', sources: [], model: 'allocation-rules-v1' } }
    else if (path.endsWith('/portfolio-plan')) {
      if (route.request().method() === 'PUT') saved = route.request().postDataJSON()
      data = saved ? { ...saved, saved: true, stocks: [{...apple, weight: 50}, {...microsoft, weight: 50}] } : { saved: false }
    }
    await route.fulfill({ json: data })
  })
  await page.goto('/portfolio-lab')
  await expect(page.getByRole('button', {name: 'Save draft', exact: true})).toBeEnabled()
  await page.getByLabel('Market & currency').selectOption('USD')
  await page.getByLabel('Search portfolio stocks').fill('AAPL')
  await page.locator('.finder-results').getByRole('button').click()
  await page.getByLabel('Search portfolio stocks').fill('MSFT')
  await page.locator('.finder-results').getByRole('button').click()
  await page.getByRole('button', {name: 'Equal weights'}).click()
  await expect(page.getByLabel('Target weight for AAPL')).toHaveValue('50')
  await expect(page.getByLabel('Target weight for MSFT')).toHaveValue('50')
  await page.getByLabel('Target weight for AAPL').fill('60')
  await expect(page.getByRole('button', {name: 'Save draft', exact: true})).toBeDisabled()
  await page.getByLabel('Target weight for AAPL').fill('50')
  await page.getByRole('button', {name: 'Discuss plan', exact: true}).click()
  await page.getByLabel('Discuss this portfolio').fill('Review the weights and concentration.')
  await page.getByRole('button', {name: 'Save & ask agent'}).click()
  await expect(page.getByText(/Rules-based review: AAPL and MSFT/)).toBeVisible()
  expect(saved).toMatchObject({ currency: 'USD', allocations: [{stock_id: 31, weight: 50}, {stock_id: 32, weight: 50}] })
  await page.reload()
  await expect(page.getByLabel('Target weight for AAPL')).toHaveValue('50')
  await expect(page.getByLabel('Market & currency')).toHaveValue('USD')
  await page.screenshot({ path: '../.local/portfolio-lab-desktop.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: '../.local/portfolio-lab-mobile.png', fullPage: true })
})
