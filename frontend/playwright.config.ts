import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  timeout: 60000,
  reporter: 'list',
  use: {
    baseURL: process.env.E2E_URL ?? 'http://127.0.0.1:5175',
    channel: process.env.E2E_BROWSER ?? 'chrome',
    launchOptions: { args: ['--disable-gpu', '--renderer-process-limit=2'] },
    trace: 'retain-on-failure',
    viewport: { width: 1280, height: 900 },
  },
})
