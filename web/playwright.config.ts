import { defineConfig } from "@playwright/test";

const useRealServer = process.env.NCL_E2E_REAL === "1";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  retries: 0,
  reporter: [["line"]],
  use: {
    baseURL: process.env.NCL_BASE_URL ?? "http://127.0.0.1:5180",
    channel: "chrome",
    colorScheme: "dark",
    reducedMotion: "no-preference",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: useRealServer
    ? undefined
    : {
        command: "pnpm dev --host 127.0.0.1 --port 5180",
        url: "http://127.0.0.1:5180",
        reuseExistingServer: false,
        env: { VITE_NCL_MOCK: "1", VITE_NCL_TEST: "1" },
      },
  projects: [
    { name: "desktop-1440", use: { viewport: { width: 1440, height: 900 } } },
    { name: "mobile-390", use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
  ],
});
