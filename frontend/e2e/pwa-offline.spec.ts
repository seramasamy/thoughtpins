import { expect, test } from "@playwright/test";

test("app shell remains available offline without caching API data", async ({ context, page }) => {
  await page.goto("/app/");
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await expect(page).toHaveTitle("Thought Pins");

  const cachedPaths = await page.evaluate(async () => {
    const keys = await caches.keys();
    const requests = (await Promise.all(keys.map((key) => caches.open(key).then((cache) => cache.keys())))).flat();
    return requests.map((request) => new URL(request.url).pathname);
  });
  expect(cachedPaths.length).toBeGreaterThan(0);
  expect(cachedPaths.every((path) => path.startsWith("/app/"))).toBeTruthy();
  expect(cachedPaths.some((path) => path.startsWith("/v1/") || path.startsWith("/api/"))).toBeFalsy();

  await context.setOffline(true);
  await page.reload();
  await expect(page).toHaveTitle("Thought Pins");
  await expect(page.locator("body")).toContainText("Thought Pins");
});
