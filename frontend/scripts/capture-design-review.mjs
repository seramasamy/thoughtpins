import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const outputDir = resolve(process.cwd(), "..", "reports", "design-review");
await mkdir(outputDir, { recursive: true });

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  await page.goto(process.env.THOUGHTPINS_LIVE_URL || "http://127.0.0.1:8420/", { waitUntil: "networkidle" });
  for (const [name, selector] of [
    ["hero", ".hero"],
    ["features", "#features"],
    ["product", ".product-section"],
    ["workflow", ".workflow-band"],
    ["privacy", ".privacy-band"],
  ]) {
    const section = page.locator(selector);
    let chromeStyle = null;
    if (name === "product") {
      chromeStyle = await page.addStyleTag({ content: ".skip-link, .site-header { visibility: hidden !important; }" });
    }
    await section.screenshot({ path: resolve(outputDir, `site-${name}-desktop.png`) });
    await chromeStyle?.evaluate((element) => element.remove());
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload({ waitUntil: "networkidle" });
  const mobileChromeStyle = await page.addStyleTag({ content: ".skip-link, .site-header { visibility: hidden !important; }" });
  await page.locator(".product-section").screenshot({ path: resolve(outputDir, "site-product-mobile.png") });
  await mobileChromeStyle.evaluate((element) => element.remove());
} finally {
  await browser.close();
}
