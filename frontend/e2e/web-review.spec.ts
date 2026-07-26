import { AxeBuilder } from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { installMockApi } from "./mockApi";

const screenshotDir = path.resolve(process.cwd(), "..", "reports", "web-smoke");
const proofManifestPath = path.join(screenshotDir, "web-proof-manifest.json");

type ProofScreenshot = {
  file: string;
  scenario: string;
  viewport: string;
  min_width: number;
  min_height: number;
};

type ShellProofScreenshot = ProofScreenshot & {
  viewportName: "desktop" | "tablet" | "mobile";
  width: number;
  height: number;
};

type LayoutAuditViewport = {
  name: string;
  width: number;
  height: number;
};

const shellProofs: ShellProofScreenshot[] = [
  {
    viewportName: "desktop",
    width: 1440,
    height: 960,
    file: "desktop-review-shell.png",
    scenario: "desktop responsive app shell",
    viewport: "desktop",
    min_width: 1200,
    min_height: 800,
  },
  {
    viewportName: "tablet",
    width: 834,
    height: 1112,
    file: "tablet-review-shell.png",
    scenario: "tablet responsive app shell",
    viewport: "tablet",
    min_width: 760,
    min_height: 900,
  },
  {
    viewportName: "mobile",
    width: 390,
    height: 844,
    file: "mobile-review-shell.png",
    scenario: "mobile responsive app shell",
    viewport: "mobile",
    min_width: 360,
    min_height: 700,
  },
];

const currentIphoneProofs: Array<ProofScreenshot & LayoutAuditViewport> = [
  {
    name: "iPhone 17 / 17 Pro",
    width: 402,
    height: 874,
    file: "iphone17-pro-review-shell.png",
    scenario: "iPhone 17 class responsive app shell",
    viewport: "iPhone 17 / 17 Pro",
    min_width: 390,
    min_height: 820,
  },
  {
    name: "iPhone Air",
    width: 420,
    height: 912,
    file: "iphone-air-review-shell.png",
    scenario: "iPhone Air responsive app shell",
    viewport: "iPhone Air",
    min_width: 400,
    min_height: 860,
  },
  {
    name: "iPhone 17 Pro Max",
    width: 440,
    height: 956,
    file: "iphone17-pro-max-review-shell.png",
    scenario: "iPhone 17 Pro Max responsive app shell",
    viewport: "iPhone 17 Pro Max",
    min_width: 420,
    min_height: 900,
  },
];

const iosViewportAudits: LayoutAuditViewport[] = [
  { name: "iPhone SE", width: 320, height: 568 },
  { name: "iPhone 8", width: 375, height: 667 },
  { name: "iPhone 16", width: 393, height: 852 },
  { name: "iPhone 17 / 17 Pro", width: 402, height: 874 },
  { name: "iPhone Air", width: 420, height: 912 },
  { name: "iPhone 16 Pro Max", width: 430, height: 932 },
  { name: "iPhone 17 Pro Max", width: 440, height: 956 },
  { name: "iPad mini", width: 744, height: 1133 },
  { name: "iPad Air", width: 834, height: 1112 },
  { name: "iPad Pro 12.9", width: 1024, height: 1366 },
  { name: "iPhone 17 landscape", width: 874, height: 402 },
  { name: "iPad mini landscape", width: 1133, height: 744 },
  { name: "iPad Pro 12.9 landscape", width: 1366, height: 1024 },
];

const utilityViewAudits = [
  { action: "New journal entry", heading: "Capture", slug: "capture" },
  { action: "Source library", heading: "Library", slug: "library" },
  { action: "All entries", heading: "Entries", slug: "entries" },
  { action: "All memory cards", heading: "Memory", slug: "memory" },
  { action: "Processing activity", heading: "Activity", slug: "activity" },
  { action: "System status", heading: "Status", slug: "status" },
  { action: "Settings & account", heading: "Account", slug: "account" },
  { action: "Privacy & support", heading: "Legal", slug: "legal" },
];

function usesMobileNavigation(viewport: LayoutAuditViewport): boolean {
  return viewport.width <= 700 || (viewport.height <= 500 && viewport.width <= 960);
}

