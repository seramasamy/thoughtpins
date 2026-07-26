export function registerAppShellServiceWorker(): void {
  if (!import.meta.env.PROD || !("serviceWorker" in navigator)) return;
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/app/sw.js", { scope: "/app/" });
  }, { once: true });
}
