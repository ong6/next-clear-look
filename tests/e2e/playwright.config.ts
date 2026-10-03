import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  outputDir: '../../test-results/e2e',
  reporter: [['list'], ['html', { outputFolder: '../../playwright-report', open: 'never' }]],
  retries: 0,
  use: {
    baseURL: process.env.NCL_BASE_URL ?? 'http://127.0.0.1:4173',
    colorScheme: 'dark',
    launchOptions: process.env.NCL_CHROMIUM_EXECUTABLE || process.env.NCL_CHROMIUM_USE_METAL === '1'
      ? {
          executablePath: process.env.NCL_CHROMIUM_EXECUTABLE,
          args: process.env.NCL_CHROMIUM_USE_METAL === '1' ? ['--use-angle=metal'] : undefined,
        }
      : undefined,
    locale: 'en-SG',
    timezoneId: 'UTC',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
  },
  expect: {
    toHaveScreenshot: {
      animations: 'disabled',
      maxDiffPixelRatio: 0.01,
    },
  },
  projects: [
    {
      name: 'desktop-1440',
      use: { ...devices['Desktop Chrome'], deviceScaleFactor: 1, viewport: { width: 1440, height: 900 } },
    },
    {
      name: 'mobile-390',
      use: {
        ...devices['iPhone 13'],
        browserName: 'chromium',
        deviceScaleFactor: 1,
        viewport: { width: 390, height: 844 },
      },
    },
  ],
});
