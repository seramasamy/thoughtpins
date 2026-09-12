/* Shared by the modern and classic homepages. Storage is optional. */
(() => {
  const root = document.documentElement;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const toggle = document.querySelector("[data-motion-toggle]");
  let paused = false;
  try { paused = sessionStorage.getItem("thoughtpins.motionPaused") === "true"; } catch { /* Use memory only. */ }
  function sync() {
    root.dataset.motionPaused = String(paused || reduced.matches);
    if (toggle) {
      toggle.hidden = reduced.matches;
      toggle.textContent = paused ? "Resume motion" : "Pause motion";
    }
    document.dispatchEvent(new Event("thoughtpins:motionchange"));
  }
  toggle?.addEventListener("click", () => {
    paused = !paused;
    try { sessionStorage.setItem("thoughtpins.motionPaused", String(paused)); } catch { /* Retain this visit's choice. */ }
    sync();
  });
  reduced.addEventListener("change", sync);
  sync();
})();
