import { defineConfig, devices } from "@playwright/test";

/**
 * The iOS device matrix, run against WebKit rather than Chromium.
 *
 * The web app is what an iPhone or iPad actually loads before the native shell
 * ships, and it is what App Review sees if they open the marketing site. The
 * default smoke config runs one desktop Chromium profile, which cannot see a
 * safe-area inset, a 320pt iPad Slide Over window, or a WebKit-only layout
 * difference. This config is separate so the fast smoke stays fast.
 *
 * Widths and heights below are CSS pixels for real shipping hardware, not
 * Playwright's rounded presets.
 */
export default defineConfig({
  testDir: "./e2e",
  testMatch: "ios-device-matrix.spec.ts",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "../reports/playwright-ios-matrix.json" }]],
  use: {
    baseURL: "http://127.0.0.1:5179",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...devices["Desktop Safari"],
  },
  webServer: {
    command: "npm run dev -- --port 5179",
    url: "http://127.0.0.1:5179/app/",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [{ name: "webkit", use: { ...devices["Desktop Safari"] } }],
});
