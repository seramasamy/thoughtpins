import { expect, test } from "@playwright/test";
import { installMockApi } from "./mockApi";

/**
 * The transcript is bottom-anchored so a short conversation sits against the
 * composer instead of stranding the reply half a window above the input. That
 * is done with an auto-margin spacer rather than `justify-content: flex-end`,
 * because flex-end makes overflowing content unreachable above the fold in
 * several browsers — the layout looks right and the history becomes unscrollable.
 *
 * This asserts the half that a screenshot cannot show: that a transcript long
 * enough to overflow can still be scrolled back to its first message.
 */
test("a long transcript can still be scrolled back to its first message", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await installMockApi(page, "local", 0, "product");
  await page.goto("/app/");
  await page.waitForLoadState("networkidle");

  const composer = page.locator("textarea, [contenteditable=true]").first();
  for (let i = 1; i <= 10; i += 1) {
    await composer.click();
    await composer.fill(`turn number ${i} about the harbour project and the copper lantern`);
    await composer.press("Enter");
    await page.waitForTimeout(350);
  }
  await page.waitForTimeout(1200);

  const metrics = await page.evaluate(() => {
    const stream = document.querySelector(".chat-stream") as HTMLElement;
    return { scrollHeight: stream.scrollHeight, clientHeight: stream.clientHeight };
  });
  expect(metrics.scrollHeight).toBeGreaterThan(metrics.clientHeight);

  await page.evaluate(() => {
    const stream = document.querySelector(".chat-stream") as HTMLElement;
    // scroll-behavior is smooth, so assigning scrollTop starts an animation and
    // reads back the previous value. Force it instant, then let it settle.
    stream.style.scrollBehavior = "auto";
    stream.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
  });
  await page.waitForTimeout(700);

  const top = await page.evaluate(() => {
    const stream = document.querySelector(".chat-stream") as HTMLElement;
    const first = document.querySelector(".chat-message-row") as HTMLElement;
    const streamRect = stream.getBoundingClientRect();
    const firstRect = first.getBoundingClientRect();
    return {
      scrollTop: stream.scrollTop,
      offsetFromTop: Math.round(firstRect.top - streamRect.top),
      visible: firstRect.bottom > streamRect.top && firstRect.top < streamRect.bottom,
    };
  });

  expect(top.scrollTop).toBe(0);
  expect(top.visible).toBe(true);
  expect(top.offsetFromTop).toBeGreaterThanOrEqual(-1);
});
