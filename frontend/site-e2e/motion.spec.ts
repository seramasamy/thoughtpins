import { expect, test, type Page } from "@playwright/test";

async function instrumentCanvas(page: Page) {
  await page.addInitScript(() => {
    const draw = CanvasRenderingContext2D.prototype.clearRect;
    CanvasRenderingContext2D.prototype.clearRect = function (...args) {
      if (this.canvas.matches("[data-constellation], [data-hero-particles]")) {
        this.canvas.dataset.draws = String(Number(this.canvas.dataset.draws || 0) + 1);
      }
      return draw.apply(this, args);
    };
  });
}
const draws = (page: Page) => page.locator("[data-constellation], [data-hero-particles]").getAttribute("data-draws");
async function expectStill(page: Page) {
  // Allow the preference/visibility observer to deliver its final static frame.
  await page.waitForTimeout(150);
  const before = await draws(page);
  expect(Number(before)).toBeGreaterThan(0);
  await page.waitForTimeout(250);
  expect(await draws(page)).toBe(before);
}

test("motion can pause, persist, react to system preference and resume", async ({ page }) => {
  await instrumentCanvas(page);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/");
  await expect.poll(async () => Number(await draws(page))).toBeGreaterThan(2);
  await page.getByRole("button", { name: "Pause motion" }).click();
  await expectStill(page);
  await expect(page.locator("[data-marquee-track]")).toHaveCSS("animation-play-state", "paused");
  await page.reload();
  await expect(page.getByRole("button", { name: "Resume motion" })).toBeVisible();
  await expectStill(page);
  await page.getByRole("button", { name: "Resume motion" }).click();
  const before = Number(await draws(page));
  await expect.poll(async () => Number(await draws(page))).toBeGreaterThan(before + 2);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.locator("[data-motion-toggle]")).toBeHidden();
  await expectStill(page);
  await expect(page.locator("[data-marquee-track]")).toHaveCSS("animation-name", "none");
  await page.emulateMedia({ reducedMotion: "no-preference" });
  const reducedDraws = Number(await draws(page));
  await expect.poll(async () => Number(await draws(page))).toBeGreaterThan(reducedDraws + 2);
  // A cached document must pick up a choice made on the other homepage.
  await page.evaluate(() => {
    sessionStorage.setItem("thoughtpins.motionPaused", "true");
    window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true }));
  });
  await expect(page.getByRole("button", { name: "Resume motion" })).toBeVisible();
  await expectStill(page);
});

test("network stops offscreen and across page lifecycle events", async ({ page }) => {
  await instrumentCanvas(page);
  await page.goto("/");
  await expect.poll(async () => Number(await draws(page))).toBeGreaterThan(2);
  await page.locator("footer").scrollIntoViewIfNeeded();
  await expectStill(page);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  const offscreenDraws = Number(await draws(page));
  await expect.poll(async () => Number(await draws(page))).toBeGreaterThan(offscreenDraws + 2);
  // Exercise the bfcache lifecycle handlers, including a persisted restore.
  await page.evaluate(() => window.dispatchEvent(new PageTransitionEvent("pagehide", { persisted: true })));
  await expectStill(page);
  await page.evaluate(() => window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true })));
  const hiddenDraws = Number(await draws(page));
  await expect.poll(async () => Number(await draws(page))).toBeGreaterThan(hiddenDraws + 2);
});

test("classic shares motion control and does not restart an offscreen canvas", async ({ page }) => {
  await instrumentCanvas(page);
  await page.goto("/classic/");
  await expect.poll(async () => Number(await draws(page))).toBeGreaterThan(2);
  await page.getByRole("button", { name: "Pause motion" }).click();
  await expectStill(page);
  await expect(page.locator(".hero-mark")).toHaveCSS("animation-name", "none");
  await page.getByRole("button", { name: "Resume motion" }).click();
  await page.locator("footer").scrollIntoViewIfNeeded();
  await expectStill(page);
  await page.setViewportSize({ width: 1024, height: 768 });
  await expectStill(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  await expectStill(page);
});

for (const route of ["/", "/classic/"]) {
  test(`${route} button motion follows a live preference change`, async ({ page }) => {
    await page.goto(route);
    const cta = page.locator("[data-primary-cta]");
    await page.getByRole("button", { name: "Pause motion" }).click();
    await cta.hover({ position: { x: 10, y: 10 } });
    expect(await cta.evaluate(el => el.style.transform)).toBe("");
    await expect(cta).toHaveCSS("transform", "none");
    await page.getByRole("button", { name: "Resume motion" }).click();
    await page.emulateMedia({ reducedMotion: "reduce" });
    await cta.hover({ position: { x: 15, y: 15 } });
    expect(await cta.evaluate(el => el.style.transform)).toBe("");
    await expect(cta).toHaveCSS("transform", "none");
  });

  test(`${route} stays static if the motion control script cannot load`, async ({ page }) => {
    await instrumentCanvas(page);
    await page.route("**/motion-preference.js*", route => route.abort());
    await page.goto(route);
    await expectStill(page);
    await expect(page.locator("[data-primary-cta]")).toBeVisible();
    await expect(page.locator("[data-motion-toggle]")).toBeHidden();
  });
}

for (const width of [320, 390, 834, 1440, 1920]) {
  test(`examples are reachable by keyboard and buttons at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/#week");
    const track = page.locator("[data-week-track]");
    await track.focus();
    await track.press("End");
    await expect(page.getByRole("button", { name: "Next example" })).toBeDisabled();
    await expect(page.locator("[data-example-position]")).toHaveText("5 / 5");
    const end = await track.evaluate(el => el.scrollLeft);
    await page.getByRole("button", { name: "Previous example" }).click();
    await expect.poll(() => track.evaluate(el => el.scrollLeft)).toBeLessThan(end - 2);
    await track.focus();
    await track.press("Home");
    await expect(page.getByRole("button", { name: "Previous example" })).toBeDisabled();
    await page.getByRole("button", { name: "Next example" }).click();
    await expect.poll(() => track.evaluate(el => el.scrollLeft)).toBeGreaterThan(0);
    await page.setViewportSize({ width: 430, height: 932 });
    await track.focus();
    await track.press("End");
    await expect(page.locator("[data-example-position]")).toHaveText("5 / 5");
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  });
}

test("classic stays accessible with its return link but is absent from modern navigation", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator('a[href="/classic/"]')).toHaveCount(0);
  await page.goto("/classic/");
  await expect(page.getByRole("link", { name: "Modern Site" })).toHaveAttribute("href", "/");
  await page.getByRole("link", { name: "Modern Site" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/Your memory,\s*connected\./);
});

for (const route of ["/", "/classic/"]) test(`${route} blocked storage and unavailable canvas do not break the page`, async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "sessionStorage", { get() { throw new DOMException("Blocked", "SecurityError"); } });
    HTMLCanvasElement.prototype.getContext = () => null;
  });
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto(route);
  await expect(page.locator("[data-primary-cta]")).toBeVisible();
  await page.getByRole("button", { name: "Pause motion" }).click();
  await expect(page.getByRole("button", { name: "Resume motion" })).toBeVisible();
  await expect(page.locator("[data-product-demo]")).toBeVisible();
  expect(errors).toEqual([]);
});
