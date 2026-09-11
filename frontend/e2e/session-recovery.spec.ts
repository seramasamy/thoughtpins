import { expect, test } from "@playwright/test";
import { installMockApi } from "./mockApi";

for (const delayOldResponse of [false, true]) {
  test(`expired sessions share one renewal${delayOldResponse ? " even when an old 401 arrives later" : " across parallel requests"}`, async ({ page }) => {
    await installMockApi(page, "auth", 0, "product", { aiConsentAccepted: true });
    await page.addInitScript(() => localStorage.setItem("thoughtpins.session.v1", JSON.stringify({
      accessToken: "expired-fixture-access", refreshToken: "fixture-refresh-once",
    })));
    let renewals = 0;
    let release!: () => void;
    const renewed = new Promise<void>(resolve => { release = resolve; });
    await page.route("**/v1/**", async route => {
      const request = route.request();
      if (new URL(request.url()).pathname === "/v1/auth/refresh") {
        renewals += 1;
        if (renewals > 1) return route.fulfill({ status: 401, json: { error: { message: "Refresh token already consumed" } } });
        await new Promise(resolve => setTimeout(resolve, 150));
        await route.fulfill({ json: { access_token: "renewed-fixture-access", refresh_token: "renewed-fixture-refresh", token_type: "bearer", expires_in: 3600 } });
        release();
        return;
      }
      if (request.headers().authorization === "Bearer expired-fixture-access") {
        if (delayOldResponse && new URL(request.url()).pathname === "/v1/preferences") {
          await renewed;
          await new Promise(resolve => setTimeout(resolve, 100));
        }
        return route.fulfill({ status: 401, json: { error: { message: "Access token expired" } } });
      }
      return route.fallback();
    });
    await page.goto("/app/");
    await expect(page.getByRole("heading", { level: 1, name: "Chat", exact: true })).toBeVisible();
    await expect.poll(() => renewals).toBe(1);
    expect(await page.evaluate(() => JSON.parse(localStorage.getItem("thoughtpins.session.v1") || "null")?.accessToken)).toBe("renewed-fixture-access");
    await expect(page.getByRole("heading", { name: "Welcome back", exact: true })).toHaveCount(0);
  });
}

test("a rejected renewal returns to a usable sign-in form", async ({ page }) => {
  await installMockApi(page, "auth", 0, "product", { aiConsentAccepted: true });
  await page.addInitScript(() => localStorage.setItem("thoughtpins.session.v1", JSON.stringify({
    accessToken: "expired-fixture-access", refreshToken: "revoked-fixture-refresh",
  })));
  await page.route("**/v1/**", route => {
    if (new URL(route.request().url()).pathname === "/v1/auth/refresh" || route.request().headers().authorization === "Bearer expired-fixture-access") {
      return route.fulfill({ status: 401, json: { error: { message: "Session expired. Please sign in again." } } });
    }
    return route.fallback();
  });
  await page.goto("/app/");
  await expect(page.getByRole("heading", { level: 1, name: "Welcome back", exact: true })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("thoughtpins.session.v1"))).toBeNull();
  await page.getByLabel("Email or phone").fill("review@example.com");
  await page.getByLabel("Password", { exact: true }).fill("fictional password");
  await page.locator("form").getByRole("button", { name: "Login", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Chat", exact: true })).toBeVisible();
});
