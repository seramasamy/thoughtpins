import { expect, test } from "@playwright/test";
import path from "node:path";
import { installMockApi } from "./mockApi";

const screenshotDir = path.join("test-results", "invite-gate");

const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 960 },
  { name: "laptop", width: 1180, height: 820 },
  { name: "tablet", width: 820, height: 1180 },
  { name: "phone", width: 390, height: 844 },
  { name: "small-phone", width: 320, height: 640 },
];


/** Sign in before navigating. The wall only applies to real accounts: the local
 *  no-auth developer mode is deliberately never gated. */
async function signedIn(page: import("@playwright/test").Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "thoughtpins.session.v1",
      JSON.stringify({ accessToken: "test-access", refreshToken: "test-refresh" }),
    );
  });
}

test.describe("Private launch invite gate", () => {
  for (const viewport of VIEWPORTS) {
    test(`the wall reads well and fits on ${viewport.name}`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await signedIn(page);
    await installMockApi(page, "auth", 0, "review", { aiConsentAccepted: true, inviteRequired: true });
      await page.goto("/app/");

      await expect(page.getByRole("heading", { level: 1, name: /rolling out quietly/i })).toBeVisible();
      await expect(page.getByText("Private testing")).toBeVisible();
      await expect(page.getByRole("textbox", { name: "Invite code" })).toBeVisible();
      await expect(page.getByText("Your details are saved")).toBeVisible();

      // Nothing may scroll sideways at any width.
      const overflow = await page.evaluate(() => {
        const root = document.documentElement;
        return Math.max(0, root.scrollWidth - root.clientWidth);
      });
      expect(overflow).toBeLessThanOrEqual(1);

      await page.screenshot({ path: path.join(screenshotDir, `${viewport.name}.png`), fullPage: true });
    });
  }

  test("the product is not reachable behind the wall", async ({ page }) => {
    await signedIn(page);
    await installMockApi(page, "auth", 0, "review", { aiConsentAccepted: true, inviteRequired: true });
    await page.goto("/app/");

    await expect(page.getByRole("heading", { level: 1, name: /rolling out quietly/i })).toBeVisible();
    // No app shell: no navigation, no composer.
    await expect(page.locator(".mobile-tabbar")).toHaveCount(0);
    await expect(page.locator(".global-composer")).toHaveCount(0);
  });

  test("a valid code opens the app", async ({ page }) => {
    await signedIn(page);
    await installMockApi(page, "auth", 0, "review", { aiConsentAccepted: true, inviteRequired: true });
    await page.goto("/app/");

    await page.getByRole("textbox", { name: "Invite code" }).fill("abcd-efgh-jklm");
    await page.getByRole("button", { name: "Continue", exact: true }).click();

    await expect(page.getByRole("heading", { level: 1, name: "Chat" })).toBeVisible();
  });

  test("a wrong code says so and keeps the person on the page", async ({ page }) => {
    await signedIn(page);
    await installMockApi(page, "auth", 0, "review", { aiConsentAccepted: true, inviteRequired: true });
    await page.goto("/app/");

    await page.getByRole("textbox", { name: "Invite code" }).fill("ZZZZ-ZZZZ-ZZZZ");
    await page.getByRole("button", { name: "Continue", exact: true }).click();

    await expect(page.getByRole("alert")).toContainText(/not valid/i);
    await expect(page.getByRole("heading", { level: 1, name: /rolling out quietly/i })).toBeVisible();
  });

  test("the redeem button stays disabled until something is typed", async ({ page }) => {
    await signedIn(page);
    await installMockApi(page, "auth", 0, "review", { aiConsentAccepted: true, inviteRequired: true });
    await page.goto("/app/");

    const redeem = page.getByRole("button", { name: "Continue", exact: true });
    await expect(redeem).toBeDisabled();
    await page.getByRole("textbox", { name: "Invite code" }).fill("AB");
    await expect(redeem).toBeDisabled();
    await page.getByRole("textbox", { name: "Invite code" }).fill("ABCD");
    await expect(redeem).toBeEnabled();
  });

  test("asking for an invite builds a mail link, with the note optional", async ({ page }) => {
    await signedIn(page);
    await installMockApi(page, "auth", 0, "review", { aiConsentAccepted: true, inviteRequired: true });
    await page.goto("/app/");

    await page.getByRole("button", { name: /don't have a code/i }).click();
    const mailLink = page.getByRole("link", { name: /invite@thoughtpins\.com/ });

    // Optional: the link works before anything is typed.
    await expect(mailLink).toHaveAttribute("href", /^mailto:invite@thoughtpins\.com\?subject=/);

    await page.getByLabel(/Add a note/).fill("I keep a lot of notes and would love to try this.");
    const href = await mailLink.getAttribute("href");
    expect(href).toContain(encodeURIComponent("I keep a lot of notes"));
  });

  test("the wall is absent once the private launch is over", async ({ page }) => {
    await signedIn(page);
    await installMockApi(page, "auth", 0, "review", { aiConsentAccepted: true, inviteRequired: false });
    await page.goto("/app/");
    await expect(page.getByRole("heading", { level: 1, name: "Chat" })).toBeVisible();
  });

  test("an already-admitted account goes straight in", async ({ page }) => {
    await signedIn(page);
    await installMockApi(page, "auth", 0, "review", { aiConsentAccepted: true, inviteRequired: true, inviteAdmitted: true });
    await page.goto("/app/");
    await expect(page.getByRole("heading", { level: 1, name: "Chat" })).toBeVisible();
  });

  test("the code field is reachable and submittable by keyboard alone", async ({ page }) => {
    await signedIn(page);
    await installMockApi(page, "auth", 0, "review", { aiConsentAccepted: true, inviteRequired: true });
    await page.goto("/app/");

    await page.getByRole("textbox", { name: "Invite code" }).focus();
    await page.keyboard.type("ABCD-EFGH-JKLM");
    await page.keyboard.press("Enter");

    await expect(page.getByRole("heading", { level: 1, name: "Chat" })).toBeVisible();
  });
});
