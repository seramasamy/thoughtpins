import AxeBuilder from "@axe-core/playwright";
import { chromium, firefox, webkit } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const baseUrl = (process.env.THOUGHTPINS_LIVE_URL || "http://127.0.0.1:8420").replace(/\/$/, "");
const outputDir = resolve(process.cwd(), "..", "reports", "cross-browser");
const engines = [
  ["chromium", chromium],
  ["firefox", firefox],
  ["webkit", webkit],
];
const viewports = [
  { name: "desktop", width: 1440, height: 960 },
  { name: "wide-desktop", width: 1920, height: 1080 },
  { name: "iphone", width: 390, height: 844 },
  { name: "android", width: 412, height: 915 },
  { name: "small-mobile", width: 320, height: 568 },
  { name: "iphone-landscape", width: 844, height: 390 },
  { name: "ipad-portrait", width: 834, height: 1194 },
  { name: "ipad-landscape", width: 1133, height: 744 },
];

function usesMobileNavigation(viewport) {
  return viewport.width <= 700 || (viewport.height <= 500 && viewport.width <= 960);
}

await mkdir(outputDir, { recursive: true });
const results = [];
const failures = [];

for (const [engineName, browserType] of engines) {
  const browser = await browserType.launch();
  try {
    for (const viewport of viewports) {
      const context = await browser.newContext({
        viewport: { width: viewport.width, height: viewport.height },
        colorScheme: "light",
        reducedMotion: "reduce",
      });
      const page = await context.newPage();
      const runtimeErrors = [];
      const failedResources = [];
      page.on("pageerror", (error) => runtimeErrors.push(error.message));
      page.on("console", (message) => {
        if (message.type() === "error" && !message.text().startsWith("Failed to load resource:")) {
          runtimeErrors.push(message.text());
        }
      });
      page.on("response", (response) => {
        if (response.status() >= 400) failedResources.push(`${response.status()} ${response.url()}`);
      });
      page.on("requestfailed", (request) => {
        failedResources.push(`request failed ${request.url()}: ${request.failure()?.errorText || "unknown error"}`);
      });

      const siteResponse = await page.goto(`${baseUrl}/`, { waitUntil: "networkidle", timeout: 60_000 });
      const site = await page.evaluate(() => ({
        heading: document.querySelector("h1")?.textContent?.trim() || "",
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        logoLoaded: [...document.querySelectorAll(".site-brand img")].some((node) => node instanceof HTMLImageElement && node.complete && node.naturalWidth > 0),
        primaryTarget: document.querySelector("[data-primary-cta]")?.getAttribute("href") || "",
      }));
      const siteAxe = await blockingAxe(page);
      await page.screenshot({ path: resolve(outputDir, `${engineName}-site-${viewport.name}.png`), fullPage: true });

      const appResponse = await page.goto(`${baseUrl}/app/`, { waitUntil: "networkidle", timeout: 60_000 });
      const composer = page.locator(".chat-composer");
      const mobileNav = page.locator(".mobile-tabbar");
      const navBox = usesMobileNavigation(viewport) && await mobileNav.count() ? await mobileNav.boundingBox() : null;
      const app = await page.evaluate(() => ({
        heading: document.querySelector("h1")?.textContent?.trim() || "",
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      }));
      if (usesMobileNavigation(viewport)) {
        const people = mobileNav.getByRole("button", { name: "People" });
        await people.click();
        await page.getByRole("heading", { level: 1, name: "People", exact: true }).waitFor();
        await mobileNav.getByRole("button", { name: "Chat" }).click();
      }
      await page.waitForTimeout(50);
      const composerBox = await composer.boundingBox();
      const composerOverlap = composerBox && navBox
        ? Math.max(0, Math.round(composerBox.y + composerBox.height - navBox.y))
        : 0;
      await page.waitForFunction(
        () => document.querySelector(".chat-welcome h2, .chat-message-row:not(.thinking-row)"),
        undefined,
        { timeout: 10_000 },
      );
      // Capture the asynchronous empty/populated state atomically. The API can
      // replace the welcome view while the audit is measuring it.
      const chatSnapshot = await page.evaluate(() => {
        const visible = (node) => {
          if (!(node instanceof HTMLElement)) return false;
          const style = getComputedStyle(node);
          const box = node.getBoundingClientRect();
          return style.display !== "none" && style.visibility !== "hidden" && box.width > 0 && box.height > 0;
        };
        const heading = document.querySelector(".chat-welcome h2");
        const headingVisible = visible(heading);
        const headingBox = headingVisible ? heading.getBoundingClientRect() : null;
        const starterBoxes = headingVisible
          ? [...document.querySelectorAll(".starter-list button")]
              .filter(visible)
              .map((node) => {
                const box = node.getBoundingClientRect();
                return { top: box.top, bottom: box.bottom };
              })
          : [];
        const populatedVisible = [...document.querySelectorAll(".chat-message-row:not(.thinking-row)")].some(visible);
        return {
          emptyChatHeadingVisible: headingVisible,
          emptyChatHeadingBox: headingBox
            ? { x: headingBox.x, y: headingBox.y, width: headingBox.width, height: headingBox.height }
            : null,
          starterBoxes,
          populatedChatVisible: populatedVisible,
        };
      });
      const {
        emptyChatHeadingVisible,
        emptyChatHeadingBox,
        starterBoxes,
        populatedChatVisible,
      } = chatSnapshot;
      const welcomeBottom = emptyChatHeadingBox
        ? Math.max(emptyChatHeadingBox.y + emptyChatHeadingBox.height, ...starterBoxes.map((box) => box.bottom))
        : null;
      const welcomeClearOfComposer = !emptyChatHeadingVisible || Boolean(
        emptyChatHeadingBox
        && emptyChatHeadingBox.y >= 0
        && welcomeBottom !== null
        && welcomeBottom <= (composerBox?.y ?? viewport.height)
        && welcomeBottom <= viewport.height,
      );
      const chatContentVisible = emptyChatHeadingVisible || populatedChatVisible;
      const appAxe = await blockingAxe(page);
      await page.screenshot({ path: resolve(outputDir, `${engineName}-app-${viewport.name}.png`), fullPage: true });

      const result = {
        engine: engineName,
        viewport: viewport.name,
        site: { status: siteResponse?.status() || 0, ...site, axe: siteAxe },
        app: {
          status: appResponse?.status() || 0,
          ...app,
          composerVisible: await composer.isVisible(),
          composerOverlap,
          emptyChatHeadingVisible,
          populatedChatVisible,
          chatContentVisible,
          welcomeClearOfComposer,
          composerTop: composerBox ? Math.round(composerBox.y) : null,
          welcomeBottom: welcomeBottom === null ? null : Math.round(welcomeBottom),
          axe: appAxe,
        },
        runtimeErrors,
        failedResources: [...new Set(failedResources)],
      };
      results.push(result);
      const prefix = `${engineName}/${viewport.name}`;
      if (!siteResponse?.ok() || site.heading !== "Thought Pins") failures.push(`${prefix}: homepage unavailable`);
      if (site.overflow > 1 || app.overflow > 1) failures.push(`${prefix}: horizontal overflow`);
      if (!site.logoLoaded || !site.primaryTarget.includes("/app/")) failures.push(`${prefix}: homepage asset or CTA failed`);
      if (!appResponse?.ok() || app.heading !== "Chat" || !result.app.composerVisible) failures.push(`${prefix}: app shell unavailable`);
      if (!chatContentVisible) failures.push(`${prefix}: neither empty nor populated Chat content is visible`);
      if (!welcomeClearOfComposer) failures.push(`${prefix}: empty Chat welcome is clipped or occluded by the composer`);
      if (composerOverlap > 0) failures.push(`${prefix}: composer overlaps mobile navigation by ${composerOverlap}px`);
      if (siteAxe.length || appAxe.length) failures.push(`${prefix}: serious accessibility violation`);
      if (runtimeErrors.length) failures.push(`${prefix}: browser runtime errors: ${runtimeErrors.join(" | ")}`);
      if (result.failedResources.length) failures.push(`${prefix}: failed resources: ${result.failedResources.join(" | ")}`);
      await context.close();
    }
  } finally {
    await browser.close();
  }
}

const report = { url: baseUrl, generatedAt: new Date().toISOString(), results, failures };
await writeFile(resolve(outputDir, "report.json"), `${JSON.stringify(report, null, 2)}\n`, "utf8");
console.log(JSON.stringify(report, null, 2));
if (failures.length) process.exitCode = 1;

async function blockingAxe(page) {
  const analysis = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  return analysis.violations
    .filter((violation) => ["serious", "critical"].includes(violation.impact || ""))
    .map((violation) => violation.id);
}
