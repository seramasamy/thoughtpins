import { expect, test, type Page } from "@playwright/test";
import { installMockApi } from "./mockApi";

async function openUtility(page: Page, name: string) {
  await page.locator(".profile-button").click();
  await page.getByRole("button", { name, exact: true }).click();
}

for (const target of ["journal", "pin"] as const) {
  test(`${target} saving blocks duplicates and preserves text typed during the request`, async ({ page }) => {
    await installMockApi(page, "local", 0, "product");
    await page.goto("/app/");
    if (target === "journal") await openUtility(page, "New journal entry");
    else await page.getByRole("navigation", { name: "Primary", exact: true }).getByRole("button", { name: "Pins", exact: true }).click();
    const input = page.getByRole("textbox", { name: target === "journal" ? "Journal entry text" : "New pin", exact: true });
    const save = page.getByRole("button", { name: target === "journal" ? "Save" : "Save pin", exact: true });
    let count = 0;
    let release!: () => void;
    const held = new Promise<void>(resolve => { release = resolve; });
    await page.route(target === "journal" ? "**/v1/entries" : "**/v1/library", async route => {
      if (route.request().method() !== "POST") return route.fallback();
      count += 1;
      await held;
      await route.fallback();
    });
    await input.fill("A fictional memory to save");
    // Two submit events before a render also exercise the synchronous guard.
    await input.evaluate(el => {
      const form = (el as HTMLInputElement).form!;
      form.requestSubmit();
      form.requestSubmit();
    });
    await expect.poll(() => count).toBe(1);
    await expect(save).toBeDisabled();
    await input.fill("Another thought still being written");
    release();
    await expect(save).toBeEnabled();
    await expect(input).toHaveValue("Another thought still being written");
    expect(count).toBe(1);
  });
}

test("a failed pin remains editable and can be retried", async ({ page }) => {
  await installMockApi(page, "local", 0, "product");
  await page.goto("/app/");
  await page.getByRole("navigation", { name: "Primary", exact: true }).getByRole("button", { name: "Pins", exact: true }).click();
  await page.route("**/v1/library", route => route.request().method() === "POST"
    ? route.fulfill({ status: 503, json: { error: { message: "Pin unavailable temporarily." } } }) : route.fallback(), { times: 1 });
  const input = page.getByRole("textbox", { name: "New pin", exact: true });
  await input.fill("A fictional note to pin");
  await page.getByRole("button", { name: "Save pin" }).click();
  await expect(page.getByText("Pin unavailable temporarily.", { exact: true })).toBeVisible();
  await expect(input).toHaveValue("A fictional note to pin");
  await page.getByRole("button", { name: "Save pin" }).click();
  await expect(input).toHaveValue("");
});

test("deletion requires the exact confirmation and a failure keeps the account open", async ({ page }) => {
  const mock = await installMockApi(page, "auth", 0, "product", { aiConsentAccepted: true });
  await page.goto("/app/");
  await page.getByLabel("Email or phone").fill("review@example.com");
  await page.getByLabel("Password", { exact: true }).fill("fictional password");
  await page.locator("form").getByRole("button", { name: "Login", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Chat", exact: true, level: 1 })).toBeVisible();
  await openUtility(page, "Settings & account");
  const input = page.getByLabel("Type DELETE to confirm account deletion");
  const remove = page.getByRole("button", { name: "Delete", exact: true });
  for (const invalid of ["", "delete", "DELETE ", "DELET"]) {
    await input.fill(invalid);
    await expect(remove).toBeDisabled();
  }
  expect(mock?.getDeleteAccountCount()).toBe(0);
  await page.route("**/v1/me", route => route.request().method() === "DELETE"
    ? route.fulfill({ status: 503, json: { error: { message: "Deletion unavailable temporarily." } } }) : route.fallback());
  await input.fill("DELETE");
  await remove.click();
  await expect(page.getByText("Deletion unavailable temporarily.", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Account", exact: true, level: 1 })).toBeVisible();
});

test("a failed journal save keeps an encrypted local draft", async ({ page }) => {
  await installMockApi(page, "local", 0, "product");
  await page.goto("/app/");
  await openUtility(page, "New journal entry");
  await page.route("**/v1/entries", route => route.request().method() === "POST"
    ? route.abort("failed") : route.fallback());
  const content = "Fictional offline note with a unique copper bookmark.";
  const input = page.getByRole("textbox", { name: "Journal entry text" });
  await input.fill(content);
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Saved locally. Sync queued drafts when the connection or backend is healthy.", { exact: true })).toBeVisible();
  await expect(input).toHaveValue("");
  expect(await page.evaluate(text => JSON.stringify(localStorage).includes(text), content)).toBe(false);
  await page.reload();
  await openUtility(page, "New journal entry");
  await expect(page.getByText(content, { exact: true })).toBeVisible();
});

test("storage exhaustion leaves an unsaved journal editable", async ({ page }) => {
  await installMockApi(page, "local", 0, "product");
  await page.goto("/app/");
  await openUtility(page, "New journal entry");
  await page.route("**/v1/entries", route => route.request().method() === "POST"
    ? route.abort("failed") : route.fallback());
  await page.evaluate(() => { Storage.prototype.setItem = () => { throw new DOMException("Storage full", "QuotaExceededError"); }; });
  const input = page.getByRole("textbox", { name: "Journal entry text" });
  await input.fill("Fictional note that still needs saving.");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Could not save locally. Your text is still here; try saving again.", { exact: true })).toBeVisible();
  await expect(input).toHaveValue("Fictional note that still needs saving.");
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeEnabled();
});
