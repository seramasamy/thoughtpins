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
  let seed = 731;
  const random = () => ((seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0) / 4294967296);
  const nodes = Array.from({ length: 112 }, (_, i) => ({
    // Seeded positions preserve the original scattered constellation on resize.
    x: 0.02 + random() * 0.96, y: 0.04 + random() * 0.92,
    phase: random() * Math.PI * 2, depth: 0.45 + random() * 0.55,
    warm: i % 4 === 0, hub: i % 9 === 0,
  }));
  let active = [], links = [];
  function connect() {
    active = nodes.slice(0, width < 600 ? 64 : 112);
    const distance = (a, b) => Math.hypot((a.x - b.x) * width, (a.y - b.y) * height);
    const pairs = new Map();
    const add = (a, b) => pairs.set(`${Math.min(a, b)}:${Math.max(a, b)}`, { a, b });
    // A spanning tree keeps every memory connected; nearby links add structure.
    // Build only on resize, not on every animation frame.
    const joined = new Set([0]);
    const nearest = active.map((node, i) => ({ from: 0, to: i, length: distance(active[0], node) }));
    while (joined.size < active.length) {
      const next = nearest.filter(edge => !joined.has(edge.to)).reduce((a, b) => a.length < b.length ? a : b);
      add(next.from, next.to);
      joined.add(next.to);
      active.forEach((node, i) => {
        const length = distance(active[next.to], node);
        if (length < nearest[i].length) nearest[i] = { from: next.to, to: i, length };
      });
    }
    active.forEach((node, i) => {
      active.map((other, j) => ({ j, length: distance(node, other) }))
        .filter(other => other.j !== i).sort((a, b) => a.length - b.length).slice(0, 2)
        .forEach(other => add(i, other.j));
    });
    links = [...pairs.values()];
  }
  function draw() {
    ctx.clearRect(0, 0, width, height);
    const time = elapsed / 1000;
    const points = active.map(node => ({ ...node,
      x: node.x * width + Math.sin(time * 0.3 + node.phase) * 22 * node.depth,
      y: node.y * height + Math.cos(time * 0.24 + node.phase) * 26 * node.depth }));
    const cool = "180,174,255", warm = "244,180,147";
    // Faint long connections give the closer mesh a second, deeper layer.
    const hubs = points.filter(point => point.hub);
    ctx.lineWidth = 0.65;
    hubs.forEach((a, i) => {
      const b = hubs[(i + 1) % hubs.length];
      ctx.strokeStyle = `rgba(${warm},0.075)`;
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    });
    ctx.lineWidth = 0.8;
    links.forEach((link, i) => {
      const a = points[link.a], b = points[link.b];
      const color = a.warm || b.warm ? warm : cool;
      ctx.strokeStyle = `rgba(${color},${0.14 + 0.12 * Math.min(a.depth, b.depth)})`;
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      if (i % 23 === 0) {
        const progress = (time * 0.09 + i * 0.137) % 1;
        ctx.fillStyle = `rgba(${color},${Math.sin(progress * Math.PI) ** 2 * 0.85})`;
        ctx.beginPath(); ctx.arc(a.x + (b.x - a.x) * progress, a.y + (b.y - a.y) * progress, 1.8, 0, Math.PI * 2); ctx.fill();
      }
    });
    points.forEach(point => {
      const color = point.warm || point.hub ? warm : cool;
      const glow = ctx.createRadialGradient(point.x, point.y, 0, point.x, point.y, point.hub ? 18 : 8);
      glow.addColorStop(0, `rgba(${color},${point.hub ? 0.28 : 0.13})`);
      glow.addColorStop(1, `rgba(${color},0)`);
      ctx.fillStyle = glow;
      ctx.beginPath(); ctx.arc(point.x, point.y, point.hub ? 18 : 8, 0, Math.PI * 2); ctx.fill();
      if (point.hub) {
        ctx.strokeStyle = `rgba(${color},0.35)`;
        ctx.beginPath(); ctx.arc(point.x, point.y, 6.5, 0, Math.PI * 2); ctx.stroke();
      }
      ctx.fillStyle = `rgba(${color},${0.65 + 0.2 * Math.sin(time * 0.55 + point.phase)})`;
      ctx.beginPath(); ctx.arc(point.x, point.y, point.hub ? 2.6 : 1 + point.depth, 0, Math.PI * 2); ctx.fill();
    });
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
    connect();
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
