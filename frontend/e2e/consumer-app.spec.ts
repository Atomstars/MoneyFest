import { test, expect } from '@playwright/test'

test('company cards, watchlist, research tabs and mobile section menu form a clear app flow', async ({ page }) => {
  const stocks = [
    { stock_id: 1, symbol: 'RELIANCE', ticker: 'RELIANCE', name: 'Reliance Industries', close: 1450.5, change_pct: .012 },
    { stock_id: 2, symbol: 'TCS', ticker: 'TCS', name: 'Tata Consultancy Services', close: 3100.25, change_pct: -.007 },
    { stock_id: 3, symbol: 'HDFCBANK', ticker: 'HDFCBANK', name: 'HDFC Bank', close: 1705, change_pct: .008 },
    { stock_id: 4, symbol: 'INFY', ticker: 'INFY', name: 'Infosys', close: 1550.7, change_pct: .005 },
  ].map(s => ({...s, exchange: 'NSE', currency: 'INR', date: '2026-10-26', held: false}))
  const watched = new Set<number>()
  const errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url()), path = url.pathname
    let data: unknown = {}
    if (path.endsWith('/auth/me')) data = {id: 1, display_name: 'Akash'}
    else if (path.endsWith('/auth/csrf')) data = {token: 'fixture', headerName: 'X-CSRF-TOKEN'}
    else if (path.endsWith('/assistant/status')) data = {available: false}
    else if (/\/watchlist\/\d+$/.test(path)) { const id = Number(path.split('/').at(-1)); if (route.request().method() === 'DELETE') watched.delete(id); else watched.add(id); data = {ok: true} }
    else if (path.endsWith('/stocks')) {
      const q = url.searchParams.get('query')?.toLowerCase() ?? ''
      data = stocks.filter(s => (!q || `${s.ticker} ${s.name}`.toLowerCase().includes(q)) && (url.searchParams.get('filter') !== 'watched' || watched.has(s.stock_id))).map(s => ({...s, watched: watched.has(s.stock_id)}))
    }
    else if (path.endsWith('/prices')) data = Array.from({length: 20}, (_, i) => ({date: `2026-10-${String(i + 1).padStart(2, '0')}`, close: 100 + i * 2 + (i % 4) * 3}))
    else if (path.endsWith('/research')) data = {stock: {...stocks[1], id: 2}, close: 3100.25, sma20: 3000, sma50: 2900, change_pct: -.007, observations: 60, trend: 'UPTREND', as_of: '2026-10-26', bars: [{date: '2026-10-26', close: 3100.25}, {date: '2026-10-23', close: 3050}], news: [{id: 1, headline: 'TCS wins a new contract', source: 'Example publisher', url: 'https://example.com/tcs', published_at: '2026-10-26T12:00:00Z', sentiment: 'POSITIVE'}], sync: []}
    else if (path.endsWith('/refresh')) data = {queued: true, enabled: true}
    else if (path.endsWith('/funds')) data = {items: [], has_more: false}
    await route.fulfill({json: data})
  })
  await page.setViewportSize({width: 1440, height: 1000})
  await page.goto('/home')
  await expect(page.getByRole('navigation', {name: 'Main', exact: true}).getByRole('link')).toHaveCount(5)
  await expect(page.locator('.sidebar')).toHaveCount(0)
  await expect(page.locator('.company-card-open')).toHaveCount(4)
  await expect(page.locator('.company-chart svg')).toHaveCount(4)
  await page.screenshot({path: '../.local/consumer-stocks-desktop.png', fullPage: true})
  await page.getByRole('button', {name: 'Switch to dark theme', exact: true}).click()
  await page.screenshot({path: '../.local/consumer-stocks-dark.png', fullPage: true})
  await page.getByRole('button', {name: 'Switch to light theme', exact: true}).click()
  await page.getByRole('button', {name: 'Add to watchlist: TCS', exact: true}).click()
  await expect(page.getByRole('button', {name: 'Remove from watchlist: TCS', exact: true})).toBeVisible()
  await page.getByRole('button', {name: 'Watchlist', exact: true}).click()
  await expect(page.locator('.stock-table-row')).toHaveCount(1)
  await page.getByRole('group', {name: 'Filter', exact: true}).getByRole('button', {name: 'Explore', exact: true}).click()
  await page.locator('.company-card-open').filter({hasText: 'TCS'}).click()
  await expect(page).toHaveURL(/stock-research\?stockId=2$/)
  await expect(page.getByText('Observed uptrend', {exact: true})).toBeVisible()
  await page.getByRole('button', {name: 'News · 1', exact: true}).click()
  await expect(page.getByRole('link', {name: 'TCS wins a new contract ↗', exact: true})).toBeVisible()
  await expect(page.getByRole('heading', {name: 'Price direction', exact: true})).toHaveCount(0)
  await page.getByRole('button', {name: 'Trade planner', exact: true}).click()
  await expect(page.getByLabel('Risk budget', {exact: true})).toBeVisible()
  await page.setViewportSize({width: 390, height: 844})
  await page.goto('/home')
  await expect(page.locator('.company-card-open')).toHaveCount(4)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await expect(page.getByRole('navigation', {name: 'Mobile navigation'}).getByRole('link')).toHaveCount(4)
  await page.screenshot({path: '../.local/consumer-stocks-mobile.png', fullPage: true})
  await page.getByRole('button', {name: 'More sections', exact: true}).click()
  await expect(page.getByRole('dialog', {name: 'Explore Moneyfest'})).toBeVisible()
  await page.getByRole('dialog').getByRole('link', {name: 'Stock research', exact: true}).click()
  await expect(page.getByRole('heading', {name: 'Stock research', exact: true})).toBeVisible()
  await expect(page.getByRole('dialog', {name: 'Explore Moneyfest'})).not.toBeVisible()
  expect(errors).toEqual([])
})
