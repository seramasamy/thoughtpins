// Capture utility-menu views of the running app at 127.0.0.1:8420.
// Usage: node capture-views.mjs <outDir> [--theme=dark] [--scheme=dark] [--width=1440] [--height=900] [--only=Jobs,Status]
import { chromium } from "playwright";

const outDir = process.argv[2] || "../.tmp/views";
const opt = Object.fromEntries(
  process.argv.slice(3).map((a) => {
    const m = a.match(/^--([^=]+)=(.*)$/);
    return m ? [m[1], m[2]] : [a.replace(/^--/, ""), true];
  })
);
const width = Number(opt.width || 1440);
const height = Number(opt.height || 900);
const suffix = `${opt.theme === "dark" ? "dark" : "light"}-${width}`;

const VIEW_MAP = [
  ["capture", "New journal entry"],
  ["library", "Source library"],
  ["entries", "All entries"],
  ["memory", "All memory cards"],
  ["jobs", "Processing activity"],
  ["status", "System status"],
  ["account", "Settings & account"],
  ["legal", "Privacy & support"],
];
const only = opt.only ? String(opt.only).split(",").map((s) => s.trim().toLowerCase()) : null;

const browser = await chromium.launch();
const ctx = await browser.newContext({
  viewport: { width, height },
  colorScheme: opt.scheme === "dark" ? "dark" : "light",
});
if (opt.theme) {
  await ctx.addInitScript((t) => {
    try { localStorage.setItem("tp-theme", t); } catch {}
  }, String(opt.theme));
}
const page = await ctx.newPage();
await page.goto("http://127.0.0.1:8420/app/", { waitUntil: "networkidle" });
await page.waitForTimeout(1400);

for (const [slug, label] of VIEW_MAP) {
  if (only && !only.includes(slug)) continue;
  await page.click('button[aria-label="Open settings menu"]');
  await page.waitForTimeout(350);
  try {
    await page.getByRole("button", { name: new RegExp(`^${label}`, "i") }).first().click({ timeout: 2500 });
  } catch {
    console.log("skip", slug, "(menu item not found)");
    continue;
  }
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${outDir}/${slug}-${suffix}.png` });
  console.log("captured", slug);
}
await browser.close();
console.log("done", suffix);
