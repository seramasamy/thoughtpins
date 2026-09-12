import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const sizes = [
  { width: 320, height: 568 }, { width: 390, height: 844 },
  { width: 430, height: 932 }, { width: 768, height: 1024 },
  { width: 834, height: 1194 }, { width: 1024, height: 768 },
  { width: 1440, height: 1000 }, { width: 1920, height: 1080 },
];

for (const route of ["/", "/classic/"]) {
  for (const viewport of sizes) {
    test(`${route} product preview at ${viewport.width}px`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.emulateMedia({ reducedMotion: "reduce" });
      const errors: string[] = [];
      page.on("pageerror", error => errors.push(error.message));
      await page.goto(route + "#product");
      if (route === "/classic/") {
        await page.evaluate(() => document.fonts.ready);
        const header = await page.locator(".site-header").evaluate(el => {
          const brand = el.querySelector(".site-brand")!.getBoundingClientRect();
          const actions = el.querySelector(".header-actions")!.getBoundingClientRect();
          const back = el.querySelector(".header-back")!.getBoundingClientRect();
          return { brandRight: brand.right, actionsLeft: actions.left, switchHeight: back.height };
        });
        expect(header.brandRight + 8).toBeLessThanOrEqual(header.actionsLeft);
        expect(header.switchHeight).toBeGreaterThanOrEqual(44);
      }
      const root = page.locator("[data-product-demo]");
      const mode = viewport.width <= 680 ? "mobile" : "desktop";
      const active = page.locator(`[data-preview-tab="${mode}"]`);
      await expect(active).toHaveAttribute("aria-selected", "true");
      const image = page.locator(`[data-preview-panel="${mode}"] img`);
      await expect(image).toBeVisible();
      await expect.poll(() => image.evaluate(el => el.getBoundingClientRect().height)).toBeGreaterThan(100);
      await expect.poll(() => image.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0)).toBe(true);

      await active.focus();
      await active.press(mode === "mobile" ? "Home" : "End");
      const other = mode === "mobile" ? "desktop" : "mobile";
      await expect(page.locator(`[data-preview-tab="${other}"]`)).toBeFocused();
      await expect(page.locator(`[data-preview-panel="${mode}"]`)).toBeHidden();
      await expect(page.locator(`[data-preview-panel="${other}"]`)).toBeVisible();
      await page.setViewportSize({ width: viewport.width <= 680 ? 1024 : 390, height: 900 });
      await expect(root).toHaveAttribute("data-preview-mode", other);
      await page.setViewportSize(viewport);

      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
      const accessibility = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
      expect(accessibility.violations.map(v => ({ id: v.id, nodes: v.nodes.map(n => n.target) }))).toEqual([]);
      expect(errors).toEqual([]);
    });
  }

  test(`${route} remains useful without JavaScript`, async ({ browser }) => {
    const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    await page.goto("http://127.0.0.1:8878" + route + "#product");
    if (route === "/") {
      await expect(page.locator(".lab-hero-cta > span")).toHaveCSS("opacity", "1");
      await expect(page.locator(".lab-hero-cta > span")).toHaveCSS("transform", "none");
      await expect(page.locator("[data-marquee-track]")).toHaveCSS("animation-name", "none");
    }
    await expect(page.locator(".product-showcase .preview-tabs")).toBeHidden();
    await expect(page.locator('.product-showcase [data-preview-panel="desktop"] img')).toBeVisible();
    await expect(page.getByRole("heading", { name: "Capture it naturally" })).toBeVisible();
    await expect(page.locator(".showcase-open")).toHaveAttribute("href", "/app/?auth=register");
    await context.close();
  });
}

test("Classic appearance selection survives reload", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/classic/");
  const toggle = page.locator("[data-theme-toggle]");
  await toggle.click();
  const chosen = await page.locator("html").getAttribute("data-theme");
  expect(["light", "dark"]).toContain(chosen);
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", chosen!);
  await page.evaluate(() => document.fonts.ready);
  const accessibility = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(accessibility.violations.map(v => ({ id: v.id, nodes: v.nodes.map(n => ({ target: n.target, reason: n.failureSummary })) }))).toEqual([]);
});

test("phone preview reserves its frame while the image is still loading", async ({ page }) => {
  let releaseImage!: () => void;
  const pending = new Promise<void>(resolve => { releaseImage = resolve; });
  await page.route("**/product-chat-mobile.png*", async route => {
    await pending;
    await route.continue();
  });
  try {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/#product", { waitUntil: "domcontentloaded" });
    const image = page.locator('[data-preview-panel="mobile"] img');
    await expect(image).toBeVisible();
    const height = await image.evaluate(el => el.getBoundingClientRect().height);
    expect(height).toBeGreaterThan(400);
    expect(await image.evaluate((el: HTMLImageElement) => el.complete)).toBe(false);
    releaseImage();
    await expect.poll(() => image.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0)).toBe(true);
    expect(await image.evaluate(el => el.getBoundingClientRect().height)).toBeCloseTo(height, 0);
  } finally {
    releaseImage();
  }
});
