import { defineConfig, devices } from '@playwright/test'

// Real-browser tests. They start Flask and Vite when those are not already running.
// Set E2E_CHANNEL=chrome to use an installed Chrome, or run `npx playwright install chromium` once.
// Set E2E_WEBKIT=1 to also run in WebKit (Safari's engine): `npx playwright install webkit` once.
// Set E2E_BACKEND_COMMAND when the Python path differs (for example on Windows).
export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.e2e.js',
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'chrome', use: { channel: process.env.E2E_CHANNEL || undefined } },
    ...(process.env.E2E_WEBKIT === '1' ? [{ name: 'webkit', use: { ...devices['Desktop Safari'] } }] : []),
  ],
  webServer: [
    {
      command: process.env.E2E_BACKEND_COMMAND || '../.venv/bin/python app.py',
      cwd: '../backend',
      url: 'http://localhost:5001/api/health',
      reuseExistingServer: true,
      timeout: 60000,
    },
    {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: true,
      timeout: 60000,
    },
  ],
})
