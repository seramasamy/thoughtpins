import { chromium } from 'playwright';
import { AxeBuilder } from '@axe-core/playwright';
import fs from 'node:fs/promises';
// Serve site/ on loopback port 8878 before running this audit.
const browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined});
await fs.mkdir('../reports/ui-robustness', {recursive: true});
const results = [];
for (const route of ['/', '/privacy.html', '/terms.html', '/support.html', '/security.html', '/ai-disclosure.html', '/account/delete/', '/classic/']) {
  for (const width of [320, 390, 834, 1440]) {
    const context = await browser.newContext({viewport: {width, height: 900}, reducedMotion: 'reduce'});
    const page = await context.newPage();
    await page.goto('http://127.0.0.1:8878' + route);
    await page.getByRole('heading', {level: 1}).waitFor();
    await page.screenshot({path: `../reports/ui-robustness/site-${route.replaceAll(/[^a-z]/g, "") || "home"}-${width}.png`});
    const axe = await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa']).analyze();
    results.push({route,width, overflow: await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), violations: axe.violations.map(v => ({id: v.id, impact: v.impact, nodes: v.nodes.map(n => ({target: n.target, summary: n.failureSummary}))}))});
    await context.close();
  }
}
await fs.writeFile('../reports/ui-robustness/site-audit.json', JSON.stringify(results, null, 2));
console.log(JSON.stringify({checks:results.length, findings:results.filter(r=>r.overflow || r.violations.length)},null,2));
await browser.close();
if (results.some(r => r.overflow || r.violations.length)) process.exitCode = 1;
