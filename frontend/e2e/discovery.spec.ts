import { test, expect } from '@playwright/test'

test('progressive discovery, cross-catalog search and contextual assistant', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname
    let data: unknown = {}
    if (path.endsWith('/auth/me')) data = { id: 1, display_name: 'Preview', email: 'preview@example.com' }
    else if (path.endsWith('/auth/csrf')) data = { token: 'test', headerName: 'X-CSRF-TOKEN' }
    else if (path.endsWith('/assistant/status')) data = { available: true }
    else if (path.endsWith('/me/assistant')) {
      expect(route.request().postDataJSON().question).toContain('Section: Explore stocks')
      data = { answer: 'Compare business fundamentals and recent evidence.', sources: [], as_of: '', model: 'test' }
    }
    else if (path.endsWith('/stocks')) data = [{stock_id: 1, symbol: 'TCS', ticker: 'TCS', name: 'Tata Consultancy Services', exchange: 'NSE', close: 3000, change_pct: .01, date: '2026-10-14', watched: false, held: false}]
    else if (path.endsWith('/funds/discover')) data = {items: [{code: '123', name: 'Example Index Fund', category: 'Index', group_id: 'index', amc: 'Example', nav: 25, date: '2026-10-26', plan: 'Direct', option_name: 'Growth', return_1y: 12, return_3y: 18.42, return_5y: null}], has_more: false, summary: {total: 1, ranked: 1, as_of: '2026-10-26'}, groups: [{group_id: 'index', schemes: 1}], sync: [{status: 'OK'}]}
    else if (path.endsWith('/me/funds')) data = { positions: [], invested: 0, value: 0, pnl: 0, unpriced: 0, sync: [] }
    else if (path.endsWith('/funds')) data = {items: [{code: '123', name: 'Example Index Fund', category: 'Index', amc: 'Example', nav: 25, date: '2026-10-14', plan: 'Direct', option_name: 'Growth'}], has_more: false}
    await route.fulfill({json: data})
  })
  await page.goto('/home')
  await expect(page.getByRole('heading', {name: 'Explore stocks', exact: true})).toBeVisible()
  await expect(page.locator('.stock-table')).toHaveCount(0)
  await page.getByRole('button', {name: 'Ask Moneyfest', exact: true}).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByRole('button', {name: 'How should I research a stock?'}).click()
  await page.getByRole('dialog').getByRole('button', {name: 'Ask Moneyfest'}).click()
  await expect(page.getByText('Compare business fundamentals and recent evidence.')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await page.getByLabel('Search workspace').fill('TCS')
  await expect(page.locator('.workspace-results').getByText('Tata Consultancy Services')).toBeVisible()
  await page.locator('.workspace-results').getByRole('link').first().click()
  await expect(page.getByLabel('Search stocks')).toHaveValue('TCS')
  await expect(page.locator('.stock-table-row')).toHaveCount(1)
  await page.getByRole('link', {name: 'Mutual funds', exact: true}).first().click()
  await expect(page.locator('.fund-result')).toHaveCount(1)
  await expect(page.getByLabel('Fund category', {exact: true})).toHaveCount(0)
  await page.getByRole('button', {name: 'Index', exact: true}).click()
  await expect(page.getByRole('button', {name: 'Index', exact: true})).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByText('+18.42%')).toBeVisible()
  await page.getByRole('button', {name: '1Y', exact: true}).click()
  await expect(page.getByText('+12.00%')).toBeVisible()
  await expect(page.getByText('Example Index Fund', {exact:true})).toBeVisible()
  await page.getByRole('button', {name: 'My funds · 0'}).click()
  await expect(page.getByText('No funds tracked')).toBeVisible()
  await expect(page.locator('.fund-discovery')).toHaveCount(0)
  await page.setViewportSize({width:390,height:844})
  await page.goto('/home')
  await expect(page.getByRole('heading', {name: 'Explore stocks', exact: true})).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({path:'../.local/discovery-mobile.png',fullPage:true})
  await page.setViewportSize({width:1440,height:1000})
  await page.screenshot({path:'../.local/discovery-desktop.png',fullPage:true})
  expect(errors).toEqual([])
})
