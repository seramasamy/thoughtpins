import { AxeBuilder } from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { installMockApi } from "./mockApi";

/**
 * Every shipping iOS size the app has to survive, driven through WebKit.
 *
 * Two of these are not optional. `iPhone SE` is the narrowest device that can
 * run iOS 17, so it is the floor for the deployment target. `iPad Slide Over`
 * is 320 CSS pixels wide — narrower than any iPhone — and the app is a
 * universal target without `UIRequiresFullScreen`, so iPadOS can put it in that
 * window whether or not the layout was designed for it.
 */
const devices = [
  { name: "iPhone SE (3rd gen)", width: 375, height: 667, ipad: false },
  { name: "iPhone 13 mini", width: 375, height: 812, ipad: false },
  { name: "iPhone 16", width: 393, height: 852, ipad: false },
  { name: "iPhone 16 Pro Max", width: 430, height: 932, ipad: false },
  { name: "iPhone 16 landscape", width: 852, height: 393, ipad: false },
  { name: "iPad Slide Over", width: 320, height: 1024, ipad: true },
  { name: "iPad mini portrait", width: 744, height: 1133, ipad: true },
  { name: "iPad Air 11 portrait", width: 820, height: 1180, ipad: true },
  { name: "iPad Pro 13 landscape", width: 1366, height: 1024, ipad: true },
];

/** Apple's Human Interface Guidelines minimum, in CSS pixels. */
const MIN_TAP_TARGET = 44;

type Offender = { label: string; width: number; height: number };

async function bootApp(page: Page, width: number, height: number) {
  await page.setViewportSize({ width, height });
  await installMockApi(page, "local", 0, "product");
  await page.goto("/app/");
  await expect(page.getByRole("heading", { level: 1, name: "Chat", exact: true })).toBeVisible();
  // Fonts and the canvas mark settle after first paint; measuring before they
  // do reports layout that no user ever sees.
  await page.waitForLoadState("networkidle");
}

/**
 * Controls smaller than the HIG minimum, measured the way a finger meets them.
 *
 * Three exemptions, each because the element is not what anyone actually taps:
 *
 * - Inline links inside running text. Apple's rule is about standalone
 *   controls, and flagging every word-level link buries the real offenders.
 * - Visually hidden inputs. The file picker is a 1px sr-only `input[type=file]`
 *   driven by a visible button beside it; its own box is not a target.
 * - Inputs wrapped in a label. Tapping the label activates the input, so the
 *   label's box is the target — this is how the private-memory checkbox stays
 *   14px while remaining easy to hit.
 */
async function undersizedTapTargets(page: Page): Promise<Offender[]> {
  return page.evaluate((minimum) => {
    const selector = "button, a[href], input, select, textarea, [role=button], [role=tab], [role=switch]";
    const offenders: Offender[] = [];
    for (const node of Array.from(document.querySelectorAll(selector))) {
      const element = node as HTMLElement;
      const style = getComputedStyle(element);
      if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") continue;
      if (element.closest("[hidden]") || element.hasAttribute("hidden")) continue;
      if (element.getAttribute("aria-hidden") === "true") continue;
      if (element.classList.contains("visually-hidden")) continue;

      let rect = element.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue;

      const isInlineLink =
        element.tagName === "A" && style.display.startsWith("inline") && Boolean(element.closest("p, li, small"));
      if (isInlineLink) continue;

      const wrappingLabel = element.tagName === "INPUT" ? element.closest("label") : null;
      if (wrappingLabel) rect = wrappingLabel.getBoundingClientRect();

      if (rect.width < minimum || rect.height < minimum) {
        const label =
          element.getAttribute("aria-label") ||
          (element.textContent || "").trim().slice(0, 40) ||
          `${element.tagName.toLowerCase()}.${element.className}`.slice(0, 60);
        offenders.push({ label, width: Math.round(rect.width), height: Math.round(rect.height) });
      }
    }
    return offenders;
  }, MIN_TAP_TARGET);
}

/** Anything pushing the document wider than the window, which iOS renders as a rubber-band scroll. */
async function horizontalOverflow(page: Page) {
  return page.evaluate(() => {
    const doc = document.documentElement;
    const bleeding: { tag: string; right: number }[] = [];
    if (doc.scrollWidth > doc.clientWidth) {
      for (const node of Array.from(document.body.querySelectorAll("*"))) {
        const rect = (node as HTMLElement).getBoundingClientRect();
        if (rect.width > 0 && rect.right > doc.clientWidth + 1) {
          const element = node as HTMLElement;
          bleeding.push({
            tag: `${element.tagName.toLowerCase()}.${String(element.className).split(" ")[0]}`,
            right: Math.round(rect.right),
          });
        }
      }
    }
    return { scrollWidth: doc.scrollWidth, clientWidth: doc.clientWidth, bleeding: bleeding.slice(0, 8) };
  });
}

for (const device of devices) {
  test.describe(device.name, () => {
    // Touch emulation is the whole point. The app's 44px minimums live behind
    // `@media (pointer: coarse)` in 130-touch-targets.css, so a default desktop
    // context reports every one of them as a 40px failure that no iPhone has.
    test.use({
      viewport: { width: device.width, height: device.height },
      hasTouch: true,
      isMobile: !device.ipad,
      deviceScaleFactor: 2,
    });

    test(`lays out without horizontal bleed at ${device.width}x${device.height}`, async ({ page }) => {
      await bootApp(page, device.width, device.height);
      const overflow = await horizontalOverflow(page);
      expect(
        overflow.scrollWidth,
        `document scrolls sideways on ${device.name}: ${JSON.stringify(overflow.bleeding)}`,
      ).toBeLessThanOrEqual(overflow.clientWidth + 1);
    });

    test(`keeps every control finger-sized at ${device.width}x${device.height}`, async ({ page }) => {
      await bootApp(page, device.width, device.height);
      const offenders = await undersizedTapTargets(page);
      expect(offenders, `controls under ${MIN_TAP_TARGET}px on ${device.name}`).toEqual([]);
    });

    test(`keeps the composer reachable at ${device.width}x${device.height}`, async ({ page }) => {
      await bootApp(page, device.width, device.height);
      const composer = page.locator("textarea, [contenteditable=true]").first();
      await expect(composer).toBeVisible();
      const box = await composer.boundingBox();
      expect(box, "the composer has no layout box").not.toBeNull();
      // Inside the window, not pushed under the fold or off the side.
      expect(box!.y).toBeGreaterThanOrEqual(0);
      expect(box!.y + box!.height).toBeLessThanOrEqual(device.height + 1);
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.width).toBeGreaterThan(80);
    });

    test(`survives dark mode at ${device.width}x${device.height}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: "dark" });
      await bootApp(page, device.width, device.height);
      const overflow = await horizontalOverflow(page);
      expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 1);
      // A surface that collapses to the page background in dark mode makes the
      // app look unstyled; this catches the whole shell going one flat colour.
      const distinct = await page.evaluate(() => {
        const colours = new Set<string>();
        for (const node of Array.from(document.querySelectorAll("body, main, header, nav, .chat-stream, button"))) {
          colours.add(getComputedStyle(node as HTMLElement).backgroundColor);
        }
        return colours.size;
      });
      expect(distinct, "dark mode collapsed the shell to a single flat surface").toBeGreaterThan(1);
    });

    test(`has no serious accessibility violations at ${device.width}x${device.height}`, async ({ page }) => {
      await bootApp(page, device.width, device.height);
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
      expect(
        serious.map((v) => `${v.id}: ${v.nodes.length} node(s)`),
        `axe violations on ${device.name}`,
      ).toEqual([]);
    });
  });
}