const flowProofs = {
  auth: {
    file: "auth-review.png",
    scenario: "auth login and registration without founder controls",
    viewport: "desktop-default",
    min_width: 1000,
    min_height: 650,
  },
  library: {
    file: "library-ingestion-review.png",
    scenario: "library article link and file upload ingestion",
    viewport: "desktop-default",
    min_width: 1000,
    min_height: 650,
  },
  memory: {
    file: "memory-card-review.png",
    scenario: "memory card provenance and Obsidian vault paths",
    viewport: "desktop-default",
    min_width: 1000,
    min_height: 650,
  },
  account: {
    file: "account-export-delete-review.png",
    scenario: "account export and deletion controls",
    viewport: "desktop-default",
    min_width: 1000,
    min_height: 650,
  },
  maintenance: {
    file: "maintenance-review.png",
    scenario: "maintenance mode pauses writes with a useful message",
    viewport: "desktop-default",
    min_width: 1000,
    min_height: 650,
  },
  offline: {
    file: "offline-review.png",
    scenario: "offline backend configuration message",
    viewport: "desktop-default",
    min_width: 1000,
    min_height: 650,
  },
} satisfies Record<string, ProofScreenshot>;

const proofScreenshots: ProofScreenshot[] = [];

test.beforeAll(() => {
  fs.mkdirSync(screenshotDir, { recursive: true });
  resetProofManifest();
});

