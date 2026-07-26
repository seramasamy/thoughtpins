const CACHE_VERSION = "thought-pins-shell-v1";
const APP_ROOT = "/app/";
const SHELL_ASSETS = [
  APP_ROOT,
  `${APP_ROOT}index.html`,
  `${APP_ROOT}manifest.webmanifest`,
  `${APP_ROOT}assets/thought-pins-mark.svg`,
  `${APP_ROOT}assets/thought-pins-brain-pin.svg`,
  `${APP_ROOT}assets/thought-pins-icon-1024.png`,
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_VERSION).then((cache) => cache.addAll(SHELL_ASSETS)));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_VERSION).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin || !url.pathname.startsWith(APP_ROOT)) return;

  if (request.mode === "navigate") {
    event.respondWith(networkFirst(request, APP_ROOT));
    return;
  }

  if (url.pathname.startsWith(`${APP_ROOT}assets/`)) {
    event.respondWith(cacheFirst(request));
    return;
  }

  event.respondWith(networkFirst(request));
});

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (isCacheable(response)) {
    const cache = await caches.open(CACHE_VERSION);
    await cache.put(request, response.clone());
  }
  return response;
}

async function networkFirst(request, fallbackPath) {
  try {
    const response = await fetch(request);
    if (isCacheable(response)) {
      const cache = await caches.open(CACHE_VERSION);
      await cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) return cached;
    if (fallbackPath) {
      const fallback = await caches.match(fallbackPath);
      if (fallback) return fallback;
    }
    throw error;
  }
}

function isCacheable(response) {
  return response && response.ok && response.type === "basic";
}
