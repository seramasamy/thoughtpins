/* Original floating memory field, recovered from backup a67bbdf. No asset fetch.
   One frame when paused; no frame loop while hidden or outside the viewport. */
(() => {
  const canvas = document.querySelector("[data-constellation]");
  if (!canvas) return;
  let ctx;
  try { ctx = canvas.getContext("2d"); } catch { return; }
  if (!ctx) return;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  let width = 0, height = 0, frame = 0, elapsed = 0, lastTime = null;
  let inView = true;
  let pageActive = true;
  const moving = () => !reduced.matches && document.documentElement.dataset.motionPaused === "false";
  const visible = () => inView && !document.hidden && pageActive;
  // The original pre-redesign field: 72 outline samples and seven 9-point
  // brain strokes. Keep all 135 motes on phones as well as larger screens.
  const motes = [], tracePairs = [];
  for (const [segment, count] of [72, 9, 9, 9, 9, 9, 9, 9].entries()) {
    const start = motes.length;
    for (let i = 0; i < count; i++) {
      motes.push({
        sx: Math.random(), sy: Math.random(), phase: Math.random() * Math.PI * 2,
        twinkle: 0.5 + Math.random() * 0.9,
        r: i % 9 === 0 ? 1.8 + Math.random() * 0.8 : 0.9 + Math.random() * 0.8,
        warm: Math.random() < 0.24,
      });
      if (i) tracePairs.push([start + i - 1, start + i]);
    }
    if (segment === 0) tracePairs.push([start + count - 1, start]);
  }
  function draw() {
    ctx.clearRect(0, 0, width, height);
    const t = elapsed / 1000;
    // Restore the backup's independent floating speeds, 14px wobble and
    // additional 12px vertical drift. Positions scale without reshuffling.
    const points = motes.map(m => ({
      x: m.sx * width + Math.sin(t * m.twinkle + m.phase) * 14,
      y: m.sy * height + Math.cos(t * m.twinkle * 0.8 + m.phase) * 14
        - 12 * Math.sin(t * 0.3 + m.phase),
      m,
    }));
    const linkDistance = Math.min(120, Math.max(64, width * 0.07));
    ctx.globalCompositeOperation = "lighter";
    ctx.lineWidth = 0.8;
    // Neighbors reconnect as the nodes float, as in the original canvas.
    for (let i = 0; i < points.length; i++) {
      for (let j = i + 1; j < points.length; j++) {
        const a = points[i], b = points[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const distanceSquared = dx * dx + dy * dy;
        if (distanceSquared > linkDistance * linkDistance) continue;
        const alpha = (1 - Math.sqrt(distanceSquared) / linkDistance) * 0.18;
        if (alpha < 0.01) continue;
        ctx.strokeStyle = `rgba(244,180,147,${alpha.toFixed(3)})`;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      }
    }
    // Restore the long, fine strands between consecutive original samples.
    ctx.lineWidth = 1;
    ctx.strokeStyle = "rgba(244,180,147,0.040)";
    for (const [a, b] of tracePairs) {
      ctx.beginPath(); ctx.moveTo(points[a].x, points[a].y);
      ctx.lineTo(points[b].x, points[b].y); ctx.stroke();
    }
    ctx.globalCompositeOperation = "source-over";
    for (const { x, y, m } of points) {
      const alpha = 0.28 * (0.65 + 0.35 * Math.sin(t * m.twinkle + m.phase));
      ctx.fillStyle = m.warm
        ? `rgba(232,97,43,${Math.min(1, alpha + 0.12).toFixed(3)})`
        : `rgba(244,214,194,${alpha.toFixed(3)})`;
      ctx.beginPath(); ctx.arc(x, y, m.r, 0, Math.PI * 2); ctx.fill();
    }
  }
  function tick(now) {
    frame = 0;
    if (!visible() || !moving()) return;
    // Use the original display-synchronized cadence, rather than a 30Hz
    // throttle. The elapsed clock pauses with the page and never jumps back in.
    elapsed += lastTime === null ? 0 : Math.min(now - lastTime, 50);
    lastTime = now;
    draw();
    frame = requestAnimationFrame(tick);
  }
  function sync() {
    cancelAnimationFrame(frame);
    frame = 0;
    lastTime = null;
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
