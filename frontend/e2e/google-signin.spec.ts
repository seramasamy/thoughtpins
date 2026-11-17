import { expect, test, type Page } from "@playwright/test";
import { installMockApi } from "./mockApi";

// Google sign-in leaves for Google's own page and comes back with an ID token in
// the URL fragment. Google is stood in for here: the outbound request is caught
// and answered, and the return is the redirect Google would make.

const CLIENT_ID = "fixture-web-client.apps.googleusercontent.com";

async function leaveForGoogle(page: Page): Promise<{ outbound: URL; appHome: string }> {
  let outbound: URL | null = null;
  await page.route("https://accounts.google.com/**", route => {
    outbound = new URL(route.request().url());
    return route.fulfill({ contentType: "text/html", body: "<title>Google</title><p>Fictional Google sign-in</p>" });
  });
  await page.goto("/app/");
  // Taken before the click: afterwards the tab is on Google's page.
  const appHome = new URL("/app/", page.url()).href;
  await page.getByRole("button", { name: "Continue with Google" }).click();
  await expect.poll(() => outbound).not.toBeNull();
  return { outbound: outbound as unknown as URL, appHome };
}

test("the button leaves for Google's sign-in page with this tab's state and nonce", async ({ page }) => {
  await installMockApi(page, "auth", 0, "product", { googleClientId: CLIENT_ID });
  const { outbound, appHome } = await leaveForGoogle(page);

  expect(`${outbound.origin}${outbound.pathname}`).toBe("https://accounts.google.com/o/oauth2/v2/auth");
  expect(outbound.searchParams.get("client_id")).toBe(CLIENT_ID);
  expect(outbound.searchParams.get("response_type")).toBe("id_token");
  expect(outbound.searchParams.get("redirect_uri")).toBe(appHome);
  expect(outbound.searchParams.get("state")).toMatch(/^[A-Za-z0-9_-]{43}$/);
  expect(outbound.searchParams.get("nonce")).toMatch(/^[A-Za-z0-9_-]{43}$/);
  // One Tap, which most browsers skipped, is gone.
  await expect(page.locator("#tp-gsi")).toHaveCount(0);
});

for (const outcome of ["success", "wrong-state", "cancelled", "server-refuses"] as const) {
  test(`returning from Google: ${outcome}`, async ({ page }) => {
    await installMockApi(page, "auth", 0, "product", { aiConsentAccepted: true, googleClientId: CLIENT_ID });
    const { outbound } = await leaveForGoogle(page);
    const state = outbound.searchParams.get("state") as string;
    const nonce = outbound.searchParams.get("nonce") as string;

    const submissions: Record<string, unknown>[] = [];
    await page.route("**/v1/auth/oauth", route => {
      submissions.push(route.request().postDataJSON());
      return outcome === "server-refuses"
        ? route.fulfill({ status: 401, json: { error: { code: "unauthorized", message: "Google sign-in nonce validation failed", request_id: "req" } } })
        : route.fulfill({ json: { access_token: "test-access", refresh_token: "test-refresh", expires_in: 3600, token_type: "bearer" } });
    });
    const fragment = outcome === "cancelled"
      ? `state=${state}&error=access_denied`
      : `state=${outcome === "wrong-state" ? "mismatched-state" : state}&id_token=fictional.google.token&authuser=0`;
    await page.goto(`/app/#${fragment}`);

    if (outcome === "success") {
      await expect(page.getByRole("heading", { name: "Chat", exact: true, level: 1 })).toBeVisible();
      expect(submissions).toHaveLength(1);
      expect(submissions[0]).toMatchObject({ provider: "google", id_token: "fictional.google.token", nonce });
    } else {
      const message = {
        "wrong-state": "Google sign-in could not be verified. Please try again.",
        cancelled: "Google sign-in was cancelled.",
        "server-refuses": "Google sign-in nonce validation failed",
      }[outcome];
      await expect(page.getByText(message, { exact: true })).toBeVisible();
      expect(submissions).toHaveLength(outcome === "server-refuses" ? 1 : 0);
      await expect(page.getByRole("button", { name: "Continue with Google" })).toBeEnabled();
    }
    // The ID token never stays in the address bar or the history entry.
    expect(new URL(page.url()).hash).toBe("");
  });
}
