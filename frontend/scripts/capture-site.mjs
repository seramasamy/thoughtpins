import AxeBuilder from "@axe-core/playwright";
import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const baseUrl = process.env.THOUGHTPINS_SITE_URL || "http://127.0.0.1:8420/";
const outputDir = resolve(process.cwd(), "..", "reports", "public-site");
const viewports = [
  { name: "desktop", width: 1440, height: 960 },
  { name: "tablet", width: 834, height: 1194 },
  { name: "mobile", width: 390, height: 844 },
  { name: "small-mobile", width: 320, height: 568 },
  { name: "mobile-landscape", width: 844, height: 390 },
  { name: "tablet-landscape", width: 1133, height: 744 },
];
const policyPaths = ["/privacy", "/terms", "/support", "/security", "/ai-disclosure", "/account/delete"];

await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch();
const results = [];
const policyResults = [];
const failures = [];
let reducedMotionResult = null;

try {
  for (const viewport of viewports) {
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    const response = await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 60_000 });
    if (!response?.ok()) failures.push(`${viewport.name}: homepage returned ${response?.status() || "no response"}`);
    await page.screenshot({ path: resolve(outputDir, `homepage-${viewport.name}.png`), fullPage: true });

    const result = await page.evaluate(() => {
      const primary = document.querySelector("[data-primary-cta]");
      const logo = document.querySelector(".site-brand img") || document.querySelector(".lab-brand img");
      const product = document.querySelector("[data-product-demo]");
      const header = document.querySelector(".site-header");
      const hero = document.querySelector(".hero");
      const headerRect = header?.getBoundingClientRect();
      const heroRect = hero?.getBoundingClientRect();
      const particleCanvas = document.querySelector("[data-constellation]") || document.querySelector("[data-hero-particles]");
      let paintedParticlePixels = 0;
      let faintParticlePixels = 0;
      if (particleCanvas instanceof HTMLCanvasElement && particleCanvas.width && particleCanvas.height) {
        const particleContext = particleCanvas.getContext("2d");
        const pixels = particleContext?.getImageData(0, 0, particleCanvas.width, particleCanvas.height).data;
        if (pixels) {
          for (let offset = 3; offset < pixels.length; offset += 16) {
            const alpha = pixels[offset];
            if (alpha > 2) paintedParticlePixels += 1;
            if (alpha > 2 && alpha < 96) faintParticlePixels += 1;
          }
        }
      }
      return {
        title: document.querySelector("h1")?.textContent?.trim() || "",
        horizontalOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        primaryLabel: primary?.textContent?.trim() || "",
        primaryHref: primary instanceof HTMLAnchorElement ? primary.href : "",
        testSessionVisible: !document.querySelector("[data-test-session-note]")?.hasAttribute("hidden"),
        logoLoaded: logo instanceof HTMLImageElement && logo.complete && logo.naturalWidth > 0,
        productLoaded: product instanceof HTMLElement && product.querySelector("[data-preview-panel]") !== null,
        phonePreviewUsesCanonicalCapture: document.querySelector(".product-app-capture-mobile") instanceof HTMLImageElement || document.querySelector('[data-demo-live="mobile"]') instanceof HTMLElement,
        headerHeroOverlap: headerRect && heroRect ? Math.max(0, Math.round(headerRect.bottom - heroRect.top)) : 0,
        heroNetworkPainted: paintedParticlePixels > 80 && faintParticlePixels > 60,
        paintedParticlePixels,
        faintParticlePixels,
      };
    });

    const preview = page.locator("[data-product-demo]");
    const hasPreviewTabs = (await page.locator("[data-preview-tab]").count()) > 0;
    if (await preview.count() && !hasPreviewTabs) {
      if (!(await page.locator("[data-demo-live]").count())) failures.push(`${viewport.name}: live product demo is missing`);
    } else if (await preview.count()) {
      const expectedInitialMode = viewport.width <= 680 ? "mobile" : "desktop";
      const initialTab = page.locator(`[data-preview-tab="${expectedInitialMode}"]`);
      if (await initialTab.getAttribute("aria-selected") !== "true") {
        failures.push(`${viewport.name}: preview did not select ${expectedInitialMode} by default`);
      }
      const alternateMode = expectedInitialMode === "desktop" ? "mobile" : "desktop";
      const alternateTab = page.locator(`[data-preview-tab="${alternateMode}"]`);
      await alternateTab.click();
      await page.waitForTimeout(450);
      if (await alternateTab.getAttribute("aria-selected") !== "true") {
        failures.push(`${viewport.name}: preview did not switch to ${alternateMode}`);
      }
      if (await page.locator(`[data-preview-panel="${alternateMode}"]`).isHidden()) {
        failures.push(`${viewport.name}: ${alternateMode} preview panel stayed hidden after switching`);
      }
      const alternateGeometry = await previewGeometry(page, alternateMode);
      if (!alternateGeometry.contained) failures.push(`${viewport.name}: ${alternateMode} preview escapes its stage`);
      if (!alternateGeometry.imageUncropped) failures.push(`${viewport.name}: ${alternateMode} preview image is cropped`);
      await initialTab.click();
      await page.waitForTimeout(450);
      const initialGeometry = await previewGeometry(page, expectedInitialMode);
      if (!initialGeometry.contained) failures.push(`${viewport.name}: ${expectedInitialMode} preview escapes its stage`);
      if (!initialGeometry.imageUncropped) failures.push(`${viewport.name}: ${expectedInitialMode} preview image is cropped`);
      if (viewport.name === "mobile") {
        await page.locator(".phone-shell").screenshot({ path: resolve(outputDir, "mobile-preview-detail.png") });
      }
    } else {
      failures.push(`${viewport.name}: interactive product preview is missing`);
    }

    const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    const blockingViolations = axe.violations.filter((violation) => ["serious", "critical"].includes(violation.impact || ""));
    results.push({
      viewport: viewport.name,
      ...result,
      accessibilityViolations: blockingViolations.map((item) => ({
        id: item.id,
        nodes: item.nodes.map((node) => ({ target: node.target, summary: node.failureSummary })),
      })),
    });

    if (!/your memory/i.test(result.title)) failures.push(`${viewport.name}: unexpected h1 ${JSON.stringify(result.title)}`);
    if (result.horizontalOverflow > 1) failures.push(`${viewport.name}: horizontal overflow ${result.horizontalOverflow}px`);
    if (!result.logoLoaded) failures.push(`${viewport.name}: logo did not load`);
    if (!result.productLoaded) failures.push(`${viewport.name}: product image did not load`);
    if (!result.phonePreviewUsesCanonicalCapture) failures.push(`${viewport.name}: mobile preview is not using the canonical app capture`);
    if (!result.heroNetworkPainted) failures.push(`${viewport.name}: neural-link canvas is blank or missing its faint connections`);
    if (!result.primaryHref.includes("/app/")) failures.push(`${viewport.name}: primary CTA does not target the app`);
    if (!result.testSessionVisible || result.primaryLabel !== "Open test session") failures.push(`${viewport.name}: local test-session affordance is missing`);
    if (blockingViolations.length) failures.push(`${viewport.name}: axe ${blockingViolations.map((item) => item.id).join(", ")}`);
    await context.close();
  }

  const reducedMotionContext = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    reducedMotion: "reduce",
  });
  const reducedMotionPage = await reducedMotionContext.newPage();
  const reducedMotionResponse = await reducedMotionPage.goto(baseUrl, { waitUntil: "networkidle", timeout: 60_000 });
  await reducedMotionPage.waitForTimeout(250);
  const initialField = await neuralCanvasSnapshot(reducedMotionPage);
  await reducedMotionPage.waitForTimeout(750);
  const settledField = await neuralCanvasSnapshot(reducedMotionPage);
  reducedMotionResult = {
    status: reducedMotionResponse?.status() || 0,
    painted: initialField.paintedPixels > 80 && settledField.paintedPixels > 80,
    static: initialField.checksum === settledField.checksum,
    initialField,
    settledField,
  };
  if (!reducedMotionResponse?.ok()) failures.push(`reduced motion: homepage returned ${reducedMotionResult.status || "no response"}`);
  if (!reducedMotionResult.painted) failures.push("reduced motion: neural-link field is blank");
  if (!reducedMotionResult.static) failures.push("reduced motion: neural-link field continued animating");
  await reducedMotionContext.close();

  const probeContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const probe = await probeContext.newPage();
  for (const path of policyPaths) {
    const response = await probe.goto(new URL(path, baseUrl).toString(), { waitUntil: "domcontentloaded", timeout: 30_000 });
    // Let the scroll-reveal transitions settle before measuring: axe reports
    // false color-contrast positives on elements mid-fade.
    await probe.waitForTimeout(1500);
    const heading = await probe.locator("h1").first().textContent();
    const horizontalOverflow = await probe.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    const axe = await new AxeBuilder({ page: probe }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    const blockingViolations = axe.violations.filter((violation) => ["serious", "critical"].includes(violation.impact || ""));
    policyResults.push({ path, heading: heading?.trim() || "", horizontalOverflow, accessibilityViolations: blockingViolations.map((item) => item.id) });
    if (!response?.ok() || !heading?.trim()) failures.push(`${path}: unavailable or missing heading`);
    if (horizontalOverflow > 1) failures.push(`${path}: mobile horizontal overflow ${horizontalOverflow}px`);
    if (blockingViolations.length) failures.push(`${path}: axe ${blockingViolations.map((item) => item.id).join(", ")}`);
  }
  await probe.goto(new URL("/app/", baseUrl).toString(), { waitUntil: "networkidle", timeout: 60_000 });
  const appHeading = await probe.locator("h1").first().textContent();
  if (appHeading?.trim() !== "Chat") failures.push(`direct test session did not open Chat; saw ${JSON.stringify(appHeading?.trim())}`);
  await probeContext.close();
} finally {
  await browser.close();
}

