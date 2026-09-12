import { expect, test, type Page } from "@playwright/test";

declare global {
  interface Window {
    morphReview: { points: number[][]; target: number[][]; frames: number };
  }
}

async function observeMark(page: Page) {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.addInitScript(() => {
    window.morphReview = { points: [], target: [], frames: 0 };
    const prototype = CanvasRenderingContext2D.prototype;
    const clear = prototype.clearRect, arc = prototype.arc;
    prototype.clearRect = function (...args) {
      if (this.canvas.matches("[data-constellation]")) {
        window.morphReview.points = [];
        window.morphReview.frames++;
      }
      return clear.apply(this, args);
    };
    prototype.arc = function (...args) {
      if (this.canvas.matches("[data-constellation]")) window.morphReview.points.push([args[0], args[1]]);
      return arc.apply(this, args);
    };
  });
}

async function loadMark(page: Page) {
  const response = await page.request.get("/assets/thought-pins-mark.svg");
  expect(response.ok()).toBe(true);
  await page.evaluate(source => {
    // Read the actual brand asset and its SVG transforms, independently of the
    // animation's embedded geometry. A future logo change must update both.
    const svg = document.importNode(new DOMParser().parseFromString(source, "image/svg+xml").documentElement, true);
    svg.setAttribute("style", "position:absolute;width:128px;height:128px;visibility:hidden;pointer-events:none");
    document.body.append(svg);
    try {
      window.morphReview.target = [...svg.querySelectorAll("path")].flatMap(path => {
        const count = path === svg.querySelector("path") ? 72 : 9;
        const length = path.getTotalLength();
        return Array.from({ length: count }, (_, i) => {
          const sample = path.getPointAtLength(length * i / count).matrixTransform(path.getCTM()!);
          return [sample.x, sample.y];
        });
      });
    } finally { svg.remove(); }
  }, await response.text());
}

async function scrollPhase(page: Page, fraction: number) {
  await page.evaluate(value => {
    const wrap = document.querySelector<HTMLElement>("[data-hero-wrap]")!;
    const canvas = document.querySelector("[data-constellation]")!;
    const top = scrollY + wrap.getBoundingClientRect().top;
    const runway = wrap.offsetHeight - canvas.getBoundingClientRect().height;
    window.scrollTo({ top: top + runway * value, behavior: "instant" });
  }, fraction);
}

async function geometry(page: Page) {
  return page.evaluate(() => {
    const { points, target } = window.morphReview;
    const { width, height, top } = document.querySelector("[data-constellation]")!.getBoundingClientRect();
    const scale = Math.min(width, height) * (width <= 760 ? 0.66 : 0.46) / 128;
    const errors = points.map((point, i) => Math.hypot(
      point[0] - (width / 2 + (target[i][0] - 64) * scale),
      point[1] - (height / 2 + (target[i][1] - 64) * scale),
    ));
    return { count: points.length, max: Math.max(...errors), rms: Math.sqrt(errors.reduce((sum, e) => sum + e * e, 0) / errors.length), top };
  });
}

async function expectFormed(page: Page) {
  await expect.poll(async () => (await geometry(page)).max).toBeLessThan(0.002);
  expect((await geometry(page)).count).toBe(135);
  expect(Math.abs((await geometry(page)).top)).toBeLessThanOrEqual(1);
  await expect(page.locator(".lab-hero-copy")).toHaveCSS("opacity", "0");
  await expect(page.locator(".lab-hero-copy")).toHaveAttribute("inert", "");
}

