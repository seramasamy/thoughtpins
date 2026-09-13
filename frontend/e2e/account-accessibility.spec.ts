import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { installMockApi } from "./mockApi";

async function signIn(page: Page) {
  await page.getByLabel("Email or phone").fill("fictional-reader@example.com");
  await page.getByLabel("Password", { exact: true }).fill("fictional-passphrase-2048");
  await page.locator(".auth-password-form").getByRole("button", { name: "Login", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Chat", exact: true })).toBeVisible();
}

async function openAccount(page: Page) {
  const profile = page.locator(".profile-button");
  if (await profile.isVisible()) await profile.click();
  else await page.getByRole("button", { name: "Open settings menu" }).click();
  await page.getByRole("dialog", { name: "Thought Pins menu" }).getByRole("button", { name: "Settings & account" }).click();
}

for (const colorScheme of ["dark", "light"] as const) {
  for (const width of [390, 820, 1440]) {
    test(`account notices, export and deletion are accessible: ${colorScheme}, ${width}px`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 960 });
      await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
      await installMockApi(page, "auth", 0, "product", { aiConsentAccepted: true });
      await page.goto("/app/");
      await signIn(page);
      await openAccount(page);
      await expect(page.getByLabel("Response voice")).toBeEnabled();
      await page.getByLabel("Response voice").selectOption("clear");
      await expect(page.getByText("Preferences saved", { exact: true })).toBeVisible();
      await page.getByRole("button", { name: "Account JSON", exact: true }).click();
      const exported = page.getByLabel("Exported account data");
      await expect(exported).toBeVisible();
      await exported.focus();
      await expect(exported).toBeFocused();
      await page.getByLabel("Type DELETE to confirm account deletion").fill("DELETE");
      await expect(page.getByRole("button", { name: "Delete", exact: true })).toBeEnabled();
      await expect(page.getByText("Export loaded", { exact: true })).toBeVisible();
      // Inspect settled styles: the old contrast issue appeared after animation.
      await page.evaluate(async () => {
        await Promise.all(document.getAnimations().filter(a => a.effect?.getTiming().iterations !== Infinity).map(a => a.finished.catch(() => undefined)));
      });
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
      expect(results.violations.filter(v => v.impact === "serious" || v.impact === "critical")).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath(`account-${colorScheme}-${width}.png`), fullPage: true });
    });
  }
}

test("preferences cannot be edited before their saved values load", async ({ page }) => {
  const api = await installMockApi(page, "auth", 0, "product", { aiConsentAccepted: true });
  await page.goto("/app/");
  await signIn(page);
  let release!: () => void;
  const ready = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/v1/preferences", async route => {
    if (route.request().method() === "GET") await ready;
    await route.fallback();
  });
  await openAccount(page);
  await expect(page.getByText("Loading preferences…", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Preferred name")).toBeDisabled();
  await expect(page.getByLabel("Response voice")).toBeDisabled();
  expect(api?.getPreferencesPatchCount()).toBe(0);
  release();
  await expect(page.getByLabel("Preferred name")).toBeEnabled();
  await expect(page.getByLabel("Preferred name")).toHaveValue("Review");
});
