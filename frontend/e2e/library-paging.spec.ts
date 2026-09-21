import { expect, test } from "@playwright/test";
import { installMockApi } from "./mockApi";

const source = (id: string, title: string) => ({ id, title, source_type: "text", chunks: 1,
  status: "processed", topics: [], key_concepts: [], source_domain: "fixture.invalid" });

test("older sources can be paged and searched without stale responses replacing the results", async ({ page }) => {
  await installMockApi(page);
  const offsets: number[] = [];
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/v1/library?*", async route => {
    const params = new URL(route.request().url()).searchParams;
    const query = params.get("q") || "";
    const offset = Number(params.get("offset") || 0);
    if (query === "older") {
      await held;
      await route.fulfill({ json: [source("old", "Older stale result")] });
    } else if (query === "archive") {
      expect(offset).toBe(0);
      await route.fulfill({ json: [source("archive", "Archive notebook beyond page one")] });
    } else {
      offsets.push(offset);
      await route.fulfill({ json: offset === 0
        ? Array.from({ length: 100 }, (_, i) => source(`source-${i}`, `Synthetic note ${i}`))
        : [source("source-99", "Synthetic note 99"), source("last", "Final older source")] });
    }
  });
  await page.goto("/app/");
  await page.getByRole("navigation", { name: "Primary", exact: true }).getByRole("button", { name: "Pins", exact: true }).click();
  await expect(page.locator(".pin-card")).toHaveCount(100);
  await page.getByRole("button", { name: "Load more sources" }).click();
  await expect(page.locator(".pin-card")).toHaveCount(101);
  await expect(page.getByRole("heading", { name: "Final older source" })).toBeVisible();
  expect(offsets).toEqual([0, 100]);
  await expect(page.getByRole("button", { name: "Load more sources" })).toHaveCount(0);
  const search = page.getByLabel("Search pins");
  const started = page.waitForRequest(request => new URL(request.url()).searchParams.get("q") === "older");
  await search.fill("older");
  await started;
  await search.fill("archive");
  await expect(page.getByRole("heading", { name: "Archive notebook beyond page one" })).toBeVisible();
  release();
  await expect(page.locator(".pin-card")).toHaveCount(1);
  await expect(page.getByText("Older stale result", { exact: true })).toHaveCount(0);
});
