import { expect, test, type Page } from "@playwright/test";
import { installMockApi } from "./mockApi";
import { AxeBuilder } from "@axe-core/playwright";

async function boot(page: Page) {
  await installMockApi(page, "auth", 0, "product", { aiConsentAccepted: true, magicLinkEnabled: true });
}

test("an emailed sign-in link completes once under Strict Mode and leaves no token in the URL", async ({ page }) => {
  let consumed = 0;
  await boot(page);
  await page.route("**/v1/auth/magic-link/consume", async route => {
    consumed += 1;
    await route.fulfill({ json: { access_token: "test-access", refresh_token: "test-refresh", token_type: "bearer", expires_in: 3600 } });
  });
  await page.goto("/app/?magic=fictional-single-use-token");
  await expect(page.getByRole("heading", { name: "Chat", level: 1, exact: true })).toBeVisible();
  expect(consumed).toBe(1);
  expect(new URL(page.url()).searchParams.has("magic")).toBe(false);
});

test("a pending sign-in holds its inputs and blocks a second form submission", async ({ page }) => {
  await boot(page);
  await page.goto("/app/");
  let submitted = 0;
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/v1/auth/login", async route => {
    submitted += 1;
    await held;
    await route.fulfill({ status: 401, json: { error: { message: "Check your sign-in details." } } });
  });
  await page.getByLabel("Email or phone", { exact: true }).fill("fictional@example.com");
  await page.getByLabel("Password", { exact: true }).fill("fictional password phrase");
  await page.locator("form").first().evaluate(form => {
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  try {
    await expect.poll(() => submitted).toBe(1);
    await expect(page.getByLabel("Password", { exact: true })).toBeDisabled();
    await expect(page.getByLabel("Email or phone", { exact: true })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Register", exact: true })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Continue with Google" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Email me a sign-in link" })).toBeDisabled();
  } finally {
    release();
  }
  await expect(page.getByText("Check your sign-in details.", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Password", { exact: true })).toHaveValue("fictional password phrase");
  await expect(page.getByLabel("Password", { exact: true })).toBeEnabled();
});

test("expired links recover to the form, then a failed code can be retried", async ({ page }) => {
  await boot(page);
  await page.route("**/v1/auth/magic-link/consume", route => route.fulfill({ status: 400, json: { error: { message: "That sign-in link has expired." } } }));
  await page.route("**/v1/auth/magic-link/request", route => route.fulfill({ json: { status: "sent" } }));
  await page.goto("/app/?magic=fictional-expired-token");
  await expect(page.getByText("That sign-in link has expired.", { exact: true })).toBeVisible();
  expect(new URL(page.url()).searchParams.has("magic")).toBe(false);
  await page.getByLabel("Email or phone", { exact: true }).fill("fictional@example.com");
  await page.getByRole("button", { name: "Email me a sign-in link" }).click();
  await page.route("**/v1/auth/magic-code/consume", route => route.fulfill({ status: 400, json: { error: { message: "That sign-in code is not valid." } } }), { times: 1 });
  await page.getByLabel("Sign-in code", { exact: true }).fill("111111");
  await page.getByRole("button", { name: "Sign in with code", exact: true }).click();
  await expect(page.getByText("That sign-in code is not valid.", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Sign-in code", { exact: true })).toHaveValue("");
  await page.route("**/v1/auth/magic-code/consume", route => {
    expect(route.request().postDataJSON()).toEqual({ email: "fictional@example.com", code: "123456" });
    return route.fulfill({ json: { access_token: "test-access", refresh_token: "test-refresh", token_type: "bearer", expires_in: 3600 } });
  });
  await page.getByLabel("Sign-in code", { exact: true }).fill("123 456");
  await page.getByRole("button", { name: "Sign in with code", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Chat", level: 1, exact: true })).toBeVisible();
});

test("email-link delivery locks competing password and provider actions", async ({ page }) => {
  await boot(page);
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/v1/auth/magic-link/request", async route => {
    await held;
    await route.fulfill({ status: 429, json: { error: { message: "Wait before requesting another link." } } });
  });
  await page.goto("/app/");
  await page.getByLabel("Email or phone", { exact: true }).fill("fictional@example.com");
  await page.getByLabel("Password", { exact: true }).fill("fictional password phrase");
  await page.getByRole("button", { name: "Email me a sign-in link" }).click();
  try {
    await expect(page.locator(".auth-password-form").getByRole("button", { name: "Login", exact: true })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Continue with Apple" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Register", exact: true })).toBeDisabled();
    await expect(page.getByLabel("Email or phone", { exact: true })).toBeDisabled();
  } finally { release(); }
  await expect(page.getByText("Wait before requesting another link.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Email me a sign-in link" })).toBeEnabled();
});

test("password visibility preserves exact text, continued typing and server-side sign-in validation", async ({ page }) => {
  await boot(page);
  await page.goto("/app/");
  const password = page.getByLabel("Password", { exact: true });
  await password.fill("  café🔒 ");
  await page.getByRole("button", { name: "Show password", exact: true }).click();
  await expect(password).toHaveAttribute("type", "text");
  await expect(password).toHaveValue("  café🔒 ");
  await page.getByRole("button", { name: "Hide password", exact: true }).click();
  await password.press("!");
  await expect(password).toHaveValue("  café🔒 !");
  await expect(password).toHaveAttribute("type", "password");
  await page.getByLabel("Email or phone", { exact: true }).fill("  fictional@example.com  ");
  let sent: unknown;
  await page.route("**/v1/auth/login", route => {
    sent = route.request().postDataJSON();
    return route.fulfill({ status: 401, json: { error: { message: "Check your sign-in details." } } });
  });
  await page.locator(".auth-password-form").getByRole("button", { name: "Login", exact: true }).click();
  await expect(page.getByText("Check your sign-in details.", { exact: true })).toBeVisible();
  expect(sent).toEqual({ identifier: "fictional@example.com", password: "  café🔒 !" });
  await page.getByRole("button", { name: "Register", exact: true }).click();
  await expect(password).toHaveAttribute("minlength", "12");
  await expect(password).toHaveAttribute("autocomplete", "new-password");
});

test("a confirmed signup resumes after failed consent delivery without creating the account twice", async ({ page }) => {
  await boot(page);
  let registrations = 0;
  await page.route("**/v1/auth/register", route => {
    registrations += 1;
    if (registrations > 1) return route.fulfill({ status: 409, json: { error: { message: "Account already exists." } } });
    return route.fallback();
  });
  await page.route("**/v1/legal/acceptances", route => route.fulfill({ status: 503, json: { error: { message: "Could not record consent. Please retry." } } }), { times: 1 });
  await page.goto("/app/?auth=register");
  await page.getByLabel("Email", { exact: true }).fill("fictional@example.com");
  await page.getByLabel("Password", { exact: true }).fill("fictional password phrase");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Create Account", exact: true }).click();
  await expect(page.getByText("Could not record consent. Please retry.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Create Account", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Chat", level: 1, exact: true })).toBeVisible();
  expect(registrations).toBe(1);
});

test("AI consent reports a save failure and recovers without losing the confirmation", async ({ page }) => {
  await installMockApi(page, "auth");
  await page.goto("/app/");
  await page.getByLabel("Email or phone", { exact: true }).fill("fictional@example.com");
  await page.getByLabel("Password", { exact: true }).fill("fictional password phrase");
  await page.locator(".auth-password-form").getByRole("button", { name: "Login", exact: true }).click();
  await page.getByRole("checkbox", { name: /I understand and allow this processing/ }).check();
  await page.route("**/v1/legal/acceptances", route => route.fulfill({ status: 503, json: { error: { message: "Consent could not be saved. Try again." } } }), { times: 1 });
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByText("Consent could not be saved. Try again.", { exact: true })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: /I understand and allow this processing/ })).toBeChecked();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Chat", level: 1, exact: true })).toBeVisible();
});

for (const appearance of ["light", "dark"] as const) {
  for (const width of [320, 390, 834, 1440]) {
    test(`sign-in and signup stay readable at ${width}px in ${appearance}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: width === 320 ? 568 : 960 });
      await page.emulateMedia({ colorScheme: appearance, reducedMotion: "reduce" });
      await boot(page);
      await page.goto("/app/");
      for (const mode of ["login", "register"]) {
        if (mode === "register") await page.getByRole("button", { name: "Register", exact: true }).click();
        const password = page.getByLabel("Password", { exact: true });
        await password.fill("fictional password phrase");
        const toggle = page.getByRole("button", { name: "Show password", exact: true });
        const box = await toggle.boundingBox();
        expect(box?.width).toBeGreaterThanOrEqual(44);
        expect(box?.height).toBeGreaterThanOrEqual(44);
        await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
        const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
        expect(result.violations, JSON.stringify(result.violations)).toEqual([]);
        await testInfo.attach(`${mode}-${appearance}-${width}`, { body: await page.screenshot({ fullPage: true }), contentType: "image/png" });
      }
    });
  }
}
