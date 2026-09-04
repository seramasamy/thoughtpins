/* Thought Pins labs — "the night journal" concept
   Vanilla JS only. Motions: constellation-that-becomes-the-mark (scroll),
   line-mask reveals, horizontal week scrubber, clip-path product reveal.
   Everything degrades to a static, finished page under reduced motion. */

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

/* ---------------- Line-mask reveals ---------------- */
function setupLineReveals() {
  const lines = Array.from(document.querySelectorAll("[data-reveal-line]"));
  if (!lines.length) return;
  if (reduceMotion.matches || !("IntersectionObserver" in window)) {
    lines.forEach((line) => line.classList.add("lab-in"));
    return;
  }
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const group = Array.from(entry.target.parentElement.querySelectorAll(":scope > [data-reveal-line]"));
        const index = Math.max(0, group.indexOf(entry.target));
        entry.target.style.transitionDelay = `${Math.min(index * 110, 440)}ms`;
        entry.target.classList.add("lab-in");
        observer.unobserve(entry.target);
      }
    },
    { threshold: 0.3 }
  );
  lines.forEach((line) => observer.observe(line));
}

/* ---------------- Constellation that becomes the mark ---------------- */
async function setupConstellation() {
  const canvas = document.querySelector("[data-constellation]");
  const wrap = document.querySelector("[data-hero-wrap]");
  const copy = document.querySelector(".lab-hero-copy");
  const hint = document.querySelector(".lab-scroll-hint");
  if (!canvas || !wrap || typeof canvas.getContext !== "function") return;

  const ctx = canvas.getContext("2d");
  const rand = (min, max) => min + Math.random() * (max - min);
  const clamp01 = (v) => Math.max(0, Math.min(1, v));
  const ease = (v) => 1 - Math.pow(1 - clamp01(v), 3);

  // Sample points along the canonical mark's paths so the constellation
  // literally forms the shipping logo.
  async function sampleLogoPoints() {
    try {
      const response = await fetch("/assets/thought-pins-mark.svg");
      const text = await response.text();
      const doc = new DOMParser().parseFromString(text, "image/svg+xml");
      const svg = doc.querySelector("svg");
      if (!svg) return fallbackPoints();
      const holder = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      holder.setAttribute("viewBox", "0 0 128 128");
      holder.style.cssText = "position:absolute;width:0;height:0;overflow:hidden;";
      document.body.appendChild(holder);
      const segments = [];
      const paths = Array.from(doc.querySelectorAll("path"));
      // The mark wraps its paths in <g transform="translate(8.96 4.88) scale(.86)">
      const apply = (x, y) => ({ x: 8.96 + 0.86 * x, y: 4.88 + 0.86 * y });
      paths.forEach((source, pathIndex) => {
        const d = source.getAttribute("d");
        if (!d) return;
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", d);
        holder.appendChild(path);
        const total = path.getTotalLength();
        const count = pathIndex === 0 ? 72 : 9; // pin outline + brain strokes
        const segment = [];
        for (let i = 0; i < count; i += 1) {
          const pt = path.getPointAtLength((total * i) / count);
          segment.push(apply(pt.x, pt.y));
        }
        segments.push({ points: segment, closed: pathIndex === 0 });
      });
      holder.remove();
      return segments.length ? segments : fallbackPoints();
    } catch {
      return fallbackPoints();
    }
  }

  function fallbackPoints() {
    // Coarse pin outline if the fetch fails (120x120 box coordinates).
    const pts = [];
    for (let i = 0; i < 72; i += 1) {
      const a = (Math.PI * 2 * i) / 72;
      const pinch = Math.max(0, Math.sin(a - Math.PI / 2)) ** 2;
      pts.push({
        x: 64 + Math.cos(a) * 34 * (1 - pinch * 0.6),
        y: 56 + Math.sin(a) * 34 + pinch * 48,
      });
    }
    return [{ points: pts, closed: true }];
  }

  const logoSegments = await sampleLogoPoints();

  let width = 0;
  let height = 0;
  let dpr = 1;
  let motes = [];
  let tracePairs = [];
  let raf = 0;
  let inView = true;

  function layout() {
    const rect = canvas.getBoundingClientRect();
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = rect.width;
    height = rect.height;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // Sized off the short edge so the mark never overflows sideways. On a
    // landscape desktop the short edge is the height and 0.46 reads as a
    // centrepiece; on a portrait phone it is the *width*, which put a ~200px
    // mark in the middle of a 950px-tall screen — the hero looked empty, and
    // the long scroll runway made you sit in that emptiness. The narrow case
    // gets a bigger share of its short edge to land at a comparable weight.
    // 760 matches the `max-width: 760px` breakpoint that shortens the hero
    // runway in labs.css. Keep the two the same: at 730px they disagreed, so
    // that band got the short runway without the larger mark — the one width
    // where the fix made things slightly worse.
    const shortEdge = Math.min(width, height);
    const scale = (shortEdge * (width <= 760 ? 0.66 : 0.46)) / 128;
    const cx = width / 2;
    const cy = height / 2;
    motes = [];
    tracePairs = [];
    logoSegments.forEach((segment, segmentIndex) => {
      const startIndex = motes.length;
      segment.points.forEach((p, pointIndex) => {
        motes.push({
          segment: segmentIndex,
          order: pointIndex,
          tx: cx + (p.x - 64) * scale,
          ty: cy + (p.y - 64) * scale,
          sx: rand(0, width),
          sy: rand(0, height),
          phase: rand(0, Math.PI * 2),
          twinkle: rand(0.5, 1.4),
          r: pointIndex % 9 === 0 ? rand(1.8, 2.6) : rand(0.9, 1.7),
          warm: Math.random() < 0.24,
        });
      });
      for (let k = 0; k < segment.points.length - 1; k += 1) {
        tracePairs.push([startIndex + k, startIndex + k + 1]);
      }
      if (segment.closed && segment.points.length > 2) {
        tracePairs.push([startIndex + segment.points.length - 1, startIndex]);
      }
    });
  }

  function progress() {
    const runway = wrap.offsetHeight - window.innerHeight;
    return runway > 0 ? clamp01(window.scrollY / runway) : 1;
  }

  function draw(now) {
    raf = 0;
    if (!inView || document.hidden) return;
    const t = now / 1000;
    const p = reduceMotion.matches ? 1 : ease(progress());
    const scatterWeight = 1 - p;
    ctx.clearRect(0, 0, width, height);

    const pts = motes.map((m) => {
      const wobble = scatterWeight * 14;
      const x = m.sx + (m.tx - m.sx) * p + Math.sin(t * m.twinkle + m.phase) * wobble;
      const y = m.sy + (m.ty - m.sy) * p + Math.cos(t * m.twinkle * 0.8 + m.phase) * wobble - scatterWeight * 12 * Math.sin(t * 0.3 + m.phase);
      return { x, y, m };
    });

    // Sparse distance-based mesh — strong while scattered, recedes as the
    // mark forms so the traced silhouette can read.
    const linkDistance = Math.min(120, Math.max(64, width * 0.07));
    ctx.globalCompositeOperation = "lighter";
    ctx.lineWidth = 0.8;
    const meshAlpha = (1 - p) * 0.16 + 0.02;
    for (let i = 0; i < pts.length; i += 1) {
      for (let j = i + 1; j < pts.length; j += 1) {
        const dx = pts[i].x - pts[j].x;
        const dy = pts[i].y - pts[j].y;
        const d2 = dx * dx + dy * dy;
        if (d2 > linkDistance * linkDistance) continue;
        const closeness = 1 - Math.sqrt(d2) / linkDistance;
        const alpha = closeness * meshAlpha;
        if (alpha < 0.01) continue;
        ctx.strokeStyle = `rgba(244, 180, 147, ${alpha.toFixed(3)})`;
        ctx.beginPath();
        ctx.moveTo(pts[i].x, pts[i].y);
        ctx.lineTo(pts[j].x, pts[j].y);
        ctx.stroke();
      }
    }

    // Path tracing: connect consecutive sample points along each mark path.
    // This is what turns the constellation INTO the logo as p approaches 1.
    const traceAlpha = 0.04 + 0.34 * p;
    ctx.lineWidth = 1;
    for (const [ia, ib] of tracePairs) {
      ctx.strokeStyle = `rgba(244, 180, 147, ${traceAlpha.toFixed(3)})`;
      ctx.beginPath();
      ctx.moveTo(pts[ia].x, pts[ia].y);
      ctx.lineTo(pts[ib].x, pts[ib].y);
      ctx.stroke();
    }
    ctx.globalCompositeOperation = "source-over";

    // Motes
    for (const { x, y, m } of pts) {
      const twinkle = 0.65 + 0.35 * Math.sin(t * m.twinkle + m.phase);
      const alpha = (0.28 + 0.62 * p) * twinkle;
      ctx.beginPath();
      ctx.arc(x, y, m.r, 0, Math.PI * 2);
      ctx.fillStyle = m.warm
        ? `rgba(232, 97, 43, ${Math.min(1, alpha + 0.12).toFixed(3)})`
        : `rgba(244, 214, 194, ${alpha.toFixed(3)})`;
      ctx.fill();
    }

    // Copy yields the stage as the mark forms
    if (copy) copy.style.opacity = String(1 - clamp01((p - 0.5) / 0.32));
    if (hint) hint.style.opacity = String(1 - clamp01(p / 0.12));

    if (!reduceMotion.matches) raf = window.requestAnimationFrame(draw);
  }

  function play() {
    if (!raf && !reduceMotion.matches) raf = window.requestAnimationFrame(draw);
    else if (reduceMotion.matches) draw(performance.now());
  }

  layout();
  play();

  window.addEventListener("resize", () => {
    layout();
    play();
  });
  window.addEventListener("scroll", play, { passive: true });
  document.addEventListener("visibilitychange", play);
  new IntersectionObserver((entries) => {
    inView = entries[0]?.isIntersecting ?? true;
    play();
  }).observe(wrap);
  if (reduceMotion.addEventListener) reduceMotion.addEventListener("change", play);
}

