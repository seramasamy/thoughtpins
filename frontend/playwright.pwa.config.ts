import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "pwa-offline.spec.ts",
  timeout: 45_000,
  fullyParallel: false,
  use: {
    baseURL: "http://127.0.0.1:5198",
    serviceWorkers: "allow",
  },
  webServer: {
    command: "npm run preview -- --port 5198 --strictPort",
    url: "http://127.0.0.1:5198/app/",
    reuseExistingServer: false,
    timeout: 30_000,
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
