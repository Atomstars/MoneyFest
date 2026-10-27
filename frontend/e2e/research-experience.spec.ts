import { test, expect } from '@playwright/test'

test('sector spotlight and headline filters update together in the new colour system', async ({ page }) => {
  const story = (headline: string, sentiment: string, id: number) => ({headline, sentiment, source: 'Example publisher', url: `https://example.com/story-${id}`, published_at: '2026-10-27T04:00:00Z'})
  const macro = [story('Global earnings rise as companies report results', 'POSITIVE', 1), story('Export demand falls in the latest update', 'NEGATIVE', 2), story('Central bank policy meeting scheduled this week', 'NEUTRAL', 3)]
  const banking = [story('Bank earnings rise in quarterly report', 'POSITIVE', 4), story('Bank wins a new services contract', 'POSITIVE', 5)]
  const themes = [['MACRO', 'Macro & global'], ['BANKING', 'Banking'], ['TECH', 'Technology'], ['ENERGY', 'Energy'], ['PHARMA', 'Pharma'], ['AUTO', 'Auto']].map(([id, label]) => ({id, label, signal: id === 'BANKING' ? 'POSITIVE' : 'MIXED', focus: id === 'MACRO' ? 'Macro policy and flows' : null, positive: id === 'BANKING' ? 2 : 1, negative: id === 'BANKING' ? 0 : 1, events: id === 'MACRO' ? macro : id === 'BANKING' ? banking : macro.slice(0, 2), sync: []}))
  const errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    const data = path.endsWith('/auth/me') ? {id: 1, display_name: 'Akash'} : path.endsWith('/research/themes') ? themes : path.endsWith('/assistant/status') ? {available: false} : {}
    await route.fulfill({json: data})
  })
  await page.setViewportSize({width: 1440, height: 1000})
  await page.goto('/research')
  await expect(page.getByRole('heading', {name: 'Research desk', exact: true})).toBeVisible()
  await expect(page.getByRole('group', {name: 'Select a research sector'}).getByRole('button')).toHaveCount(6)
  await expect(page.locator('.evidence-story')).toHaveCount(3)
  await expect(page.getByRole('link', {name: /Try the portfolio coach/})).toBeVisible()
  await page.screenshot({path: '../.local/research-vivid-desktop.png', fullPage: true})
  await page.getByRole('button', {name: 'Switch to dark theme', exact: true}).click()
  await page.screenshot({path: '../.local/research-vivid-dark.png', fullPage: true})
  await page.getByRole('button', {name: 'Switch to light theme', exact: true}).click()
  const counts = page.getByRole('group', {name: 'Filter selected sector headlines'})
  await counts.getByRole('button', {name: /Positive tone/}).click()
  await expect(page.locator('.evidence-story')).toHaveCount(1)
  await expect(page.getByRole('heading', {name: macro[0].headline, exact: true})).toBeVisible()
  await page.getByRole('group', {name: 'Headline tone', exact: true}).getByRole('button', {name: 'Negative', exact: true}).click()
  await expect(page.getByRole('heading', {name: macro[1].headline, exact: true})).toBeVisible()
  await page.getByRole('group', {name: 'Select a research sector'}).getByRole('button', {name: /Banking/}).click()
  await expect(page.locator('#market-lens-title')).toHaveText('Banking')
  await expect(page.locator('.evidence-story')).toHaveCount(2)
  await counts.getByRole('button', {name: /Negative tone/}).click()
  await expect(page.getByRole('heading', {name: 'No stories with this tone', exact: true})).toBeVisible()
  await page.getByRole('button', {name: 'Show all stories', exact: true}).click()
  await expect(page.locator('.evidence-story')).toHaveCount(2)
  await page.getByRole('button', {name: 'What news matters to my portfolio?', exact: true}).click()
  await expect(page.getByLabel('Your research question')).toHaveValue('What news matters to my portfolio?')
  await expect(page.getByRole('button', {name: 'Ask Moneyfest', exact: true})).toBeDisabled()
  await page.setViewportSize({width: 390, height: 844})
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.getByRole('group', {name: 'Select a research sector'}).getByRole('button', {name: /Macro & policy/}).click()
  await page.screenshot({path: '../.local/research-vivid-mobile.png', fullPage: true})
  await page.emulateMedia({reducedMotion: 'reduce'})
  await page.getByRole('group', {name: 'Select a research sector'}).getByRole('button', {name: /Energy/}).click()
  expect(await page.locator('.market-lens').evaluate(e => getComputedStyle(e).animationName)).toBe('none')
  expect(errors).toEqual([])
})
