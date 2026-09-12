// Fictional, loopback-only fixtures for the native UI review target.
// Never point this harness at production or load a real account.
import http from 'node:http';
import { installMockApi } from '../e2e/mockApi.ts';
import { NativeReviewHolds } from './native-review-holds.mjs';
const holds = new NativeReviewHolds();
let handler;
let failures = {};
let calls = {};
let delays = {};
async function reset() {
  holds.reset();
  failures = {}; calls = {}; delays = {};
  await installMockApi({ route: async (pattern, cb) => { handler = cb; } }, 'local', 0, 'product', { aiConsentAccepted: true });
}
await reset();
http.createServer(async (req, res) => {
  try {
  let body = ''; for await (const chunk of req) body += chunk;
  // Only the disposable XCTest host uses this loopback-only fault control.
  if (req.url === '/__review' && req.method === 'POST') {
    await reset();
    const settings = JSON.parse(body || '{}');
    failures = settings.failures || {};
    delays = settings.delays || {};
    holds.configure(settings.holds || []);
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end('{}'); return;
  }
  if (req.url === '/__review/release' && req.method === 'POST') {
    holds.release(JSON.parse(body || '{}').route);
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end('{}'); return;
  }
  if (req.url === '/__review' && req.method === 'GET') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ calls })); return;
  }
  const path = new URL(req.url, 'http://127.0.0.1:8877').pathname;
  const key = `${req.method} ${path}`;
  calls[key] = (calls[key] || 0) + 1;
  const failure = failures[key]?.shift();
  await holds.wait(key);
  const delay = Math.max(0, Math.min(5000, Number(delays[key]) || 0));
  if (delay) await new Promise(resolve => setTimeout(resolve, delay));
  if (failure) {
    res.writeHead(failure, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: { code: 'review_failure', message: 'Please try again shortly.' } })); return;
  }
  await handler({
    request: () => ({ url: () => 'http://127.0.0.1:8877' + req.url, method: () => req.method, postDataJSON: () => body ? JSON.parse(body) : {}, postDataBuffer: () => Buffer.from(body) }),
    fulfill: async ({ status = 200, body = '{}', contentType = 'application/json' }) => {
      // Keep fictional journal fixtures inside the selected day on every run.
      const date = new Date();
      const today = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
      if (typeof body === 'string') body = body.replaceAll('2026-07-01', today).replaceAll('2026-07-10', today).replaceAll('TP_DEMO_CORPUS: ', '');
      res.writeHead(status, { 'Content-Type': contentType }); res.end(body);
    },
  });
  } catch {
    // Do not log request bodies, even in this fictional harness.
    if (!res.headersSent) res.writeHead(400, { 'Content-Type': 'application/json' });
    res.end('{"error":{"message":"Invalid review fixture request."}}');
  }
}).listen(8877, '127.0.0.1', () => process.stdout.write('Fictional UI fixture server on 8877\n'));
