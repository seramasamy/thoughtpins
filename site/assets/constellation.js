/* Decorative network: deterministic layout, bounded drawing, no asset fetch.
   One frame when paused; no frame loop while hidden or outside the viewport. */
(() => {
  const canvas = document.querySelector("[data-constellation]");
  if (!canvas) return;
  let ctx;
  try { ctx = canvas.getContext("2d"); } catch { return; }
  if (!ctx) return;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  let width = 0, height = 0, frame = 0, elapsed = 0, lastTime = 0;
  let inView = true;
  let pageActive = true;
  const moving = () => !reduced.matches && document.documentElement.dataset.motionPaused === "false";
  const visible = () => inView && !document.hidden && pageActive;
  const nodes = Array.from({ length: 64 }, (_, i) => {
    // Golden-angle placement keeps the composition stable across resizes.
    const angle = i * 2.3999632297;
    const radius = 0.45 + ((i * 17) % 31) / 62;
    return { x: 0.5 + Math.cos(angle) * radius * 0.64,
      y: 0.48 + Math.sin(angle) * radius * 0.62, phase: angle, hub: i % 7 === 0 };
  });
  function draw() {
    ctx.clearRect(0, 0, width, height);
    const time = elapsed / 1000;
    const points = nodes.slice(0, width < 600 ? 40 : 64).map(node => ({ ...node,
      x: node.x * width + Math.sin(time * 0.22 + node.phase) * 12,
      y: node.y * height + Math.cos(time * 0.18 + node.phase) * 10 }));
    const reach = Math.min(210, Math.max(110, width * 0.17));
    ctx.lineWidth = 0.8;
    for (let i = 0; i < points.length; i++) {
      const a = points[i];
      // At most three forward links per point keep the mesh legible.
      const near = points.slice(i + 1).map(b => ({ b, distance: Math.hypot(a.x - b.x, a.y - b.y) }))
        .filter(({ distance }) => distance < reach).sort((a, b) => a.distance - b.distance).slice(0, 3);
      for (const { b, distance } of near) {
        ctx.strokeStyle = `rgba(172,168,255,${0.22 * (1 - distance / reach)})`;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      }
      if (a.hub) {
        ctx.beginPath(); ctx.arc(a.x, a.y, 7, 0, Math.PI * 2);
        ctx.strokeStyle = "rgba(232,137,95,0.19)"; ctx.stroke();
      }
      ctx.beginPath(); ctx.arc(a.x, a.y, a.hub ? 2.4 : 1.4, 0, Math.PI * 2);
      ctx.fillStyle = a.hub ? "rgba(232,137,95,0.85)" : "rgba(190,188,255,0.64)";
      ctx.fill();
    }
  }
  function tick(now) {
    frame = 0;
    if (!visible() || !moving()) return;
    // Draw at most 30 Hz. Clamp elapsed time so resuming never jumps.
    if (!lastTime || now - lastTime >= 1000 / 30) {
      elapsed += lastTime ? Math.min(now - lastTime, 50) : 0;
      lastTime = now;
      draw();
    }
    frame = requestAnimationFrame(tick);
  }
  function sync() {
    cancelAnimationFrame(frame);
    frame = 0;
    lastTime = 0;
    if (!visible()) return;
    draw();
    if (moving()) frame = requestAnimationFrame(tick);
  }
  function resize() {
    const rect = canvas.getBoundingClientRect();
    width = rect.width; height = rect.height;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    sync();
  }
  if ("ResizeObserver" in window) new ResizeObserver(resize).observe(canvas);
  else window.addEventListener("resize", resize);
  if ("IntersectionObserver" in window) new IntersectionObserver(entries => {
    inView = entries[0].isIntersecting;
    sync();
  }).observe(canvas);
  document.addEventListener("visibilitychange", sync);
  document.addEventListener("thoughtpins:motionchange", sync);
  reduced.addEventListener("change", sync);
  window.addEventListener("pagehide", () => { pageActive = false; sync(); });
  window.addEventListener("pageshow", () => { pageActive = true; sync(); });
  resize();
})();
