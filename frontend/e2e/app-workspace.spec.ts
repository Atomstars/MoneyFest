import { test, expect } from '@playwright/test'

test('news is a persistent inbox with a reader, saved stories and stock research actions', async ({ page }) => {
  let owner = 41
  let failRead = false
  const read = new Set<number>()
  const stories = [
    { id: 1, stock_id: 11, ticker: 'TCS', name: 'Tata Consultancy Services', exchange: 'NSE', headline: 'TCS announces a new services contract', summary: 'The company has announced a new services contract in its latest update.', sentiment: 'POSITIVE', source: 'Example publisher', url: 'https://example.com/story-1', published_at: '2026-10-27T08:00:00Z' },
    { id: 2, stock_id: 12, ticker: 'AAPL.US', name: 'Apple Inc.', exchange: 'NASDAQ', headline: 'Apple schedules its quarterly earnings call', summary: 'Apple schedules its quarterly earnings call', sentiment: 'NEUTRAL', source: 'Example newswire', url: 'https://example.com/story-2', published_at: '2026-10-27T07:00:00Z' },
    { id: 3, stock_id: 13, ticker: 'INFY', name: 'Infosys', exchange: 'NSE', headline: 'Infosys shares fall after the latest update', summary: 'Infosys shares fall after the latest update', sentiment: 'NEGATIVE', source: 'Example business desk', url: 'https://example.com/story-3', published_at: '2026-10-27T06:00:00Z' },
  ]
  const errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url()), path = url.pathname
    let data: unknown = {}
    if (path.endsWith('/auth/me')) data = { id: owner, display_name: 'Akash', email: 'preview@example.com' }
    else if (path.endsWith('/auth/csrf')) data = { token: 'fixture', headerName: 'X-CSRF-TOKEN' }
    else if (/\/news\/\d+\/read$/.test(path)) {
      if (failRead) return route.fulfill({ status: 503, json: { detail: 'Unavailable' } })
      read.add(Number(path.split('/').at(-2))); data = { ok: true }
    }
    else if (path.endsWith('/me/news')) {
      const items = stories.filter(x => (url.searchParams.get('sentiment') === 'ALL' || x.sentiment === url.searchParams.get('sentiment')) && (url.searchParams.get('unread') !== 'true' || !read.has(x.id))).map(x => ({ ...x, read: read.has(x.id) }))
      data = { items, total: items.length, sync: [], refreshing: false }
    }
    else if (path.endsWith('/assistant/status')) data = { available: false }
    else if (path.endsWith('/stocks')) data = []
    else if (path.endsWith('/funds')) data = { items: [], has_more: false }
    await route.fulfill({ json: data })
  })
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto('/news')
  await expect(page.locator('.app-rail')).toBeVisible()
  await expect(page.locator('.inbox-headline')).toHaveCount(3)
  await expect(page.getByRole('region', { name: 'Headline detail' }).getByRole('heading', { name: stories[0].headline })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Read at Example publisher', exact: true })).toHaveAttribute('href', stories[0].url)
  await expect(page.locator('.reader-company')).toHaveAttribute('href', '/stock-research?stockId=11')
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByRole('group', { name: 'News inbox' }).getByRole('button', { name: /Saved/ }).click()
  await expect(page.locator('.inbox-headline')).toHaveCount(1)
  await page.reload()
  await page.getByRole('group', { name: 'News inbox' }).getByRole('button', { name: /Saved/ }).click()
  await expect(page.locator('.inbox-headline')).toHaveCount(1)
  await page.getByRole('button', { name: 'All news', exact: true }).click()
  await page.locator('.inbox-headline').first().focus()
  await page.keyboard.press('ArrowDown')
  await expect(page.getByRole('region', { name: 'Headline detail' }).getByRole('heading', { name: stories[1].headline })).toBeVisible()
  await page.getByLabel('Search headlines on this page').fill('INFY')
  await expect(page.locator('.inbox-headline')).toHaveCount(1)
  await page.getByLabel('Clear headline search').click()
  await page.getByRole('button', { name: 'Positive', exact: true }).click()
  await expect(page.locator('.inbox-headline')).toHaveCount(1)
  failRead = true
  await page.getByRole('button', { name: 'Mark read', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Could not mark')
  await expect(page.getByRole('button', { name: 'Mark read', exact: true })).toBeEnabled()
  failRead = false
  await page.getByRole('button', { name: 'Mark read', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Read', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'All tones', exact: true }).click()
  await page.getByLabel('Collapse navigation', { exact: true }).click()
  await expect(page.locator('.native-app')).toHaveClass(/navigation-collapsed/)
  await page.reload()
  await expect(page.locator('.native-app')).toHaveClass(/navigation-collapsed/)
  await page.getByLabel('Expand navigation', { exact: true }).click()
  await page.keyboard.press('Control+k')
  await expect(page.getByLabel('Search workspace')).toBeFocused()
  await page.keyboard.press('Escape')
  await page.getByRole('heading', { name: 'News & alerts', exact: true }).click()
  await page.screenshot({ path: '../.local/app-news-desktop.png' })
  await page.getByRole('button', { name: 'Switch to dark theme' }).click()
  await page.waitForTimeout(200)
  await page.screenshot({ path: '../.local/app-news-dark.png' })
  await page.getByRole('button', { name: 'Switch to light theme' }).click()
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.locator('.app-rail')).not.toBeVisible()
  await expect(page.getByRole('region', { name: 'Headline detail' })).not.toBeVisible()
  await page.screenshot({ path: '../.local/app-news-mobile-inbox.png' })
  await page.locator('.inbox-headline').nth(1).click()
  await expect(page.getByRole('region', { name: 'Headline detail' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Headline detail' }).getByRole('heading')).toBeFocused()
  await page.screenshot({ path: '../.local/app-news-mobile-reader.png' })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.getByRole('button', { name: 'Inbox', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Headline detail' })).not.toBeVisible()
  await expect(page.locator('.inbox-headline').nth(1)).toBeFocused()
  owner = 42
  await page.reload()
  await page.getByRole('group', { name: 'News inbox' }).getByRole('button', { name: /Saved/ }).click()
  await expect(page.getByText('Keep the stories that matter')).toBeVisible()
  expect(errors).toEqual([])
})
