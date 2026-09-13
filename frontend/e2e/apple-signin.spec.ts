import { expect, test } from "@playwright/test";
import { installMockApi } from "./mockApi";

test("native-only Apple configuration does not offer a broken web login", async ({ page }) => {
  await installMockApi(page, "auth", 0, "product", { appleClientId: "" });
  await page.goto("/app/");
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Continue with Apple" })).toHaveCount(0);
  await expect(page.locator("#tp-appleid")).toHaveCount(0);
});

for (const outcome of ["success", "wrong-state", "missing-code"] as const) {
  test(`Apple web authorization: ${outcome}`, async ({ page }) => {
    await installMockApi(page, "auth", 0, "product", { aiConsentAccepted: true, appleClientId: "com.thoughtpins.web.fixture" });
    await page.route("https://appleid.cdn-apple.com/**", route => route.fulfill({
      contentType: "application/javascript",
      body: `window.AppleID = {auth: {
        init(options) { window.appleOptions = options; },
        async signIn() { return {authorization: {id_token: 'fictional-provider-token',
          code: ${outcome === "missing-code" ? "undefined" : "'fictional-one-time-code'"},
          state: ${outcome === "wrong-state" ? "'mismatched-state'" : "window.appleOptions.state"}},
          user: {name: {firstName: 'Fictional', lastName: 'Reader'}}}; }
      }};`,
    }));
    const submissions: Record<string, unknown>[] = [];
    await page.route("**/v1/auth/oauth", route => {
      submissions.push(route.request().postDataJSON());
      return route.fulfill({ json: { access_token: "test-access", refresh_token: "test-refresh", expires_in: 3600, token_type: "bearer" } });
    });
    await page.goto("/app/");
    await page.getByRole("button", { name: "Continue with Apple" }).click();
    if (outcome === "success") {
      await expect(page.getByRole("heading", { name: "Chat", exact: true, level: 1 })).toBeVisible();
      expect(submissions).toHaveLength(1);
      expect(submissions[0]).toMatchObject({ provider: "apple", authorization_code: "fictional-one-time-code", display_name: "Fictional Reader" });
      expect(submissions[0].nonce).toMatch(/^[A-Za-z0-9_-]{43}$/);
      expect(submissions[0].redirect_uri).toBe(new URL("/app/", page.url()).href);
    } else {
      await expect(page.getByText(outcome === "wrong-state" ? "Apple sign-in state validation failed." : "Apple sign-in did not return a complete credential.", { exact: true })).toBeVisible();
      expect(submissions).toHaveLength(0);
      await expect(page.getByRole("button", { name: "Continue with Apple" })).toBeEnabled();
    }
  });
}

test("a failed Apple SDK download can be retried without reloading the app", async ({ page }) => {
  await installMockApi(page, "auth", 0, "product", { appleClientId: "com.thoughtpins.web.fixture" });
  let downloads = 0;
  await page.route("https://appleid.cdn-apple.com/**", route => {
    downloads += 1;
    return downloads === 1 ? route.abort("failed") : route.fulfill({ contentType: "application/javascript", body: `window.AppleID = {auth: {init() {}, async signIn() {throw new Error('Apple fixture cancellation');}}};` });
  });
  await page.goto("/app/");
  await expect.poll(() => downloads).toBe(1);
  await expect(page.locator("#tp-appleid")).toHaveCount(0);
  await page.getByRole("button", { name: "Continue with Apple" }).click();
  await expect(page.getByText("Apple fixture cancellation", { exact: true })).toBeVisible();
  expect(downloads).toBe(2);
});