/* ---------------- Week horizontal scrubber ----------------
   Two ways to move the same strip. With a cursor it is scrubbed by page
   scroll against a tall runway, which reads as film. With a thumb the CSS
   turns it into a snap carousel, and driving a transform on top of that would
   fight the finger — so here we only follow the track and report where it is.
   The progress bar is filled either way. */
function setupWeekScrub() {
  const wrap = document.querySelector("[data-week-wrap]");
  const track = document.querySelector("[data-week-track]");
  const bar = document.querySelector("[data-week-progress]");
  if (!wrap || !track) return;
  if (reduceMotion.matches) return;

  const swipeable = window.matchMedia("(max-width: 760px)");
  let raf = 0;

  function update() {
    raf = 0;
    if (swipeable.matches) {
      // The carousel owns its own position; read it, never set it.
      track.style.transform = "";
      const travel = track.scrollWidth - track.clientWidth;
      const p = travel > 0 ? Math.max(0, Math.min(1, track.scrollLeft / travel)) : 0;
      if (bar) bar.style.width = `${Math.max(p * 100, 4).toFixed(2)}%`;
      return;
    }
    const rect = wrap.getBoundingClientRect();
    const runway = wrap.offsetHeight - window.innerHeight;
    const p = runway > 0 ? Math.max(0, Math.min(1, -rect.top / runway)) : 0;
    const overflow = track.scrollWidth - track.parentElement.clientWidth;
    track.style.transform = `translate3d(${(-p * Math.max(0, overflow)).toFixed(1)}px, 0, 0)`;
    if (bar) bar.style.width = `${(p * 100).toFixed(2)}%`;
  }

  function onScroll() {
    if (!raf) raf = window.requestAnimationFrame(update);
  }

  update();
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);
  track.addEventListener("scroll", onScroll, { passive: true });
  swipeable.addEventListener("change", update);
}

