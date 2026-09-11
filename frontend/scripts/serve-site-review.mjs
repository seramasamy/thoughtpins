import { createServer } from "node:http";
import { readFile, realpath, stat } from "node:fs/promises";
import { resolve, sep, extname } from "node:path";
import { fileURLToPath } from "node:url";

// Loopback-only static host for the public-site browser tests. Mirrors the
// backend's extensionless policy URLs without loading any account or model.
const root = fileURLToPath(new URL("../../site/", import.meta.url));
const contentTypes = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".json": "application/json", ".webmanifest": "application/manifest+json", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".woff2": "font/woff2" };
const server = createServer(async (request, response) => {
  try {
    const pathname = decodeURIComponent(new URL(request.url, "http://127.0.0.1").pathname);
    if (pathname === "/v1/client-config") {
      response.writeHead(200, { "Content-Type": "application/json" });
      return response.end(JSON.stringify({ auth_required: true }));
    }
    const candidate = resolve(root, "." + pathname);
    if (candidate !== resolve(root) && !candidate.startsWith(resolve(root) + sep)) throw new Error("Outside site");
    const choices = [candidate, resolve(candidate, "index.html"), candidate + ".html"];
    for (const choice of choices) {
      try {
        if (!(await stat(choice)).isFile()) continue;
        const canonical = await realpath(choice);
        if (!canonical.startsWith(resolve(root) + sep)) continue;
        response.writeHead(200, { "Content-Type": contentTypes[extname(canonical)] || "application/octet-stream", "Cache-Control": "no-store" });
        return response.end(await readFile(canonical));
      } catch { /* Try the extensionless or directory form next. */ }
    }
  } catch { /* Invalid paths use the same small, content-free 404. */ }
  response.writeHead(404);
  response.end("Not found");
});
server.listen(8878, "127.0.0.1", () => console.log("Public-site review: http://127.0.0.1:8878"));
