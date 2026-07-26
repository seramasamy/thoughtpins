// Design-review capture helper.
// Usage: node capture.mjs <url> <out.png> [--width=1440] [--height=900]
//        [--scheme=dark|light] [--theme=dark|light] [--scroll] [--wait=2500]
//        [--clip=y,height] [--full]
// --theme presets localStorage tp-theme before load (explicit site toggle).
// --scroll glides through the page so IntersectionObserver reveals fire.
import { chromium } from "playwright";

const [url, out, ...rest] = process.argv.slice(2);
const opt = Object.fromEntries(
  rest.map((a) => {
    const m = a.match(/^--([^=]+)=(.*)$/);
    return m ? [m[1], m[2]] : [a.replace(/^--/, ""), true];
  })
);

const width = Number(opt.width || 1440);
const height = Number(opt.height || 900);
const wait = Number(opt.wait || 2500);

const browser = await chromium.launch();
const ctx = await browser.newContext({
  viewport: { width, height },
  deviceScaleFactor: 1,
  colorScheme: opt.scheme === "dark" ? "dark" : "light",
});
if (opt.theme) {
  await ctx.addInitScript((t) => {
    try { localStorage.setItem("tp-theme", t); } catch {}
  }, String(opt.theme));
}
const page = await ctx.newPage();
await page.goto(url, { waitUntil: "load" });
await page.waitForTimeout(600);

if (opt.scroll) {
  await page.evaluate(async () => {
    const html = document.documentElement;
    const previous = html.style.scrollBehavior;
    html.style.scrollBehavior = "auto"; // bypass CSS smooth scrolling
    const step = window.innerHeight * 0.7;
    for (let y = 0; y <= document.body.scrollHeight; y += step) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 120));
    }
    window.scrollTo(0, 0);
    html.style.scrollBehavior = previous;
  });
}
if (opt.scrolly !== undefined) {
  await page.evaluate(async (raw) => {
    const html = document.documentElement;
    html.style.scrollBehavior = "auto";
    const max = document.body.scrollHeight - window.innerHeight;
    const y = String(raw).endsWith("%")
      ? (parseFloat(raw) / 100) * max
      : Number(raw);
    window.scrollTo(0, Math.max(0, Math.min(max, y)));
    await new Promise((r) => setTimeout(r, 150));
  }, opt.scrolly);
}
await page.waitForTimeout(wait);

const shot = { path: out };
if (opt.full) shot.fullPage = true;
if (opt.clip) {
  const [y, h] = String(opt.clip).split(",").map(Number);
  shot.clip = { x: 0, y, width, height: h };
  shot.fullPage = true;
}
await page.screenshot(shot);
await browser.close();
console.log("captured", out);
