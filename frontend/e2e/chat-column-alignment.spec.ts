import { expect, test } from "@playwright/test";
import { installMockApi } from "./mockApi";

/**
 * The conversation is one column, and every part of it agrees where the edges are.
 *
 * It did not used to. The status row ran the full 1130px of the view, message
 * rows were 840, and the composer was 884 — three magic numbers, so the send
 * button sat 22px right of the edge of every reply and the status rule ran
 * 145px past the column it belonged to. Separately, `scrollbar-gutter: stable`
 * on the transcript reserved space on one edge only, which pulled every message
 * 7px left of the composer: close enough that nobody reports it and the whole
 * screen still feels subtly unglued.
 *
 * A screenshot cannot catch either regression. Measuring the rendered boxes can.
 */
test("the status row, transcript and composer share one measure", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 960 });
  await installMockApi(page, "local", 0, "product");
  await page.goto("/app/");
  await expect(page.getByRole("heading", { level: 1, name: "Chat", exact: true })).toBeVisible();
  await page.waitForLoadState("networkidle");

  const composer = page.locator("textarea").first();
  await composer.click();
  await composer.fill("what do you remember about the harbour project");
  await composer.press("Enter");
  const row = page.locator(".chat-message-row").first();
  await expect(row).toBeVisible();

  // Messages enter on `tp-rise`, which transforms them. getBoundingClientRect
  // reports the transformed box, so measuring on `toBeVisible` alone reads a
  // row 11.7px wider than its layout width and fails on the animation rather
  // than on the layout.
  await row.evaluate((element) =>
    Promise.all(element.getAnimations({ subtree: true }).map((animation) => animation.finished.catch(() => undefined))),
  );

  const edges = await page.evaluate(() => {
    const read = (selector: string) => {
      const element = document.querySelector(selector);
      if (!element) return null;
      const rect = element.getBoundingClientRect();
      return { left: Math.round(rect.left), right: Math.round(rect.right) };
    };
    return {
      statusRow: read(".chat-header"),
      messageRow: read(".chat-message-row"),
      composer: read(".chat-composer"),
    };
  });

  expect(edges.statusRow, ".chat-header not found").not.toBeNull();
  expect(edges.messageRow, ".chat-message-row not found").not.toBeNull();
  expect(edges.composer, ".chat-composer not found").not.toBeNull();

  // One pixel of tolerance for sub-pixel rounding, and no more. Two would hide
  // the scrollbar-gutter drift this exists to catch.
  const tolerance = 1;
  for (const edge of ["left", "right"] as const) {
    expect(
      Math.abs(edges.messageRow![edge] - edges.composer![edge]),
      `message row and composer disagree on their ${edge} edge`,
    ).toBeLessThanOrEqual(tolerance);
    expect(
      Math.abs(edges.statusRow![edge] - edges.composer![edge]),
      `status row and composer disagree on their ${edge} edge`,
    ).toBeLessThanOrEqual(tolerance);
  }
});

test("the empty state sits between its spacers, not against the top", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 960 });
  await installMockApi(page, "local", 0, "product");
  await page.goto("/app/");
  await expect(page.getByRole("heading", { level: 1, name: "Chat", exact: true })).toBeVisible();
  await page.waitForLoadState("networkidle");

  const balance = await page.evaluate(() => {
    const stream = document.querySelector(".chat-stream");
    const welcome = document.querySelector(".chat-welcome");
    if (!stream || !welcome) return null;
    const streamBox = stream.getBoundingClientRect();
    const welcomeBox = welcome.getBoundingClientRect();
    return {
      above: Math.round(welcomeBox.top - streamBox.top),
      below: Math.round(streamBox.bottom - welcomeBox.bottom),
    };
  });

  expect(balance, "welcome or stream missing").not.toBeNull();

  // Top-anchored with a clamp() margin left ~340px of dead canvas under the
  // starter chips — the emptiest the product ever looks is the first thing a
  // new account sees. Centred means the two gaps are close to equal.
  const { above, below } = balance!;
  const drift = Math.abs(above - below);
  expect(drift, `welcome is off-centre: ${above}px above, ${below}px below`).toBeLessThanOrEqual(
    Math.max(24, (above + below) * 0.12),
  );
});
