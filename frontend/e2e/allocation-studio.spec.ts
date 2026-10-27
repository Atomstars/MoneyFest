import { test, expect } from '@playwright/test'

test('weight locks, rebalancing, undo, comparison and downside scenarios use the actual draft', async ({ page }) => {
  const stocks = [
    {stock_id: 31, ticker: 'AAPL.US', symbol: 'AAPL', name: 'Apple Inc.', exchange: 'NASDAQ', sector: 'Technology', close: 100, weight: 50},
    {stock_id: 32, ticker: 'MSFT.US', symbol: 'MSFT', name: 'Microsoft Corporation', exchange: 'NASDAQ', sector: 'Technology', close: 200, weight: 30},
    {stock_id: 33, ticker: 'NVDA.US', symbol: 'NVDA', name: 'NVIDIA Corporation', exchange: 'NASDAQ', sector: 'Semiconductors', close: 150, weight: 20},
  ].map(s => ({...s, currency: 'USD', date: '2026-10-26', held: false, watched: false}))
  let saved = {currency: 'USD', risk: 'BALANCED', horizon_years: 5, budget: 10000, allocations: stocks.map(s => ({stock_id: s.stock_id, weight: s.weight}))}
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    let data: unknown = {}
    if (path.endsWith('/auth/me')) data = {id: 1, display_name: 'Akash'}
    else if (path.endsWith('/auth/csrf')) data = {token: 'fixture', headerName: 'X-CSRF-TOKEN'}
    else if (path.endsWith('/assistant/status')) data = {available: false}
    else if (path.endsWith('/portfolio-plan')) {
      if (route.request().method() === 'PUT') saved = route.request().postDataJSON()
      data = {...saved, saved: true, stocks: saved.allocations.map(a => ({...stocks.find(s => s.stock_id === a.stock_id), weight: a.weight}))}
    }
    await route.fulfill({json: data})
  })
  await page.setViewportSize({width: 1440, height: 1000})
  await page.goto('/portfolio-lab')
  await expect(page.locator('.allocation-row')).toHaveCount(3)
  await page.evaluate(() => document.fonts.ready)
  await expect(page.locator('.brand-mark, .company-mark, .assistant-cover-orb')).toHaveCount(0)
  await page.getByRole('button', {name: 'Lock target for AAPL', exact: true}).click()
  await page.getByRole('button', {name: 'Equal weights', exact: true}).click()
  await expect(page.getByLabel('Target weight for AAPL', {exact: true})).toHaveValue('50')
  await expect(page.getByLabel('Target weight for AAPL', {exact: true})).toBeDisabled()
  await expect(page.getByLabel('Target weight for MSFT', {exact: true})).toHaveValue('25')
  await expect(page.getByLabel('Target weight for NVDA', {exact: true})).toHaveValue('25')
  await page.getByRole('button', {name: 'Undo', exact: true}).click()
  await expect(page.getByLabel('Target weight for MSFT', {exact: true})).toHaveValue('30')
  await page.getByRole('button', {name: 'Redo', exact: true}).click()
  await expect(page.getByLabel('Target weight for MSFT', {exact: true})).toHaveValue('25')
  await page.getByLabel('Target weight for MSFT', {exact: true}).fill('15')
  await page.getByRole('button', {name: 'Distribute cash', exact: true}).click()
  await expect(page.getByLabel('Target weight for MSFT', {exact: true})).toHaveValue('18.75')
  await expect(page.getByLabel('Target weight for NVDA', {exact: true})).toHaveValue('31.25')
  await page.getByRole('button', {name: 'Unlock target for AAPL', exact: true}).click()
  await page.getByRole('button', {name: 'Equal weights', exact: true}).click()
  await expect(page.getByLabel('Target weight for AAPL', {exact: true})).toHaveValue('33.33')
  await expect(page.getByLabel('Target weight for MSFT', {exact: true})).toHaveValue('33.33')
  await expect(page.getByLabel('Target weight for NVDA', {exact: true})).toHaveValue('33.34')
  await page.getByLabel('Target weight for AAPL', {exact: true}).fill('50')
  await page.getByLabel('Target weight for MSFT', {exact: true}).fill('30')
  await page.getByLabel('Target weight for NVDA', {exact: true}).fill('10')
  const slider = page.getByLabel('Adjust target for NVDA', {exact: true})
  await slider.scrollIntoViewIfNeeded()
  const bounds = await slider.boundingBox()
  if (!bounds) throw new Error('Weight slider was not rendered')
  await page.mouse.move(bounds.x + bounds.width * .1, bounds.y + bounds.height / 2)
  await page.mouse.down()
  await page.mouse.move(bounds.x + bounds.width * .25, bounds.y + bounds.height / 2, {steps: 10})
  await page.mouse.up()
  await expect(page.getByLabel('Target weight for NVDA', {exact: true})).not.toHaveValue('10')
  await page.getByRole('button', {name: 'Undo', exact: true}).click()
  await expect(page.getByLabel('Target weight for NVDA', {exact: true})).toHaveValue('10')
  await page.getByLabel('Market decline scenario', {exact: true}).fill('25')
  await expect(page.locator('.stress-results')).toContainText('−$2,250')
  await expect(page.locator('.stress-results')).toContainText('$7,750')
  await expect(page.locator('.allocation-shares>strong')).toHaveText(['50', '15', '6'])
  await page.getByRole('button', {name: 'Compare with saved', exact: true}).click()
  await expect(page.locator('.comparison-row').filter({hasText: 'NVDA'})).toContainText('-10.00 pp')
  await page.getByRole('button', {name: 'Build allocation', exact: true}).click()
  await page.screenshot({path: '../.local/allocation-studio-desktop.png', fullPage: true})
  await page.getByRole('button', {name: 'Switch to dark theme', exact: true}).click()
  await page.screenshot({path: '../.local/allocation-studio-dark.png', fullPage: true})
  await page.getByRole('button', {name: 'Switch to light theme', exact: true}).click()
  await page.getByRole('button', {name: 'Save draft', exact: true}).click()
  await expect(page.getByText('Draft saved to your account.', {exact: true})).toBeVisible()
  expect(saved.allocations).toEqual([{stock_id: 31, weight: 50}, {stock_id: 32, weight: 30}, {stock_id: 33, weight: 10}])
  await page.reload()
  await expect(page.getByLabel('Target weight for NVDA', {exact: true})).toHaveValue('10')
  await page.getByLabel('Market & currency', {exact: true}).selectOption('INR')
  await expect(page.locator('.allocation-row')).toHaveCount(0)
  await page.getByLabel('Market & currency', {exact: true}).selectOption('USD')
  await expect(page.locator('.allocation-row')).toHaveCount(3)
  await page.setViewportSize({width: 390, height: 844})
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({path: '../.local/allocation-studio-mobile.png', fullPage: true})
})
