import childProcess from "node:child_process";
import { EventEmitter } from "node:events";
import { syncBuiltinESMExports } from "node:module";
import { copyFileSync, cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const originalExec = childProcess.exec;

childProcess.exec = function patchedExec(command, options, callback) {
  const commandText = Array.isArray(command) ? command.join(" ") : String(command);
  const maybeCallback = typeof options === "function" ? options : callback;
  if (process.platform === "win32" && commandText.trim().toLowerCase() === "net use") {
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    queueMicrotask(() => {
      if (maybeCallback) maybeCallback(null, "", "");
      child.emit("close", 0);
      child.emit("exit", 0);
    });
    return child;
  }
  return originalExec(command, options, callback);
};

syncBuiltinESMExports();

const { build } = await import("vite");

try {
  await build({
    configFile: "vite.config.ts",
    configLoader: "native",
  });
  writeFileSync(
    resolve("dist", ".thoughtpins-build.json"),
    `${JSON.stringify({ app: "Thought Pins", builtAt: new Date().toISOString(), builder: "frontend/scripts/build.mjs" }, null, 2)}\n`,
    "utf8",
  );
} catch (error) {
  const text = `${error?.stack || error}`;
  if (process.platform !== "win32" || !text.includes("spawn EPERM")) {
    throw error;
  }
  const html = readFileSync(resolve("static/index.html"), "utf8");
  const js = readFileSync(resolve("static/app.js"), "utf8");
  if (!html.includes("/app/app.js") || !html.includes("/app/styles.css")) {
    throw new Error("Static fallback index.html is missing app assets.");
  }
  new Function(js);
  const dist = resolve("dist");
  rmSync(dist, { recursive: true, force: true });
  mkdirSync(dist, { recursive: true });
  copyFileSync(resolve("static", "index.html"), resolve(dist, "index.html"));
  copyFileSync(resolve("static", "app.js"), resolve(dist, "app.js"));
  copyFileSync(resolve("static", "styles.css"), resolve(dist, "styles.css"));
  copyFileSync(resolve("public", "manifest.webmanifest"), resolve(dist, "manifest.webmanifest"));
  copyFileSync(resolve("public", "sw.js"), resolve(dist, "sw.js"));
  cpSync(resolve("public", "assets"), resolve(dist, "assets"), { recursive: true });
  writeFileSync(
    resolve(dist, ".thoughtpins-build.json"),
    `${JSON.stringify({
      app: "Thought Pins",
      builtAt: new Date().toISOString(),
      builder: "frontend/scripts/build.mjs",
      mode: "static-fallback",
      reason: "Vite/esbuild child-process spawn is blocked on this Windows host",
    }, null, 2)}\n`,
    "utf8",
  );
  console.warn("Vite/esbuild child-process spawn is blocked on this Windows host; static fallback written to dist.");
}
