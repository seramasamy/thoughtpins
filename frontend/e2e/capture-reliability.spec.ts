import { AxeBuilder } from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { installMockApi } from "./mockApi";
import { installVoiceFixture } from "./voiceFixture";

const file = { name: "synthetic-note.pdf", mimeType: "application/pdf", buffer: Buffer.from("synthetic fixture") };
const ready = {
  status: "processed", route_type: "library_upload", filename: file.name, destination: "library",
  media_kind: "document", extraction_status: "processed", extracted_chars: 48,
  attachment_saved: true, attachment_ref: null, title: "Fixture", entry_id: null,
  job_id: null, document_id: "fixture-source", error: null, metadata: {},
};

async function openLibrary(page: Page) {
  await page.locator(".profile-button").click();
  await page.getByRole("dialog", { name: "Thought Pins menu" }).getByRole("button", { name: "Source library" }).click();
  await page.getByRole("button", { name: "File", exact: true }).click();
}

for (const surface of ["chat", "pins", "library"]) {
  test(`${surface} explains HTTP-success uploads that contain no readable text`, async ({ page }) => {
    await installMockApi(page);
    const payloads: Record<string, unknown>[] = [];
    await page.route("**/v1/uploads", async route => {
      payloads.push(route.request().postDataJSON());
      await route.fulfill({ json: { ...ready, status: "needs_text", extraction_status: "pdf_needs_ocr",
        document_id: null, extracted_chars: 0, error: "No selectable text. Upload images of the pages or paste the text." } });
    });
    await page.goto("/app/");
    if (surface === "library") {
      await openLibrary(page);
      await page.getByLabel("Context").fill("Keep my accompanying note");
      await page.getByLabel("File Upload").setInputFiles(file);
      await page.getByRole("button", { name: "Upload File", exact: true }).click();
    } else if (surface === "pins") {
      await page.getByRole("navigation", { name: "Primary", exact: true }).getByRole("button", { name: "Pins", exact: true }).click();
      await page.getByLabel("Choose a document to pin").setInputFiles(file);
    } else {
      await page.getByLabel("Choose a file to attach").setInputFiles(file);
    }
    await expect(page.getByText("No selectable text. Upload images of the pages or paste the text.", { exact: true })).toBeVisible();
    expect(payloads).toHaveLength(1);
    expect(payloads[0].destination).toBe("library");
    await expect(page.locator(surface === "chat" ? ".chat-stream" : ".upload-feedback").getByText("Ready", { exact: true })).toHaveCount(0);
    if (surface === "library") await expect(page.getByLabel("Context")).toHaveValue("Keep my accompanying note");
  });
}

test("partial extraction is visible and a slow save preserves the next draft", async ({ page }) => {
  await installMockApi(page);
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/v1/uploads", async route => {
    await held;
    await route.fulfill({ json: { ...ready, extraction_status: "partial", metadata: {
      extraction: { warnings: ["Only the first 100 of 101 pages were read."] },
    } } });
  });
  await page.goto("/app/");
  await openLibrary(page);
  await page.getByLabel("File Upload").setInputFiles(file);
  await page.getByLabel("Context").fill("Original note");
  await page.getByRole("button", { name: "Upload File", exact: true }).click();
  await expect(page.getByRole("button", { name: "Processing…", exact: true })).toBeDisabled();
  await page.getByLabel("Context").fill("My next note");
  release();
  await expect(page.getByText("Only the first 100 of 101 pages were read.", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Context")).toHaveValue("My next note");
});

test("legacy office formats are rejected before any upload request", async ({ page }) => {
  const api = await installMockApi(page);
  await page.goto("/app/");
  await page.getByLabel("Choose a file to attach").setInputFiles({ ...file, name: "homework.doc" });
  await expect(page.getByText(/This file format is not supported yet/)).toBeVisible();
  expect(api?.getUploadPostCount()).toBe(0);
});