const report = { url: baseUrl, generatedAt: new Date().toISOString(), results, reducedMotionResult, policyResults, failures };
await writeFile(resolve(outputDir, "report.json"), `${JSON.stringify(report, null, 2)}\n`, "utf8");
console.log(JSON.stringify(report, null, 2));
if (failures.length) process.exitCode = 1;

async function previewGeometry(page, mode) {
  return page.evaluate((activeMode) => {
    const stage = document.querySelector("[data-preview-stage]");
    const panel = document.querySelector(`[data-preview-panel="${activeMode}"]`);
    const frame = activeMode === "desktop" ? panel?.querySelector(".browser-frame") : panel?.querySelector(".phone-shell");
    const image = panel?.querySelector(".product-app-capture");
    if (!(stage instanceof HTMLElement) || !(panel instanceof HTMLElement) || !(frame instanceof HTMLElement) || !(image instanceof HTMLImageElement)) {
      return { contained: false, imageUncropped: false };
    }
    const stageRect = stage.getBoundingClientRect();
    const frameRect = frame.getBoundingClientRect();
    const imageRect = image.getBoundingClientRect();
    const naturalRatio = image.naturalWidth / image.naturalHeight;
    const renderedRatio = imageRect.width / imageRect.height;
    const fit = getComputedStyle(image).objectFit;
    return {
      contained:
        frameRect.left >= stageRect.left - 1
        && frameRect.right <= stageRect.right + 1
        && frameRect.top >= stageRect.top - 1
        && frameRect.bottom <= stageRect.bottom + 1,
      imageUncropped: fit === "contain" || Math.abs(naturalRatio - renderedRatio) <= 0.01,
    };
  }, mode);
}

async function neuralCanvasSnapshot(page) {
  return page.locator("[data-constellation], [data-hero-particles]").first().evaluate((canvas) => {
    if (!(canvas instanceof HTMLCanvasElement) || !canvas.width || !canvas.height) {
      return { paintedPixels: 0, checksum: 0 };
    }
    const pixels = canvas.getContext("2d")?.getImageData(0, 0, canvas.width, canvas.height).data;
    if (!pixels) return { paintedPixels: 0, checksum: 0 };
    let paintedPixels = 0;
    let checksum = 2166136261;
    for (let offset = 0; offset < pixels.length; offset += 4) {
      if (pixels[offset + 3] > 2) paintedPixels += 1;
      checksum ^= pixels[offset];
      checksum = Math.imul(checksum, 16777619);
      checksum ^= pixels[offset + 1];
      checksum = Math.imul(checksum, 16777619);
      checksum ^= pixels[offset + 2];
      checksum = Math.imul(checksum, 16777619);
      checksum ^= pixels[offset + 3];
      checksum = Math.imul(checksum, 16777619);
    }
    return { paintedPixels, checksum: checksum >>> 0 };
  });
}
