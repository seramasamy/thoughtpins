import { defineConfig, devices } from "@playwright/test";
import base from "./playwright.config";

// Exercise the critical authentication, recovery and visual contracts on the
// independent Gecko engine, alongside Chromium and the iOS WebKit matrix.
export default defineConfig({
  ...base,
  testMatch: ["auth-recovery.spec.ts", "session-recovery.spec.ts", "robustness.spec.ts", "modern-ui.spec.ts"],
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "../reports/playwright-firefox.json" }]],
  projects: [{ name: "firefox", use: { ...devices["Desktop Firefox"] } }],
});
