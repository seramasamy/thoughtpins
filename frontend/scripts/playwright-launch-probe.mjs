import { chromium } from "@playwright/test";

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 360, height: 240 } });
  await page.setContent("<main>Thought Pins browser launch probe</main>");
  const text = await page.locator("main").textContent();
  if (text !== "Thought Pins browser launch probe") {
    throw new Error("Playwright browser probe rendered unexpected content");
  }
  console.log("Playwright browser launch completed");
} finally {
  await browser.close();
}