/* ---------------- Marquee: duplicate content for a seamless loop ---------------- */
function setupMarquee() {
  const track = document.querySelector("[data-marquee-track]");
  if (!track) return;
  track.innerHTML += track.innerHTML;
}

/* ---------------- Nav fade near footer: avoid duplicate nav on screen ---------------- */
function setupNavFade() {
  const nav = document.querySelector(".lab-nav");
  const footer = document.querySelector(".lab-footer");
  if (!nav || !footer || !("IntersectionObserver" in window)) return;
  const observer = new IntersectionObserver(
    (entries) => {
      nav.classList.toggle("lab-nav-faded", entries[0].isIntersecting);
    },
    { threshold: 0 }
  );
  observer.observe(footer);
}

/* ---------------- Product clip reveal ---------------- */
function setupShotReveal() {
  const shot = document.querySelector("[data-shot]");
  if (!shot || !("IntersectionObserver" in window)) return;
  const observer = new IntersectionObserver(
    (entries) => {
      if (!entries[0].isIntersecting) return;
      shot.classList.add("lab-in");
      observer.disconnect();
    },
    { threshold: 0.32 }
  );
  observer.observe(shot);
}

setupLineReveals();
setupMarquee();
setupWeekScrub();
setupShotReveal();
setupNavFade();
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", setupConstellation);
} else {
  setupConstellation();
}