test.describe("Thought Pins web review smoke", () => {
  test.describe.configure({ mode: "serial" });
  for (const viewport of shellProofs) {
    test(`local app shell is responsive and navigable on ${viewport.viewportName}`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await installMockApi(page, "local");
      await page.goto("/app/");

      await expect(page.getByRole("heading", { level: 1, name: "Chat", exact: true })).toBeVisible();
      await expect(page.getByLabel("Message Thought Pins")).toBeVisible();
      await expect(page.getByRole("navigation", { name: /primary/i }).first()).toBeVisible();
      await expectNoHorizontalOverflow(page);

      if (viewport.viewportName === "mobile") {
        const mobileNav = page.getByRole("navigation", { name: /Mobile primary navigation/i });
        for (const name of ["Recap", "People", "Places", "Pins", "Chat"]) {
          const destination = mobileNav.getByRole("button", { name });
          await expect(destination.locator(".mobile-nav-icon svg")).toBeVisible();
          await expect(destination.locator(".mobile-nav-label")).toBeVisible();
          await destination.click();
          await expect(page.getByRole("heading", { level: 1, name, exact: true })).toBeVisible();
          await expectNoHorizontalOverflow(page);
          await page.screenshot({ path: path.join(screenshotDir, `mobile-${name.toLowerCase()}.png`), fullPage: true });
        }
      } else {
        for (const name of ["Recap", "People", "Places", "Pins", "Chat"]) {
          await page.getByRole("navigation", { name: "Primary" }).getByRole("button", { name }).click();
          await expect(page.getByRole("heading", { level: 1, name, exact: true })).toBeVisible();
          await expectNoHorizontalOverflow(page);
          if (viewport.viewportName === "desktop") {
            await page.screenshot({ path: path.join(screenshotDir, `desktop-${name.toLowerCase()}.png`), fullPage: true });
          }
        }
      }

      await openUtility(page, "Settings & account");
      await expect(page.getByRole("heading", { level: 1, name: "Account", exact: true })).toBeVisible();
      await expect(page.getByText("This session", { exact: true })).toBeVisible();
      await expect(page.locator(".notice.error")).toHaveCount(0);
      await expectNoHorizontalOverflow(page);

      const returnNav = viewport.viewportName === "mobile"
        ? page.getByRole("navigation", { name: /Mobile primary navigation/i })
        : page.getByRole("navigation", { name: "Primary" });
      await returnNav.getByRole("button", { name: "Chat" }).click();

      await captureProofScreenshot(page, viewport);
    });
  }

  for (const viewport of currentIphoneProofs) {
    test(`local app shell is responsive and navigable on ${viewport.name}`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await installMockApi(page, "local");
      await page.goto("/app/");

      await expect(page.getByRole("heading", { level: 1, name: "Chat", exact: true })).toBeVisible();
      await expect(page.getByLabel("Message Thought Pins")).toBeVisible();
      const mobileNav = page.getByRole("navigation", { name: /Mobile primary navigation/i });
      await expect(mobileNav).toBeVisible();
      await mobileNav.getByRole("button", { name: "People" }).click();
      await expect(page.getByRole("heading", { level: 1, name: "People", exact: true })).toBeVisible();
      await mobileNav.getByRole("button", { name: "Pins" }).click();
      await expect(page.getByRole("heading", { level: 1, name: "Pins", exact: true })).toBeVisible();
      await openUtility(page, "Settings & account");
      await expect(page.getByRole("heading", { level: 1, name: "Account", exact: true })).toBeVisible();
      await openUtility(page, "Privacy & support");
      await expect(page.getByRole("heading", { level: 1, name: "Legal", exact: true })).toBeVisible();
      await expectNoHorizontalOverflow(page);
      await mobileNav.getByRole("button", { name: "Chat" }).click();
      await captureProofScreenshot(page, viewport);
    });
  }

  for (const viewport of iosViewportAudits) {
    test(`local app shell avoids overflow on ${viewport.name}`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await installMockApi(page, "local");
      await page.goto("/app/");

      await expect(page.getByRole("heading", { level: 1, name: "Chat", exact: true })).toBeVisible();
      await expect(page.getByLabel("Message Thought Pins")).toBeVisible();
      if (usesMobileNavigation(viewport)) {
        const mobileNav = page.getByRole("navigation", { name: /Mobile primary navigation/i });
        await expect(mobileNav).toBeVisible();
        await mobileNav.getByRole("button", { name: "Recap" }).click();
        await expect(page.getByRole("heading", { level: 1, name: "Recap", exact: true })).toBeVisible();
      } else {
        await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
      }
      await expectNoHorizontalOverflow(page);
    });
  }

  for (const viewport of [
    { name: "desktop", width: 1440, height: 960 },
    { name: "mobile", width: 390, height: 844 },
  ]) {
    test(`all utility views are usable on ${viewport.name}`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await installMockApi(page, "local");
      await page.goto("/app/");

      for (const view of utilityViewAudits) {
        await openUtility(page, view.action);
        await expect(page.getByRole("heading", { level: 1, name: view.heading, exact: true })).toBeVisible();
        await expectNoHorizontalOverflow(page);
        await expectNoComposerNavigationOverlap(page);
        await page.screenshot({
          path: path.join(screenshotDir, `${viewport.name}-utility-${view.slug}.png`),
          fullPage: true,
        });
      }
    });
  }

  for (const viewport of [
    { name: "desktop", width: 1280, height: 820 },
    { name: "mobile", width: 390, height: 844 },
  ]) {
    test(`login and registration are complete on ${viewport.name}`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await installMockApi(page, "auth");
      await page.goto("/app/");

      await expect(page.getByRole("button", { name: "Continue with Google" })).toBeVisible();
      await expect(page.getByRole("button", { name: "Continue with Apple" })).toBeVisible();
      await expect(page.getByText("or sign in with email or phone")).toBeVisible();
      await expectNoHorizontalOverflow(page);
      await page.screenshot({ path: path.join(screenshotDir, `${viewport.name}-auth-login.png`), fullPage: true });

      await page.getByRole("tablist", { name: "Auth mode" }).getByRole("button", { name: "Register" }).click();
      await expect(page.getByText("or sign up with email or phone")).toBeVisible();
      await expect(page.getByRole("checkbox")).toBeVisible();
      await expectNoHorizontalOverflow(page);
      await page.screenshot({ path: path.join(screenshotDir, `${viewport.name}-auth-register.png`), fullPage: true });
    });
  }

  test("auth flow exposes login and registration without founder controls", async ({ page }) => {
    await installMockApi(page, "auth");
    await page.goto("/app/");

    const authModes = page.getByRole("tablist", { name: "Auth mode" });
    await expect(authModes.getByRole("button", { name: "Login", exact: true })).toBeVisible();
    await expect(authModes.getByRole("button", { name: "Register", exact: true })).toBeEnabled();
    await expect(page.getByRole("button", { name: "Continue with Google" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Continue with Apple" })).toBeVisible();
    await expect(page.getByText("or sign in with email or phone")).toBeVisible();
    await expect(page.getByText(/founder/i)).toHaveCount(0);
    await expectNoHorizontalOverflow(page);
    await captureProofScreenshot(page, flowProofs.auth);

    await page.getByLabel("Email or phone").fill("review@example.com");
    await page.getByLabel("Password").fill("correct horse battery staple");
    await page.locator("form").getByRole("button", { name: "Login", exact: true }).click();

    await expect(page.getByRole("heading", { level: 1, name: "Before you continue", exact: true })).toBeVisible();
    await page.getByRole("checkbox", { name: /I understand and allow this processing/i }).check();
    await page.getByRole("button", { name: "Continue", exact: true }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Chat", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: /Review User/i })).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });

  test("signup deep link records legal acknowledgement before opening the app", async ({ page }) => {
    await installMockApi(page, "auth");
    await page.goto("/app/?auth=register");

    const authModes = page.getByRole("tablist", { name: "Auth mode" });
    await expect(authModes.getByRole("button", { name: "Register", exact: true })).toHaveClass(/active/);
    await expect(page.getByRole("link", { name: "Terms", exact: true })).toHaveAttribute("href", "/terms");
    await expect(page.getByRole("link", { name: "Privacy Policy", exact: true })).toHaveAttribute("href", "/privacy");
    await expect(page.getByRole("link", { name: "AI Disclosure", exact: true })).toHaveAttribute("href", "/ai-disclosure");

    const createAccount = page.getByRole("button", { name: "Create Account", exact: true });
    await page.getByLabel("Email", { exact: true }).fill("new-review@example.com");
    await page.getByLabel("Password").fill("correct horse battery staple");
    await expect(createAccount).toBeDisabled();
    await page.getByRole("checkbox").check();
    await expect(createAccount).toBeEnabled();
    await createAccount.click();

    await expect(page.getByRole("heading", { level: 1, name: "Chat", exact: true })).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });

  test("library ingestion supports article links and file uploads", async ({ page }) => {
    const api = await installMockApi(page, "local");
    await page.goto("/app/");

    await openUtility(page, "Source library");
    await expect(page.getByRole("heading", { level: 1, name: "Library", exact: true })).toBeVisible();

    await page.getByLabel("Article link").fill("https://example.com/review");
    await page.getByLabel("Personal note").fill("This review article checks readable source ingestion, concepts, provenance, and memory recall.");
    await page.getByRole("button", { name: /Save Source/i }).click();
    await expect(page.getByText("Last Source")).toBeVisible();
    await expect(page.getByText("Review Article").first()).toBeVisible();
    expect(api?.getLibraryPostCount()).toBe(1);

    await page.getByRole("tablist", { name: "Source format" }).getByRole("button", { name: "File", exact: true }).click();
    await page.getByLabel("Title").fill("Review Upload");
    await page.getByLabel("Destination").selectOption("library");
    await page.getByLabel("File Upload").setInputFiles({
      name: "review.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("Uploaded review note for article memory provenance."),
    });
    await page.getByRole("button", { name: /Upload File/i }).click();
    await expect(page.getByText("Last Upload")).toBeVisible();
    await expect(page.getByText("review.txt").first()).toBeVisible();
    expect(api?.getUploadPostCount()).toBe(1);
    await expectNoHorizontalOverflow(page);
    await captureProofScreenshot(page, flowProofs.library);
  });

  test("memory cards present provenance without internal vault paths", async ({ page }) => {
    await installMockApi(page, "local");
    await page.goto("/app/");

    await page.getByRole("navigation", { name: "Primary" }).getByRole("button", { name: "People" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "People", exact: true })).toBeVisible();
    await page.getByRole("button", { name: /Maya/i }).click();

    await expect(page.getByText("Archive reference")).toBeVisible();
    await expect(page.getByText("Prominence")).toBeVisible();
    await expect(page.getByText("Central", { exact: true })).toBeVisible();
    await expect(page.getByText("People/Maya.md")).toHaveCount(0);
    await expect(page.getByText("Atlas Cafe").first()).toBeVisible();
    await expect(page.getByText("Review Article")).toBeVisible();
    await expect(page.getByText("Library/Articles/Review Article.md")).toHaveCount(0);
    await expect(page.getByText("Met at")).toBeVisible();
    await expect(page.getByText(/TP_DEMO_CORPUS/)).toHaveCount(0);
    await expectNoHorizontalOverflow(page);
    await captureProofScreenshot(page, flowProofs.memory);
  });

  test("Enter sends chat while Shift+Enter keeps a deliberate line break", async ({ page }) => {
    const api = await installMockApi(page, "local", 450);
    await page.goto("/app/");

    const composer = page.getByLabel("Message Thought Pins");
    await composer.fill("first line");
    await composer.press("Shift+Enter");
    await composer.type("second line");
    await expect(composer).toHaveValue("first line\nsecond line");
    expect(api?.getChatPostCount()).toBe(0);

    await composer.press("Enter");
    await expect(page.getByRole("status", { name: "Thinking with your memory" })).toBeVisible();
    await expect(page.getByText("I remember the Atlas Cafe note and the copper lantern detail.")).toBeVisible();
    expect(api?.getChatPostCount()).toBe(1);
    await expectNoHorizontalOverflow(page);
  });

  test("private memories stay out of replies until the user explicitly enables them", async ({ page }) => {
    const api = await installMockApi(page, "local");
    await page.goto("/app/");

    const privateRecall = page.getByRole("checkbox", { name: "Use private memories in this reply" });
    const composer = page.getByLabel("Message Thought Pins");
    await expect(privateRecall).not.toBeChecked();
    await expect(page.getByText("Private memories stay out of replies", { exact: true })).toBeVisible();

    await composer.fill("Keep private memories out");
    await composer.press("Enter");
    await expect.poll(() => api?.getChatPostCount()).toBe(1);
    expect(api?.getLastChatPayload()?.include_private).toBe(false);

    await privateRecall.check();
    await expect(page.getByText("Private memories may inform this reply", { exact: true })).toBeVisible();
    await composer.fill("Use my private memories this time");
    await composer.press("Enter");
    await expect.poll(() => api?.getChatPostCount()).toBe(2);
    expect(api?.getLastChatPayload()?.include_private).toBe(true);
    await expectNoHorizontalOverflow(page);
  });

  test("voice notes require an intentional action and upload through the journal path", async ({ page }) => {
    const api = await installMockApi(page, "local");
    await page.addInitScript(() => {
      class ReviewMediaRecorder {
        static isTypeSupported(type: string) {
          return type === "audio/webm;codecs=opus" || type === "audio/webm";
        }

        state = "inactive";
        mimeType = "audio/webm";
        ondataavailable: ((event: { data: Blob }) => void) | null = null;
        onstop: (() => void) | null = null;

        start() {
          this.state = "recording";
        }

        stop() {
          this.state = "inactive";
          this.ondataavailable?.({ data: new Blob(["review voice note"], { type: this.mimeType }) });
          this.onstop?.();
        }
      }

      Object.defineProperty(navigator, "mediaDevices", {
        configurable: true,
        value: { getUserMedia: async () => ({ getTracks: () => [{ stop() {} }] }) },
      });
      Object.defineProperty(window, "MediaRecorder", { configurable: true, value: ReviewMediaRecorder });
    });
    await page.goto("/app/");

    const record = page.getByRole("button", { name: "Record a voice note" });
    await expect(record).toBeVisible();
    await record.click();
    const disclosure = page.getByRole("dialog", { name: "Record a voice note" });
    await expect(disclosure).toBeVisible();
    await expect(disclosure).toContainText("discard the audio after processing");
    await expect(page.getByRole("button", { name: "Stop voice note" })).toHaveCount(0);
    await page.screenshot({ path: path.join(screenshotDir, "voice-disclosure-desktop.png"), fullPage: true });
    await disclosure.getByRole("button", { name: "Continue" }).click();
    await expect(page.getByRole("button", { name: "Stop voice note" })).toBeVisible();
    await page.getByRole("button", { name: "Stop voice note" }).click();
    await expect(page.getByText("Shared a voice note", { exact: true })).toBeVisible();
    await expect.poll(() => api?.getUploadPostCount()).toBe(1);
    await expectNoHorizontalOverflow(page);
  });

  test("voice disclosure remains usable on compact mobile", async ({ page }) => {
    await installMockApi(page, "local");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/app/");

    await page.getByRole("button", { name: "Record a voice note" }).click();
    const disclosure = page.getByRole("dialog", { name: "Record a voice note" });
    await expect(disclosure).toBeVisible();
    await expect(disclosure.getByRole("button", { name: "Continue" })).toBeVisible();
    await expect(disclosure.getByRole("button", { name: "Cancel" })).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await page.screenshot({ path: path.join(screenshotDir, "voice-disclosure-mobile.png"), fullPage: true });
  });

  test("private deployment exposes separate voice archive consent", async ({ page }) => {
    await installMockApi(page, "local", 0, "review", { voiceArchiveEnabled: true });
    await page.goto("/app/");
    await openUtility(page, "Settings & account");

    await expect(page.getByText("Personal voice archive", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Review and enable" }).click();
    const consent = page.getByRole("group", { name: "Voice archive consent" });
    await expect(consent).toBeVisible();
    const enable = consent.getByRole("button", { name: "Enable archive" });
    await expect(enable).toBeDisabled();
    for (const checkbox of await consent.getByRole("checkbox").all()) await checkbox.check();
    await expect(enable).toBeEnabled();
    await page.screenshot({ path: path.join(screenshotDir, "voice-archive-consent-private.png"), fullPage: true });
    await enable.click();
    await expect(page.getByText("Enabled", { exact: true })).toBeVisible();
  });

  test("Pins composer submits on Enter and keeps thinking visible until the reply", async ({ page }) => {
    const api = await installMockApi(page, "local", 450);
    await page.goto("/app/");
    await page.getByRole("navigation", { name: "Primary" }).getByRole("button", { name: "Pins" }).click();

    const composer = page.getByLabel("Ask Thought Pins");
    await composer.fill("How many people did Sherlock meet?");
    await composer.press("Enter");

    await expect(page.getByRole("status").filter({ hasText: "Thinking with your memory" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 1, name: "Chat", exact: true })).toBeVisible();
    await expect(page.getByText("I remember the Atlas Cafe note and the copper lantern detail.")).toBeVisible();
    expect(api?.getChatPostCount()).toBe(1);
    await expectNoHorizontalOverflow(page);
  });

  test("Enter opens the best visible Pins and memory search result", async ({ page }) => {
    await installMockApi(page, "local");
    await page.goto("/app/");
    await page.getByRole("navigation", { name: "Primary" }).getByRole("button", { name: "Pins" }).click();

    await page.getByLabel("Search pins").fill("Review Article");
    await page.getByLabel("Search pins").press("Enter");
    await expect(page.getByRole("heading", { level: 2, name: "Review Article" })).toBeVisible();
    await expect(page.getByText("A review article about recall quality.").first()).toBeVisible();
    await expect(page.getByText("Technology", { exact: true })).toBeVisible();
    await expect(page.getByText(/Durable Recall/)).toBeVisible();
    await expect(page.getByRole("link", { name: "Open original on Example Review" })).toHaveAttribute("href", "https://example.com/review");
    await expect(page.getByText("Access", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Paywall", { exact: true })).toHaveCount(0);
    await expect(page.getByText(/TP_DEMO_CORPUS/)).toHaveCount(0);

    await page.getByRole("navigation", { name: "Primary" }).getByRole("button", { name: "People" }).click();
    await page.getByLabel("Search memory").fill("Maya");
    await page.getByLabel("Search memory").press("Enter");
    await expect(page.getByText("Archive reference")).toBeVisible();
    await expect(page.getByText("People/Maya.md")).toHaveCount(0);
    await expectNoHorizontalOverflow(page);
  });

  test("response voice defaults to professional and persists an explicit choice", async ({ page }) => {
    const api = await installMockApi(page, "local");
    await page.goto("/app/");
    await openUtility(page, "Settings & account");

    const voice = page.getByLabel("Response voice");
    await expect(voice).toHaveValue("friendly");
    await voice.selectOption("mirror");
    await expect(voice).toHaveValue("mirror");
    expect(api?.getPreferencesPatchCount()).toBe(1);
    expect(api?.getResponseStyle()).toBe("mirror");
    await expect(page.getByText(/Matching your style is always an explicit choice/i)).toBeVisible();
  });

  test("entry importance is accessible, updateable, and clearable", async ({ page }) => {
    await installMockApi(page, "local");
    await page.goto("/app/");
    await openUtility(page, "All entries");

    const five = page.getByRole("button", { name: "Set importance to 5 out of 5" });
    await expect(five).toBeVisible();
    await five.click();
    await expect(five).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText("5 out of 5", { exact: true })).toBeVisible();
    const savedNotice = page.getByRole("status").filter({ hasText: "Importance set to 5 of 5" });
    await expect(savedNotice).toBeVisible();
    await expect(savedNotice).toHaveClass(/is-dismissing/, { timeout: 3_500 });
    await expect(savedNotice).toBeHidden({ timeout: 4_500 });

    await page.getByRole("button", { name: "Clear importance rating" }).click();
    await expect(page.getByText("Unrated", { exact: true })).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await page.screenshot({ path: path.join(screenshotDir, "entry-importance-review.png"), fullPage: true });
  });

  test("importance prompts remain an explicit opt-in preference", async ({ page }) => {
    const api = await installMockApi(page, "local");
    await page.goto("/app/");
    await openUtility(page, "Settings & account");
    await expect(page.getByLabel("Preferred name")).toHaveValue("Review");

    const toggle = page.getByLabel("Occasional importance prompts");
    await expect(toggle).not.toBeChecked();
    await toggle.click();
    await expect.poll(() => api?.getImportancePromptsEnabled()).toBe(true);
    await expect(toggle).toBeChecked();
    expect(api?.getPreferencesPatchCount()).toBe(1);
  });

  test("account export and deletion controls work", async ({ page }) => {
    const api = await installMockApi(page, "auth");
    await page.goto("/app/");

    await page.getByLabel("Email or phone").fill("review@example.com");
    await page.getByLabel("Password").fill("correct horse battery staple");
    await page.locator("form").getByRole("button", { name: "Login", exact: true }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Before you continue", exact: true })).toBeVisible();
    await page.getByRole("checkbox", { name: /I understand and allow this processing/i }).check();
    await page.getByRole("button", { name: "Continue", exact: true }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Chat", exact: true })).toBeVisible();

    await openUtility(page, "Settings & account");
    await expect(page.getByRole("heading", { level: 1, name: "Account", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Account JSON", exact: true }).click();
    await expect(page.getByText('"raw_entries"')).toBeVisible();
    expect(api?.getExportCount()).toBe(1);

    await page.getByLabel("Import Obsidian vault ZIP").setInputFiles({
      name: "review-vault.zip",
      mimeType: "application/zip",
      buffer: Buffer.from("PK review fixture"),
    });
    await expect(page.locator(".import-summary")).toContainText("Journal");
    await expect(page.locator(".import-summary")).toContainText("Library");
    await expect(page.getByRole("button", { name: "Apply import", exact: true })).toBeVisible();
    expect(api?.getVaultImportCount()).toBe(1);
    await page.getByRole("button", { name: "Apply import", exact: true }).click();
    await expect(page.locator(".vault-transfer-progress")).toContainText(/completed/i);

    await page.getByLabel("Type DELETE to confirm account deletion").fill("DELETE");
    await expectNoHorizontalOverflow(page);
    await captureProofScreenshot(page, flowProofs.account);
    await page.getByRole("button", { name: /^Delete$/ }).click();
    await expect(page.getByRole("tablist", { name: "Auth mode" }).getByRole("button", { name: "Login", exact: true })).toBeVisible();
    expect(api?.getDeleteAccountCount()).toBe(1);
    await expectNoHorizontalOverflow(page);
  });

  test("maintenance mode keeps the web app usable and pauses chat writes", async ({ page }) => {
    const api = await installMockApi(page, "maintenance");
    await page.goto("/app/");

    await expect(page.getByRole("status").filter({ hasText: /maintenance/i })).toBeVisible();
    await page.getByLabel("Message Thought Pins").fill("today I tested the review build");
    await page.getByRole("button", { name: /Send/i }).click();

    await expect(page.locator(".chat-message-row.assistant .message-content p").filter({ hasText: /maintenance for a short upgrade/i })).toBeVisible();
    expect(api?.getChatPostCount()).toBe(0);
    await expectNoHorizontalOverflow(page);
    await captureProofScreenshot(page, flowProofs.maintenance);
  });

  test("offline config failure shows a useful review-safe message", async ({ page }) => {
    await installMockApi(page, "offline");
    await page.goto("/app/");

    await expect(page.getByText(/temporarily unreachable/i)).toBeVisible();
    await expect(page.getByLabel("Email or phone")).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await captureProofScreenshot(page, flowProofs.offline);
  });

  test("captures the canonical homepage product preview", async ({ page }) => {
    const siteAsset = path.resolve(process.cwd(), "..", "site", "assets", "product-chat-desktop.png");
    const siteMobileAsset = path.resolve(process.cwd(), "..", "site", "assets", "product-chat-mobile.png");
    const storeAsset = path.resolve(process.cwd(), "..", "deploy", "store", "assets", "web-chat-desktop.png");
    const storeMobileAsset = path.resolve(process.cwd(), "..", "deploy", "store", "assets", "web-chat-mobile.png");
    await page.setViewportSize({ width: 1440, height: 1000 });
    await installMockApi(page, "local", 120, "product");
    await page.goto("/app/");

    const composer = page.getByLabel("Message Thought Pins");
    await composer.fill("What do you remember about the copper lantern at Atlas Cafe?");
    await composer.press("Enter");
    await expect(page.getByText("I remember the Atlas Cafe note and the copper lantern detail.")).toBeVisible();
    await expect(page.getByRole("status", { name: "Thinking with your memory" })).toHaveCount(0);
    await expectNoHorizontalOverflow(page);
    await composer.evaluate((element) => (element as HTMLElement).blur());
    await page.waitForTimeout(120);

    await page.screenshot({ path: siteAsset, fullPage: false });
    fs.copyFileSync(siteAsset, storeAsset);
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByRole("navigation", { name: /Mobile primary navigation/i })).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await page.screenshot({ path: siteMobileAsset, fullPage: false });
    fs.copyFileSync(siteMobileAsset, storeMobileAsset);
  });

  test("review surface has no serious automated accessibility violations", async ({ page }) => {
    await installMockApi(page, "local");
    await page.goto("/app/");
    await expect(page.getByRole("heading", { level: 1, name: "Chat", exact: true })).toBeVisible();

    const results = await new AxeBuilder({ page })
      .include("body")
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();
    const serious = results.violations.filter((violation) => violation.impact === "critical" || violation.impact === "serious");
    expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
  });

  test("dark appearance preserves hierarchy, contrast, and navigation", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "dark", reducedMotion: "no-preference" });
    await page.setViewportSize({ width: 1440, height: 960 });
    await installMockApi(page, "local");
    await page.goto("/app/");

    await expect(page.getByRole("heading", { level: 1, name: "Chat", exact: true })).toBeVisible();
    await expect(page.getByLabel("Message Thought Pins")).toBeVisible();
    await expectNoHorizontalOverflow(page);
    const results = await new AxeBuilder({ page }).include("body").withTags(["wcag2a", "wcag2aa"]).analyze();
    const serious = results.violations.filter((violation) => violation.impact === "critical" || violation.impact === "serious");
    expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
    await page.screenshot({ path: path.join(screenshotDir, "desktop-chat-dark.png"), fullPage: true });
  });
});

async function openUtility(page: Page, name: string) {
  const profile = page.locator(".profile-button");
  const mobileSettings = page.getByRole("button", { name: "Open settings menu" });
  await expect.poll(async () => (await profile.isVisible()) || (await mobileSettings.isVisible())).toBe(true);
  if (await profile.isVisible()) {
    await profile.click();
  } else {
    await mobileSettings.click();
  }
  const dialog = page.getByRole("dialog", { name: "Thought Pins menu" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name }).click();
}

function resetProofManifest() {
  proofScreenshots.length = 0;
  fs.rmSync(proofManifestPath, { force: true });
}

async function captureProofScreenshot(page: Page, screenshot: ProofScreenshot) {
  await page.screenshot({ path: path.join(screenshotDir, screenshot.file), fullPage: true });
  proofScreenshots.push(screenshot);
  fs.writeFileSync(
    proofManifestPath,
    JSON.stringify({
      app: "Thought Pins",
      generated_at_utc: new Date().toISOString(),
      screenshots: proofScreenshots,
    }, null, 2),
  );
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => {
    const root = document.documentElement;
    return Math.max(0, root.scrollWidth - root.clientWidth);
  });
  expect(overflow).toBeLessThanOrEqual(1);
}

async function expectNoComposerNavigationOverlap(page: Page) {
  const composer = page.locator(".global-composer");
  const mobileNavigation = page.locator(".mobile-tabbar");
  if (!(await composer.isVisible()) || !(await mobileNavigation.isVisible())) return;
  const composerBox = await composer.boundingBox();
  const navigationBox = await mobileNavigation.boundingBox();
  if (!composerBox || !navigationBox) return;
  expect(composerBox.y + composerBox.height).toBeLessThanOrEqual(navigationBox.y + 1);
}
