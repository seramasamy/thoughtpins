import { sampleConstellationMark } from "/assets/constellation-shape.js?v=20260912-scroll-logo-1";

/* Original floating memory field and scroll-to-logo sequence from backup a67bbdf.
   One frame when paused; no frame loop while hidden or outside the viewport. */
(() => {
  const canvas = document.querySelector("[data-constellation]");
  const wrap = document.querySelector("[data-hero-wrap]");
  const copy = wrap?.querySelector(".lab-hero-copy");
  const hint = wrap?.querySelector(".lab-scroll-hint");
  if (!canvas || !wrap) return;
  let ctx;
  try { ctx = canvas.getContext("2d"); } catch { return; }
  if (!ctx) return;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const shape = sampleConstellationMark();
  let width = 0, height = 0, frame = 0, elapsed = 0, lastTime = null;
  let inView = true;
  let pageActive = true;
  const moving = () => !reduced.matches && document.documentElement.dataset.motionPaused === "false";
  const visible = () => inView && !document.hidden && pageActive;
  const clamp = value => Math.max(0, Math.min(1, value));
  function progress() {
    if (wrap.dataset.constellationMorph !== "ready") return 0;
    // Preserve visible keyboard focus while the introduction yields the stage.
    if (copy?.contains(document.activeElement) && document.activeElement.matches(":focus-visible")) return 0;
    const runway = wrap.offsetHeight - height;
    const fraction = runway > 0 ? clamp(-wrap.getBoundingClientRect().top / runway) : 0;
    return 1 - Math.pow(1 - fraction, 3);
  }
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
    const p = progress();
    const scatter = 1 - p;
    const scale = Math.min(width, height) * (width <= 760 ? 0.66 : 0.46) / 128;
    // Restore the backup's independent floating speeds, 14px wobble and
    // additional 12px vertical drift. Positions scale without reshuffling.
    const points = motes.map((m, i) => ({
      x: m.sx * width + (width / 2 + ((shape?.[i].x ?? 64) - 64) * scale - m.sx * width) * p
        + Math.sin(t * m.twinkle + m.phase) * 14 * scatter,
      y: m.sy * height + (height / 2 + ((shape?.[i].y ?? 64) - 64) * scale - m.sy * height) * p
        + Math.cos(t * m.twinkle * 0.8 + m.phase) * 14 * scatter
        - 12 * Math.sin(t * 0.3 + m.phase) * scatter,
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
        const alpha = (1 - Math.sqrt(distanceSquared) / linkDistance) * (scatter * 0.16 + 0.02);
        if (alpha < 0.01) continue;
        ctx.strokeStyle = `rgba(244,180,147,${alpha.toFixed(3)})`;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      }
    }
    // Restore the long, fine strands between consecutive original samples.
    ctx.lineWidth = 1;
    ctx.strokeStyle = `rgba(244,180,147,${(0.04 + 0.34 * p).toFixed(3)})`;
    for (const [a, b] of tracePairs) {
      ctx.beginPath(); ctx.moveTo(points[a].x, points[a].y);
      ctx.lineTo(points[b].x, points[b].y); ctx.stroke();
    }
    ctx.globalCompositeOperation = "source-over";
    for (const { x, y, m } of points) {
      const alpha = (0.28 + 0.62 * p) * (0.65 + 0.35 * Math.sin(t * m.twinkle + m.phase));
      ctx.fillStyle = m.warm
        ? `rgba(232,97,43,${Math.min(1, alpha + 0.12).toFixed(3)})`
        : `rgba(244,214,194,${alpha.toFixed(3)})`;
      ctx.beginPath(); ctx.arc(x, y, m.r, 0, Math.PI * 2); ctx.fill();
    }
    if (copy) {
      const opacity = String(1 - clamp((p - 0.5) / 0.32));
      if (copy.style.opacity !== opacity) copy.style.opacity = opacity;
      const hidden = opacity === "0";
      if (copy.inert !== hidden) copy.inert = hidden;
    }
    if (hint) hint.style.opacity = String(1 - clamp(p / 0.12));
  }
  function tick(now) {
    frame = 0;
    if (!visible()) return;
    // Use the original display-synchronized cadence, rather than a 30Hz
    // throttle. The elapsed clock pauses with the page and never jumps back in.
    elapsed += !moving() || lastTime === null ? 0 : Math.min(now - lastTime, 50);
    lastTime = moving() ? now : null;
    draw();
    if (moving()) frame = requestAnimationFrame(tick);
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
    // Short windows and large text retain the normal flow instead of clipping
    // the introduction inside a pinned viewport. A paused clock still permits
    // the scroll-controlled assembly; system Reduce Motion disables both.
    const fits = window.innerHeight >= 600 && (!copy || copy.offsetHeight + 180 <= window.innerHeight);
    wrap.dataset.constellationMorph = shape && fits && !reduced.matches &&
      document.documentElement.hasAttribute("data-motion-paused") ? "ready" : "static";
    const rect = canvas.getBoundingClientRect();
    width = rect.width; height = rect.height;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    sync();
  }
  if ("ResizeObserver" in window) new ResizeObserver(resize).observe(canvas);
  if (copy && "ResizeObserver" in window) new ResizeObserver(resize).observe(copy);
  window.addEventListener("resize", resize);
  const requestDraw = () => { if (!frame && visible()) frame = requestAnimationFrame(tick); };
  window.addEventListener("scroll", requestDraw, { passive: true });
  copy?.addEventListener("focusin", requestDraw);
  copy?.addEventListener("focusout", requestDraw);
  if ("IntersectionObserver" in window) new IntersectionObserver(entries => {
    inView = entries[0].isIntersecting;
    sync();
  }).observe(canvas);
  document.addEventListener("visibilitychange", sync);
  document.addEventListener("thoughtpins:motionchange", resize);
  reduced.addEventListener("change", resize);
  window.addEventListener("pagehide", () => { pageActive = false; sync(); });
  window.addEventListener("pageshow", () => { pageActive = true; sync(); });
  resize();
})();
