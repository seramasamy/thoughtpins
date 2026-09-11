import { expect, test } from "@playwright/test";
import { AxeBuilder } from "@axe-core/playwright";
import { installMockApi } from "./mockApi";

for (const appearance of ["light", "dark"] as const) {
  for (const width of [320, 390, 834, 1440]) {
    test(`modern surfaces remain usable at ${width}px in ${appearance}`, async ({ page }) => {
      await page.setViewportSize({ width, height: width === 320 ? 568 : 960 });
      await page.emulateMedia({ colorScheme: appearance, reducedMotion: "reduce" });
      const mock = await installMockApi(page, "local", 0, "product");
      await page.goto("/app/");
      const starter = page.getByRole("button", { name: "What has been on my mind?", exact: true });
      await expect(starter).toBeVisible();
      await starter.focus();
      await page.keyboard.press("Enter");
      await expect.poll(() => mock.getChatPostCount()).toBe(1);
      await expect(page.getByText("I remember the Atlas Cafe note and the copper lantern detail.")).toBeVisible();
      const nav = page.getByRole("navigation", { name: width <= 700 ? "Mobile primary navigation" : "Primary", exact: true });
      for (const name of ["Recap", "People", "Places", "Pins"] as const) {
        await nav.getByRole("button", { name, exact: true }).click();
        await expect(page.getByRole("heading", { name, level: 1, exact: true })).toBeVisible();
        await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
        const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
        expect(result.violations.filter(v => v.impact === "serious" || v.impact === "critical"), JSON.stringify(result.violations)).toEqual([]);
      }
    });
  }
}

test("appearance choice is available directly and persists", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await installMockApi(page, "local");
  await page.goto("/app/");
  await page.getByRole("button", { name: "Switch to dark appearance", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.getByRole("button", { name: "Switch to light appearance", exact: true })).toBeVisible();
});