for (const viewport of [{ width: 390, height: 844 }, { width: 834, height: 1112 }, { width: 1440, height: 900 }]) {
  test(`scroll gathers every node onto the actual logo and reverses at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await observeMark(page);
    await page.goto("/");
    await expect(page.locator("[data-hero-wrap]")).toHaveAttribute("data-constellation-morph", "ready");
    await expect.poll(() => page.evaluate(() => window.morphReview.points.length)).toBe(135);
    await loadMark(page);
    const initial = await geometry(page);
    expect(initial.rms).toBeGreaterThan(100);
    await scrollPhase(page, 0.2);
    await expect.poll(async () => (await geometry(page)).rms).toBeLessThan(initial.rms * 0.7);
    expect(Math.abs((await geometry(page)).top)).toBeLessThanOrEqual(1);
    await scrollPhase(page, 1);
    await expectFormed(page);
    await scrollPhase(page, 0);
    await expect(page.locator(".lab-hero-copy")).toHaveCSS("opacity", "1");
    await expect(page.locator(".lab-hero-copy")).not.toHaveAttribute("inert", "");
    await expect.poll(async () => (await geometry(page)).rms).toBeGreaterThan(initial.rms * 0.8);
    // Resizing preserves the identity of each node and recalculates its target.
    await page.setViewportSize({ width: viewport.width + 40, height: viewport.height + 40 });
    await scrollPhase(page, 1);
    await expectFormed(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  });
}

test("pausing stops automatic motion while deliberate scrolling can still form the logo", async ({ page }) => {
  await observeMark(page);
  await page.goto("/");
  await loadMark(page);
  await page.getByRole("button", { name: "Pause motion" }).click();
  await page.waitForTimeout(150);
  const before = await page.evaluate(() => window.morphReview.frames);
  await page.waitForTimeout(250);
  expect(await page.evaluate(() => window.morphReview.frames)).toBe(before);
  await scrollPhase(page, 1);
  await expectFormed(page);
  const after = await page.evaluate(() => window.morphReview.frames);
  await page.waitForTimeout(250);
  expect(await page.evaluate(() => window.morphReview.frames)).toBe(after);
  await scrollPhase(page, 0);
  await expect(page.locator(".lab-hero-copy")).toHaveCSS("opacity", "1");
});

test("Reduce Motion removes the pinned sequence, including a live change midway through", async ({ page }) => {
  await observeMark(page);
  await page.goto("/");
  await loadMark(page);
  await scrollPhase(page, 1);
  await expectFormed(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.locator("[data-hero-wrap]")).toHaveAttribute("data-constellation-morph", "static");
  await expect(page.locator(".lab-hero-sticky")).toHaveCSS("position", "relative");
  await expect(page.locator(".lab-hero-copy")).toHaveCSS("opacity", "1");
  await expect(page.locator(".lab-hero-copy")).not.toHaveAttribute("inert", "");
  await page.reload();
  await expect(page.locator("[data-hero-wrap]")).toHaveAttribute("data-constellation-morph", "static");
  await expect(page.locator("[data-primary-cta]")).toBeVisible();
});

test("short landscape windows and oversized text keep the introduction in normal flow", async ({ page }) => {
  await page.setViewportSize({ width: 844, height: 390 });
  await observeMark(page);
  await page.goto("/");
  await expect(page.locator("[data-hero-wrap]")).toHaveAttribute("data-constellation-morph", "static");
  await expect(page.locator(".lab-hero-sticky")).toHaveCSS("position", "relative");
  await page.locator("[data-primary-cta]").scrollIntoViewIfNeeded();
  await expect(page.locator("[data-primary-cta]")).toBeInViewport();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addStyleTag({ content: ".lab-h1 { font-size: 120px; overflow-wrap: anywhere; }" });
  await expect(page.locator("[data-hero-wrap]")).toHaveAttribute("data-constellation-morph", "static");
  await expect(page.locator(".lab-hero-copy")).toHaveCSS("opacity", "1");
  await page.locator("[data-primary-cta]").scrollIntoViewIfNeeded();
  await expect(page.locator("[data-primary-cta]")).toBeInViewport();
});

test("keyboard focus keeps a fading call to action visible and usable", async ({ page }) => {
  await observeMark(page);
  await page.goto("/");
  const cta = page.locator("[data-primary-cta]");
  await page.keyboard.press("Tab");
  await cta.focus();
  expect(await cta.evaluate(el => el.matches(":focus-visible"))).toBe(true);
  await scrollPhase(page, 0.7);
  await expect(cta).toBeFocused();
  await expect(page.locator(".lab-hero-copy")).toHaveCSS("opacity", "1");
  await expect(page.locator(".lab-hero-copy")).not.toHaveAttribute("inert", "");
  await expect(cta).toBeInViewport();
  await page.locator(".lab-brand").focus();
  await expect(page.locator(".lab-hero-copy")).toHaveAttribute("inert", "");
});

test("unavailable SVG geometry leaves visible content and the floating field", async ({ page }) => {
  await observeMark(page);
  await page.addInitScript(() => {
    SVGGeometryElement.prototype.getTotalLength = () => { throw new Error("Unavailable geometry"); };
  });
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/");
  await expect(page.locator("[data-hero-wrap]")).toHaveAttribute("data-constellation-morph", "static");
  await expect.poll(() => page.evaluate(() => window.morphReview.points.length)).toBe(135);
  await expect(page.locator("[data-primary-cta]")).toBeVisible();
  expect(errors).toEqual([]);
});
