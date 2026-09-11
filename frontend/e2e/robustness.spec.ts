import { expect, test, type Page } from "@playwright/test";
import { installMockApi } from "./mockApi";

const reply = "I remember the Atlas Cafe note and the copper lantern detail.";
const composer = (page: Page) => page.getByRole("textbox", { name: "Message Thought Pins", exact: true });

async function boot(page: Page) {
  const mock = await installMockApi(page, "local", 0, "product");
  await page.goto("/app/");
  await expect(composer(page)).toBeVisible();
  return mock;
}

for (const status of [429, 503]) {
  test(`a ${status} chat failure preserves the draft and allows an explicit retry`, async ({ page }) => {
    const mock = await boot(page);
    await page.route("**/v1/chat", route => route.fulfill({ status, json: { error: { message: "Please try again shortly." } } }), { times: 1 });
    await composer(page).fill("My fictional note includes a detail I must not lose.");
    await composer(page).press("Enter");
    await expect(page.getByText("Please try again shortly.", { exact: true })).toBeVisible();
    await expect(composer(page)).toHaveValue("My fictional note includes a detail I must not lose.");
    await page.getByRole("button", { name: "Send message", exact: true }).click();
    await expect(page.getByText(reply, { exact: true })).toBeVisible();
    expect(mock?.getChatPostCount()).toBe(1);
    await expect(page.locator(".chat-message-row.user")).toHaveCount(1);
  });
}

test("a failed send does not overwrite the next message being drafted", async ({ page }) => {
  await boot(page);
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/v1/chat", async route => {
    await held;
    await route.fulfill({ status: 503, json: { error: { message: "Please try again shortly." } } });
  });
  await composer(page).fill("First question");
  await composer(page).press("Enter");
  await expect(page.getByRole("button", { name: "Stop reply" })).toBeVisible();
  await composer(page).fill("Next question still being written");
  release();
  await expect(page.getByText("Please try again shortly.", { exact: true })).toBeVisible();
  await expect(composer(page)).toHaveValue("Next question still being written");
  // The first question must remain recoverable when the composer has newer text.
  await expect(page.getByText("First question", { exact: true })).toBeVisible();
});

test("stopping a slow reply never resends it and another question still works", async ({ page }) => {
  const mock = await boot(page);
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/v1/chat", async route => {
    await held;
    await route.fulfill({ json: { status: "completed", reply: "Late reply must stay hidden." } }).catch(() => {});
  }, { times: 1 });
  await composer(page).fill("Slow question");
  await composer(page).press("Enter");
  await page.getByRole("button", { name: "Stop reply", exact: true }).click();
  await expect(page.getByText("Stopped before a reply came back. Ask again whenever you are ready.")).toBeVisible();
  await expect(composer(page)).toHaveValue("");
  release();
  await composer(page).fill("A new question");
  await composer(page).press("Enter");
  await expect(page.getByText(reply, { exact: true })).toBeVisible();
  await expect(page.getByText("Late reply must stay hidden.")).toHaveCount(0);
  expect(mock?.getChatPostCount()).toBe(1);
});

test("editing a message respects IME composition and Shift+Enter", async ({ page }) => {
  const mock = await boot(page);
  await composer(page).fill("Original question");
  await composer(page).press("Enter");
  await expect(page.getByText(reply, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Restore conversation" }).click();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  const editor = page.getByRole("textbox", { name: "Edit your message and send it again" });
  await editor.fill("日本語の入力");
  await editor.dispatchEvent("keydown", { key: "Enter", code: "Enter", isComposing: true, keyCode: 229 });
  await expect(editor).toBeVisible();
  expect(mock?.getChatPostCount()).toBe(1);
  await editor.press("Shift+Enter");
  await expect(editor).toHaveValue("日本語の入力\n");
  await editor.press("Escape");
  await expect(page.getByText("Original question", { exact: true })).toBeVisible();
});

test("a rejected edit preserves the original conversation and edited draft", async ({ page }) => {
  await boot(page);
  await composer(page).fill("Original question");
  await composer(page).press("Enter");
  await expect(page.getByText(reply, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Restore conversation" }).click();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  const editor = page.getByRole("textbox", { name: "Edit your message and send it again" });
  await editor.fill("Revised question");
  await page.route("**/v1/chat", route => route.fulfill({ status: 503, json: { error: { message: "Edit could not be sent." } } }));
  await page.getByRole("button", { name: "Send again" }).click();
  await expect(page.getByText("Edit could not be sent.", { exact: true })).toBeVisible();
  await expect(editor).toHaveValue("Revised question");
  await expect(page.getByText(reply, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByText("Original question", { exact: true })).toBeVisible();
});

test("whitespace and composing Enter never send a message", async ({ page }) => {
  const mock = await boot(page);
  await composer(page).fill("  \n  ");
  await expect(page.getByRole("button", { name: "Send message" })).toBeDisabled();
  await composer(page).press("Enter");
  await composer(page).fill("入力中");
  await composer(page).dispatchEvent("keydown", { key: "Enter", isComposing: true, keyCode: 229 });
  expect(mock?.getChatPostCount()).toBe(0);
  await expect(composer(page)).toHaveValue("入力中");
});

for (const width of [320, 1440]) {
  test(`long text, markup and unbroken links remain safe at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await boot(page);
    const content = `A fictional journal. ${"detail ".repeat(250)}\n\nhttps://example.com/${"a".repeat(500)}\n\n<script>window.untrustedScriptRan = true</script>`;
    await page.route("**/v1/chat", route => route.fulfill({ json: { status: "completed", route_type: "chat", reply: content } }));
    await composer(page).fill(content);
    await composer(page).press("Enter");
    await expect(page.locator(".chat-message-row.assistant")).toHaveCount(1);
    expect(await page.evaluate(() => "untrustedScriptRan" in window)).toBe(false);
    const overflow = await page.locator(".chat-stream").evaluate(el => el.scrollWidth - el.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
    await expect(composer(page)).toBeVisible();
  });
}
