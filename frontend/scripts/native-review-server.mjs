// Fictional, loopback-only fixtures for the native UI review target.
// Never point this harness at production or load a real account.
import http from 'node:http';
import { installMockApi } from '../e2e/mockApi.ts';
let handler;
await installMockApi({ route: async (pattern, cb) => { handler = cb; } }, 'local', 0, 'product', { aiConsentAccepted: true });
http.createServer(async (req, res) => {
  let body = ''; for await (const chunk of req) body += chunk;
  await handler({
    request: () => ({ url: () => 'http://127.0.0.1:8877' + req.url, method: () => req.method, postDataJSON: () => body ? JSON.parse(body) : {}, postDataBuffer: () => Buffer.from(body) }),
    fulfill: async ({ status = 200, body = '{}', contentType = 'application/json' }) => {
      // Keep fictional journal fixtures inside the selected day on every run.
      body = body.replaceAll('2026-07-01', new Date().toISOString().slice(0, 10)).replaceAll('2026-07-10', new Date().toISOString().slice(0, 10)).replaceAll('TP_DEMO_CORPUS: ', '');
      res.writeHead(status, { 'Content-Type': contentType }); res.end(body);
    },
  });
}).listen(8877, '127.0.0.1', () => process.stdout.write('Fictional UI fixture server on 8877\n'));
