import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const baseUrl = process.env.THOUGHTPINS_LIVE_URL || "http://127.0.0.1:8420/app/";
const outputDir = resolve(process.cwd(), "..", "reports");
const viewports = [
  { name: "desktop", width: 1440, height: 960 },
  { name: "mobile", width: 390, height: 844 },
];

await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch();
const results = [];

try {
  for (const viewport of viewports) {
    const page = await browser.newPage({ viewport });
    await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 60_000 });
    await page.screenshot({ path: resolve(outputDir, `live-ui-${viewport.name}.png`), fullPage: true });
    const title = await page.locator("h1").first().textContent();
    const horizontalOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    const composer = page.locator(".chat-composer");
    const composerBox = await composer.boundingBox();
    const mobileNavBox = viewport.name === "mobile" ? await page.locator(".mobile-tabbar").boundingBox() : null;
    const composerNavOverlap = composerBox && mobileNavBox
      ? Math.max(0, Math.round(composerBox.y + composerBox.height - mobileNavBox.y))
      : 0;
    results.push({
      viewport: viewport.name,
      title,
      horizontalOverflow,
      composerVisible: await composer.isVisible(),
      composerNavOverlap,
    });
    await page.close();
  }
} finally {
  await browser.close();
}

console.log(JSON.stringify({ url: baseUrl, results }, null, 2));

if (results.some((result) => result.horizontalOverflow > 1 || !result.composerVisible || result.composerNavOverlap > 0)) {
  process.exitCode = 1;
}