test("word and powerpoint files are sent for reading", async ({ page }) => {
  await installMockApi(page);
  const filenames: unknown[] = [];
  await page.route("**/v1/uploads", async route => {
    const payload = route.request().postDataJSON();
    filenames.push(payload.filename);
    await route.fulfill({ json: { ...ready, filename: payload.filename } });
  });
  await page.goto("/app/");
  await expect(page.getByLabel("Choose a file to attach")).toHaveAttribute("accept", /\.docx,\.pptx/);
  await page.getByLabel("Choose a file to attach").setInputFiles({ ...file, name: "homework.docx" });
  await expect.poll(() => filenames).toEqual(["homework.docx"]);
  await expect(page.getByText(/This file format is not supported yet/)).toHaveCount(0);
});

for (const width of [320, 390, 834, 1440]) {
  test(`recording review stays local and fits a ${width}px viewport`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: width === 320 ? 568 : 900 });
    const api = await installMockApi(page);
    await installVoiceFixture(page);
    await page.goto("/app/");
    await page.getByRole("button", { name: "Record a voice note" }).click();
    await page.getByRole("button", { name: "Stop voice note" }).click();
    const review = page.getByRole("region", { name: "Review voice note" });
    await expect(review).toBeVisible();
    await expect(review.locator("audio[controls]")).toHaveAttribute("src", /^blob:/);
    expect(api?.getUploadPostCount()).toBe(0);
    await expect(review.getByRole("button", { name: "Save recording" })).toBeInViewport();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    const accessibility = await new AxeBuilder({ page }).include(".voice-draft").analyze();
    expect(accessibility.violations.filter(v => ["serious", "critical"].includes(v.impact || ""))).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath(`voice-review-${width}.png`) });
    await review.getByRole("button", { name: "Discard recording" }).click();
    await expect(review).toHaveCount(0);
    expect(api?.getUploadPostCount()).toBe(0);
  });
}

test("a failed recording save preserves audio and retries with the same idempotency key", async ({ page }) => {
  await installMockApi(page);
  await installVoiceFixture(page);
  const keys: string[] = [];
  const destinations: string[] = [];
  await page.route("**/v1/uploads", async route => {
    keys.push(route.request().headers()["idempotency-key"]);
    destinations.push(route.request().postDataJSON().destination);
    await route.fulfill(keys.length === 1
      ? { status: 503, json: { error: { code: "unavailable", message: "Synthetic transport failure" } } }
      : { json: { ...ready, destination: "journal", document_id: null, entry_id: "journal-fixture" } });
  });
  await page.goto("/app/");
  await page.getByRole("button", { name: "Record a voice note" }).click();
  await page.getByRole("button", { name: "Stop voice note" }).click();
  const save = page.getByRole("button", { name: "Save recording", exact: true });
  await save.click();
  await expect(page.getByText("Synthetic transport failure", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Review voice note" })).toBeVisible();
  await expect(save).toBeEnabled();
  await save.click();
  await expect(page.getByRole("region", { name: "Review voice note" })).toHaveCount(0);
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBeTruthy();
  expect(keys[1]).toBe(keys[0]);
  expect(destinations).toEqual(["journal", "journal"]);
});

test("recorder errors stop the microphone without uploading", async ({ page }) => {
  const api = await installMockApi(page);
  await installVoiceFixture(page);
  await page.goto("/app/");
  await page.getByRole("button", { name: "Record a voice note" }).click();
  await expect(page.getByRole("button", { name: "Stop voice note" })).toBeVisible();
  await page.evaluate(() => (window as unknown as { voiceFixture: { fail: () => void } }).voiceFixture.fail());
  await expect(page.getByText(/The recording stopped unexpectedly/)).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as { voiceFixture: { stops: number } }).voiceFixture.stops)).toBe(1);
  expect(api?.getUploadPostCount()).toBe(0);
});

test("microphone permission resolving after navigation releases the device without uploading", async ({ page }) => {
  const api = await installMockApi(page);
  await installVoiceFixture(page, true);
  await page.goto("/app/");
  await page.getByRole("button", { name: "Record a voice note" }).click();
  await page.getByRole("navigation", { name: "Primary", exact: true }).getByRole("button", { name: "Pins", exact: true }).click();
  await page.evaluate(() => (window as unknown as { voiceFixture: { release: () => void } }).voiceFixture.release());
  await expect.poll(() => page.evaluate(() => (window as unknown as { voiceFixture: { stops: number } }).voiceFixture.stops)).toBe(1);
  expect(api?.getUploadPostCount()).toBe(0);
});
