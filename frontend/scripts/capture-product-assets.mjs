import { chromium } from "playwright";
import { resolve } from "node:path";

const appUrl = process.env.THOUGHTPINS_LIVE_URL || "http://127.0.0.1:5179/app/";
const siteAssets = resolve(process.cwd(), "..", "site", "assets");
const captures = [
  { name: "product-chat-desktop.png", width: 1440, height: 1000 },
  { name: "product-chat-mobile.png", width: 390, height: 844 },
];

const browser = await chromium.launch();
try {
  for (const capture of captures) {
    const page = await browser.newPage({
      viewport: { width: capture.width, height: capture.height },
      serviceWorkers: "block",
    });
    const captureUrl = new URL(appUrl);
    captureUrl.searchParams.set("capture", String(Date.now()));
    const response = await page.goto(captureUrl.href, { waitUntil: "networkidle", timeout: 60_000 });
    if (!response?.ok()) throw new Error(`${capture.name}: app returned ${response?.status() || "no response"}`);
    await page.locator("h1", { hasText: "Chat" }).waitFor();
    await page.getByRole("checkbox", { name: "Use private memories in this reply" }).waitFor();
    if (await page.getByRole("checkbox", { name: "Use private memories in this reply" }).isChecked()) {
      await page.getByRole("checkbox", { name: "Use private memories in this reply" }).uncheck();
    }
    await page.getByText("Private memories stay out of replies", { exact: true }).waitFor({ state: "attached" });
    if (capture.width <= 700) {
      await page.getByText("Private off", { exact: true }).waitFor();
    } else {
      await page.getByText("Use private memories", { exact: true }).waitFor();
    }
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    if (overflow > 1) throw new Error(`${capture.name}: horizontal overflow is ${overflow}px`);
    await page.screenshot({ path: resolve(siteAssets, capture.name), fullPage: false });
    await page.close();
  }
} finally {
  await browser.close();
}

console.log(`Updated ${captures.length} canonical product captures from ${appUrl}`);
