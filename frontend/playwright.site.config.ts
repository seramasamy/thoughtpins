import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./site-e2e",
  timeout: 45_000,
  expect: { timeout: 8_000 },
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "../reports/site-ui-results.json" }]],
  use: { baseURL: "http://127.0.0.1:8878", screenshot: "only-on-failure", trace: "retain-on-failure" },
  webServer: {
    command: "node scripts/serve-site-review.mjs",
    url: "http://127.0.0.1:8878",
    reuseExistingServer: !process.env.CI,
  },
  projects: [
    { name: "chromium", use: { browserName: "chromium", launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined } } },
    { name: "webkit", use: { browserName: "webkit" } },
  ],
});
