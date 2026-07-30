import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import { readFileSync } from "node:fs";

const BASE = "https://thoughtpins.com";
const SCRATCH = "C:/Users/surya/AppData/Local/Temp/claude/C--Users-surya-Desktop-My-Journal-AI/1b32a1a6-10fe-455f-9dfc-089e7880bad9/scratchpad";
const OUT = `${SCRATCH}/ui-audit`;
await mkdir(OUT, { recursive: true });

const [accessToken, refreshToken] = readFileSync(`${SCRATCH}/uitok.txt`, "utf8").trim().split("|");

const devices = [
  { name: "phone-sm", width: 320, height: 568, touch: true },
  { name: "phone", width: 390, height: 844, touch: true },
  { name: "tablet", width: 834, height: 1194, touch: true },
  { name: "laptop", width: 1280, height: 800, touch: false },
  { name: "desktop", width: 1600, height: 1000, touch: false },
];

const publicPages = [["home", "/"], ["classic", "/classic/"], ["privacy", "/privacy"], ["support", "/support"]];
// Nav labels as rendered, so navigation happens the way a user does it.
const appViews = ["Chat", "People", "Pins", "New journal entry", "All memory cards", "Source library", "Processing activity", "Settings & account"];

const browser = await chromium.launch();
const problems = [];
const MIN_TOUCH = 40; // below Apple's 44 guidance is worth flagging on touch

async function audit(page, label, device) {
  const m = await page.evaluate((minTouch) => {
    const doc = document.documentElement;
    const overflow = doc.scrollWidth - window.innerWidth;
    const wide = [];
    for (const el of document.querySelectorAll("body *")) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.right > window.innerWidth + 2) {
        wide.push(`${el.tagName.toLowerCase()}.${(el.className || "").toString().split(" ")[0]}`);
        if (wide.length > 4) break;
      }
    }
    const small = [];
    for (const el of document.querySelectorAll("button, a[href], input, select, textarea")) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0 && r.height < minTouch) {
        small.push(`${(el.className || "").toString().split(" ")[0] || el.tagName.toLowerCase()}[${(el.textContent || "").trim().slice(0, 16)}] ${Math.round(r.height)}px`);
        if (small.length > 4) break;
      }
    }
    return { overflow, wide, small, signedIn: !/welcome back|create your memory space/i.test(document.body.innerText) };
  }, MIN_TOUCH);

  if (m.overflow > 2) problems.push(`OVERFLOW  ${device.name} ${label}: ${m.overflow}px [${m.wide.join(", ")}]`);
  if (device.touch && m.small.length) problems.push(`TAP       ${device.name} ${label}: ${m.small.slice(0, 3).join("; ")}`);
  await page.screenshot({ path: `${OUT}/${device.name}-${label}.png` });
  return m.signedIn;
}

for (const device of devices) {
  const ctx = await browser.newContext({
    viewport: { width: device.width, height: device.height },
    hasTouch: device.touch,
    isMobile: device.touch,
  });
  const page = await ctx.newPage();

  for (const [label, path] of publicPages) {
    await page.goto(BASE + path, { waitUntil: "networkidle" });
    await page.waitForTimeout(500);
    await audit(page, label, device);
  }

  await page.goto(`${BASE}/app/`, { waitUntil: "domcontentloaded" });
  await page.evaluate(([a, r]) => {
    localStorage.setItem("thoughtpins.session.v1", JSON.stringify({ accessToken: a, refreshToken: r }));
  }, [accessToken, refreshToken]);
  await page.goto(`${BASE}/app/`, { waitUntil: "networkidle" });
  await page.waitForTimeout(2500);

  const signedIn = await audit(page, "app-default", device);
  if (!signedIn) {
    problems.push(`SESSION   ${device.name}: could not reach the signed-in app`);
    await ctx.close();
    continue;
  }

  for (const label of appViews) {
    const target = page.getByRole("button", { name: label, exact: false }).first();
    if (!(await target.isVisible().catch(() => false))) continue;
    await target.click().catch(() => {});
    await page.waitForTimeout(1200);
    await audit(page, `app-${label.replace(/[^a-z]/gi, "").toLowerCase()}`, device);
  }
  await ctx.close();
  console.log(`swept ${device.name}`);
}

console.log(`\n=== ${problems.length} problem(s) ===`);
for (const p of problems) console.log("  " + p);
await browser.close();
