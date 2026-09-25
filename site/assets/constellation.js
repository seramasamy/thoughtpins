import { sampleConstellationMark } from "/assets/constellation-shape.js?v=20260925-luminous-3";

/* The floating memory field and its scroll-to-logo sequence.

   Recovered from backup a67bbdf: 135 motes on every screen, the original
   individual floating speeds, 14px wobble, 12px drift, neighbours that
   reconnect as they float, and the cubic gather onto the mark's eight paths.

   The luminous pass renders that field as a living network without moving
   anything the original placed: motes glow in three tones, recall signals
   travel between neighbours and light up whatever they reach, a deep dust
   layer gives the field depth, the pointer joins the network as one more
   node, a few memory pins float at the edges, and the formed mark ignites.
   Additions are drawn with sprites or plain strokes, so review hooks still
   see exactly one arc per mote and every formed node lands on the mark.
   One frame when paused; no frame loop while hidden or outside the viewport. */
(() => {
  const canvas = document.querySelector("[data-constellation]");
  const wrap = document.querySelector("[data-hero-wrap]");
  const copy = wrap?.querySelector(".lab-hero-copy");
  const hint = wrap?.querySelector(".lab-scroll-hint");
  const caption = wrap?.querySelector("[data-formed-caption]");
  const pins = wrap ? Array.from(wrap.querySelectorAll("[data-memory-pin]")) : [];
  if (!canvas || !wrap) return;
  let ctx;
  try { ctx = canvas.getContext("2d"); } catch { return; }
  if (!ctx) return;
  const root = document.documentElement;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const finePointer = matchMedia("(pointer: fine)");
  const shape = sampleConstellationMark();
  let width = 0, height = 0, frame = 0, elapsed = 0, lastTime = null;
  let inView = true;
  let pageActive = true;
  let pinsOn = false;
  const moving = () => !reduced.matches && root.dataset.motionPaused === "false";
  const visible = () => inView && !document.hidden && pageActive;
  const clamp = value => Math.max(0, Math.min(1, value));
  const lerp = (a, b, f) => a + (b - a) * f;
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
  const motes = [], tracePairs = [], strokes = [];
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
    strokes.push({ start, count });
  }
  // Tone derives from values already drawn (warm, phase), so the random
  // sequence, and with it every position, matches the original field.
  for (const m of motes) m.tone = m.warm ? 0 : m.phase < 1.45 ? 1 : 2;
  const count = motes.length;
  const px = new Float64Array(count), py = new Float64Array(count);
  const clear = new Float64Array(count), flash = new Float64Array(count).fill(-1e9);

  // Ember memories, violet connections, pale everyday motes.
  const TONES = [
    { core: "255,126,78", line: "246,150,112", glow: "255,104,52" },
    { core: "206,202,255", line: "164,158,255", glow: "140,130,255" },
    { core: "236,233,248", line: "208,210,238", glow: "190,198,255" },
  ];
  const sprites = TONES.map(tone => glowSprite(tone.glow, 64));
  const pearl = glowSprite("246,244,255", 32);
  const emberBloom = glowSprite("232,97,43", 256);
  const violetBloom = glowSprite("116,108,255", 256);
  const ring = ringSprite(256);
  function makeSprite(size, paint) {
    try {
      const sprite = document.createElement("canvas");
      sprite.width = sprite.height = size;
      const g = sprite.getContext("2d");
      if (!g) return null;
      paint(g, size / 2);
      return sprite;
    } catch {
      return null;
    }
  }
  function glowSprite(rgb, size) {
    return makeSprite(size, (g, half) => {
      const gradient = g.createRadialGradient(half, half, 0, half, half, half);
      gradient.addColorStop(0, `rgba(${rgb},0.95)`);
      gradient.addColorStop(0.14, `rgba(${rgb},0.52)`);
      gradient.addColorStop(0.4, `rgba(${rgb},0.15)`);
      gradient.addColorStop(1, `rgba(${rgb},0)`);
      g.fillStyle = gradient;
      g.fillRect(0, 0, half * 2, half * 2);
    });
  }
  function ringSprite(size) {
    return makeSprite(size, (g, half) => {
      const gradient = g.createRadialGradient(half, half, half * 0.8, half, half, half);
      gradient.addColorStop(0, "rgba(244,180,147,0)");
      gradient.addColorStop(0.5, "rgba(244,180,147,0.6)");
      gradient.addColorStop(1, "rgba(244,180,147,0)");
      g.fillStyle = gradient;
      g.fillRect(0, 0, half * 2, half * 2);
    });
  }
  function glow(sprite, x, y, size, alpha) {
    if (!sprite || alpha <= 0.004) return;
    ctx.globalAlpha = Math.min(1, alpha);
    ctx.drawImage(sprite, x - size / 2, y - size / 2, size, size);
  }

  // Deep dust: fine points on three depths that parallax with the pointer
  // and stream outward as the visitor scrolls into the mark.
  const dust = Array.from({ length: 150 }, () => ({
    x: Math.random(), y: Math.random(), z: 0.25 + Math.random() * 0.75,
    s: 0.5 + Math.random() * 0.9, phase: Math.random() * Math.PI * 2, speed: 0.4 + Math.random() * 0.9,
  }));

  // Recall signals: a light leaves one memory, travels to a neighbour and
  // wakes it; sometimes the neighbour passes it on.
  const sparks = [];
  let links = new Int16Array(4096), linkCount = 0, nextSpark = 900;
  function spawnSpark(a, b, depth) {
    if (sparks.length >= 22) return;
    const distance = Math.hypot(px[a] - px[b], py[a] - py[b]);
    sparks.push({ a, b, start: elapsed, duration: 420 + distance * 7, depth, tone: motes[a].tone === 2 ? 1 : motes[a].tone });
  }
  function neighbour(of, except) {
    const found = [];
    for (let k = 0; k < linkCount; k += 2) {
      if (links[k] === of && links[k + 1] !== except) found.push(links[k + 1]);
      else if (links[k + 1] === of && links[k] !== except) found.push(links[k]);
    }
    return found.length ? found[Math.floor(Math.random() * found.length)] : -1;
  }

  // The pointer becomes one more node: nearby memories lean toward it and
  // it draws its own faint connections.
  const pointer = { x: 0, y: 0, tx: 0, ty: 0, strength: 0, target: 0, seen: false };
  addEventListener("pointermove", event => {
    if (!finePointer.matches || event.pointerType === "touch") return;
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left, y = event.clientY - rect.top;
    const inside = x >= 0 && y >= 0 && x <= rect.width && y <= rect.height;
    pointer.target = inside ? 1 : 0;
    if (!inside) return;
    pointer.tx = x; pointer.ty = y;
    if (!pointer.seen) { pointer.x = x; pointer.y = y; pointer.seen = true; }
  }, { passive: true });
  document.addEventListener("pointerleave", () => { pointer.target = 0; });

  // A fully faded introduction becomes inert, but only once it has stayed
  // faded briefly: a keyboard user whose focus lands on the call to action
  // mid-scroll (Safari tabs to the example strip, which scrolls the page)
  // must still be able to reach it. Restoring is always immediate.
  let inertTimer = 0;
  function setInert(hidden) {
    if (!copy) return;
    if (!hidden) {
      clearTimeout(inertTimer);
      inertTimer = 0;
      if (copy.inert) copy.inert = false;
      return;
    }
    if (copy.inert || inertTimer) return;
    inertTimer = setTimeout(() => {
      inertTimer = 0;
      if (copy.style.opacity === "0") copy.inert = true;
    }, 300);
  }

  let formedLatch = false, ringStart = -1e9;
  function draw() {
    ctx.clearRect(0, 0, width, height);
    const t = elapsed / 1000;
    const p = progress();
    const scatter = 1 - p;
    const scale = Math.min(width, height) * (width <= 760 ? 0.66 : 0.46) / 128;
    const cx = width / 2, cy = height / 2;
    if (moving()) {
      pointer.x = lerp(pointer.x, pointer.tx, 0.14);
      pointer.y = lerp(pointer.y, pointer.ty, 0.14);
      pointer.strength = lerp(pointer.strength, pointer.target, 0.08);
    }
    const lean = pointer.strength * scatter;
    // Keep the headline clear: motes crossing behind the words dim while the
    // field is scattered, and regain full strength as they form the mark.
    const rx = Math.min(width * 0.36, 540), ry = Math.min(height * 0.3, 270);
    // Restore the backup's independent floating speeds, 14px wobble and
    // additional 12px vertical drift. Positions scale without reshuffling.
    for (let i = 0; i < count; i++) {
      const m = motes[i];
      let x = m.sx * width + (cx + ((shape?.[i].x ?? 64) - 64) * scale - m.sx * width) * p
        + Math.sin(t * m.twinkle + m.phase) * 14 * scatter;
      let y = m.sy * height + (cy + ((shape?.[i].y ?? 64) - 64) * scale - m.sy * height) * p
        + Math.cos(t * m.twinkle * 0.8 + m.phase) * 14 * scatter
        - 12 * Math.sin(t * 0.3 + m.phase) * scatter;
      if (lean > 0.002) {
        const dx = pointer.x - x, dy = pointer.y - y, d = Math.hypot(dx, dy);
        if (d > 1 && d < 230) {
          const pull = Math.pow(1 - d / 230, 2) * 20 * lean;
          x += dx / d * pull; y += dy / d * pull;
        }
      }
      px[i] = x; py[i] = y;
      const zone = Math.hypot((x - cx) / rx, (y - cy) / ry);
      clear[i] = 1 - (1 - clamp((zone - 0.5) / 0.65)) * 0.62 * scatter;
    }

    // Dust sits deepest, so it is drawn first.
    ctx.globalCompositeOperation = "lighter";
    const dustCount = width <= 760 ? 80 : dust.length;
    const warp = p * 0.6;
    const nx = pointer.strength * (pointer.x / Math.max(width, 1) - 0.5);
    const ny = pointer.strength * (pointer.y / Math.max(height, 1) - 0.5);
    for (let i = 0; i < dustCount; i++) {
      const d = dust[i];
      let x = d.x * width - nx * 26 * d.z;
      let y = ((d.y * height - t * 5 * d.z) % height + height) % height - ny * 20 * d.z;
      x = cx + (x - cx) * (1 + warp * d.z);
      y = cy + (y - cy) * (1 + warp * d.z);
      const alpha = (0.16 + 0.42 * d.z) * (0.55 + 0.45 * Math.sin(t * d.speed + d.phase)) * (1 - p * 0.35);
      const size = d.s * (0.6 + d.z * 0.9) * (1 + p * 0.6 * d.z);
      ctx.fillStyle = `rgba(196,204,255,${alpha.toFixed(3)})`;
      ctx.fillRect(x, y, size, size);
    }

    // The formed mark ignites: an ember bloom, a violet halo, and a ring the
    // moment the last node lands.
    const ignite = clamp((p - 0.6) / 0.4);
    const markSize = 128 * scale;
    if (ignite > 0) {
      const breathe = 0.9 + 0.1 * Math.sin(t * 1.3);
      glow(violetBloom, cx, cy, markSize * 2.5, 0.12 * ignite * breathe);
      glow(emberBloom, cx, cy + markSize * 0.02, markSize * 1.5, 0.34 * ignite * breathe);
    }
    if (p > 0.975 && !formedLatch) { formedLatch = true; ringStart = elapsed; }
    else if (p < 0.8) formedLatch = false;
    const ringAge = (elapsed - ringStart) / 1600;
    if (ringAge >= 0 && ringAge < 1) glow(ring, cx, cy, markSize * (1.05 + ringAge * 1.25), Math.pow(1 - ringAge, 2) * 0.5);

    const linkDistance = Math.min(120, Math.max(64, width * 0.07));
    ctx.lineWidth = 0.8;
    linkCount = 0;
    // Neighbors reconnect as the nodes float, as in the original canvas.
    for (let i = 0; i < count; i++) {
      for (let j = i + 1; j < count; j++) {
        const dx = px[i] - px[j], dy = py[i] - py[j];
        const distanceSquared = dx * dx + dy * dy;
        if (distanceSquared > linkDistance * linkDistance) continue;
        const alpha = (1 - Math.sqrt(distanceSquared) / linkDistance) * (scatter * 0.26 + 0.03) * Math.min(clear[i], clear[j]);
        if (alpha < 0.01) continue;
        if (linkCount < links.length) { links[linkCount++] = i; links[linkCount++] = j; }
        ctx.strokeStyle = `rgba(${TONES[Math.min(motes[i].tone, motes[j].tone)].line},${alpha.toFixed(3)})`;
        ctx.beginPath(); ctx.moveTo(px[i], py[i]); ctx.lineTo(px[j], py[j]); ctx.stroke();
      }
    }
    // Restore the long, fine strands between consecutive original samples;
    // as the mark forms they gain a soft neon halo.
    if (p > 0.3) {
      ctx.lineWidth = 4;
      ctx.strokeStyle = `rgba(255,120,70,${(0.16 * clamp((p - 0.3) / 0.7)).toFixed(3)})`;
      for (const [a, b] of tracePairs) {
        ctx.beginPath(); ctx.moveTo(px[a], py[a]);
        ctx.lineTo(px[b], py[b]); ctx.stroke();
      }
    }
    ctx.lineWidth = 1 + 0.35 * p;
    ctx.strokeStyle = `rgba(250,196,170,${(0.05 + 0.55 * p).toFixed(3)})`;
    for (const [a, b] of tracePairs) {
      ctx.beginPath(); ctx.moveTo(px[a], py[a]);
      ctx.lineTo(px[b], py[b]); ctx.stroke();
    }

    // The pointer's own connections.
    if (lean > 0.01) {
      const near = [];
      for (let i = 0; i < count; i++) {
        const d = Math.hypot(px[i] - pointer.x, py[i] - pointer.y);
        if (d < 210) near.push([d, i]);
      }
      near.sort((a, b) => a[0] - b[0]);
      ctx.lineWidth = 0.9;
      for (const [d, i] of near.slice(0, 4)) {
        ctx.strokeStyle = `rgba(196,192,255,${((1 - d / 210) * 0.5 * lean).toFixed(3)})`;
        ctx.beginPath(); ctx.moveTo(pointer.x, pointer.y); ctx.lineTo(px[i], py[i]); ctx.stroke();
        flash[i] = Math.max(flash[i], elapsed - 480);
      }
      glow(sprites[1], pointer.x, pointer.y, 34, 0.55 * lean);
      glow(pearl, pointer.x, pointer.y, 9, 0.9 * lean);
    }

    // Memory pins float at the edges, tethered to the nearest memory.
    const pinAlpha = pinsOn ? 1 - clamp(p / 0.3) : 0;
    for (let k = 0; k < pins.length; k++) {
      const pin = pins[k];
      if (!pinsOn) continue;
      const bx = Number(pin.dataset.x) * width, by = Number(pin.dataset.y) * height;
      const x = bx + Math.sin(t * 0.33 + k * 1.9) * 10 - nx * 34 + (bx - cx) * p * 0.35;
      const y = by + Math.cos(t * 0.27 + k * 1.3) * 8 - ny * 26;
      const transform = `translate3d(${x.toFixed(1)}px,${y.toFixed(1)}px,0) translate(-50%,-50%)`;
      if (pin.style.transform !== transform) pin.style.transform = transform;
      const opacity = pinAlpha.toFixed(3);
      if (pin.style.opacity !== opacity) pin.style.opacity = opacity;
      if (pinAlpha < 0.02) continue;
      let best = -1, bestDistance = 1e9;
      for (let i = 0; i < count; i++) {
        const d = Math.hypot(px[i] - x, py[i] - y);
        if (d > 90 && d < bestDistance) { best = i; bestDistance = d; }
      }
      if (best < 0 || bestDistance > 320) continue;
      ctx.lineWidth = 0.9;
      ctx.strokeStyle = `rgba(${pin.dataset.tone === "violet" ? TONES[1].line : TONES[0].line},${(0.3 * pinAlpha).toFixed(3)})`;
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(px[best], py[best]); ctx.stroke();
      flash[best] = Math.max(flash[best], elapsed - 420);
    }

    // Idle recall signals ride the current links while the field is loose.
    if (moving() && scatter > 0.35 && elapsed >= nextSpark && linkCount) {
      const k = Math.floor(Math.random() * (linkCount / 2)) * 2;
      if (Math.random() < 0.5) spawnSpark(links[k], links[k + 1], 0);
      else spawnSpark(links[k + 1], links[k], 0);
      nextSpark = elapsed + 240 + Math.random() * 420;
    }
    for (let s = sparks.length - 1; s >= 0; s--) {
      const spark = sparks[s];
      const f = (elapsed - spark.start) / spark.duration;
      if (f >= 1) {
        sparks.splice(s, 1);
        flash[spark.b] = elapsed;
        if (scatter > 0.35 && spark.depth < 4 && Math.random() < 0.62) {
          const next = neighbour(spark.b, spark.a);
          if (next >= 0) spawnSpark(spark.b, next, spark.depth + 1);
        }
        continue;
      }
      const eased = f < 0.5 ? 4 * f * f * f : 1 - Math.pow(-2 * f + 2, 3) / 2;
      const fade = scatter * Math.min(1, f * 6, (1 - f) * 8);
      for (let tail = 3; tail >= 0; tail--) {
        const g = Math.max(0, eased - tail * 0.045);
        const x = lerp(px[spark.a], px[spark.b], g), y = lerp(py[spark.a], py[spark.b], g);
        glow(sprites[spark.tone], x, y, 20 - tail * 3.5, (0.85 - tail * 0.2) * fade);
      }
      glow(pearl, lerp(px[spark.a], px[spark.b], eased), lerp(py[spark.a], py[spark.b], eased), 7, 0.95 * fade);
    }

    // As the mark forms, light circles the pin and travels each brain stroke.
    const run = clamp((p - 0.5) / 0.35);
    if (run > 0) {
      const outline = strokes[0];
      for (let k = 0; k < 3; k++) {
        const u = ((t * 0.075 + k / 3) % 1) * outline.count;
        const i0 = Math.floor(u) % outline.count, f = u - Math.floor(u);
        const a = outline.start + i0, b = outline.start + (i0 + 1) % outline.count;
        const x = lerp(px[a], px[b], f), y = lerp(py[a], py[b], f);
        glow(sprites[0], x, y, 26, 0.7 * run);
        glow(pearl, x, y, 8, 0.9 * run);
      }
      for (let s = 1; s < strokes.length; s++) {
        const { start, count: length } = strokes[s];
        const u = (t * 0.45 + s * 0.37) % 1.4;
        if (u > 1) continue;
        const position = u * (length - 1);
        const i0 = Math.min(length - 2, Math.floor(position)), f = position - i0;
        const x = lerp(px[start + i0], px[start + i0 + 1], f), y = lerp(py[start + i0], py[start + i0 + 1], f);
        const fade = Math.sin(u * Math.PI);
        glow(sprites[1], x, y, 22, 0.75 * run * fade);
        glow(pearl, x, y, 7, 0.9 * run * fade);
      }
    }

    // Glows under each mote; a recall flash swells briefly.
    for (let i = 0; i < count; i++) {
      const m = motes[i];
      const twinkle = 0.65 + 0.35 * Math.sin(t * m.twinkle + m.phase);
      const woken = clamp(1 - (elapsed - flash[i]) / 700);
      const size = m.r * (8 + 3 * p) * (1 + woken * 1.6);
      glow(sprites[m.tone], px[i], py[i], size, ((m.tone === 0 ? 0.62 : 0.4) * (0.3 + 0.7 * p) * twinkle + woken * 0.75) * clear[i]);
    }
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
    for (let i = 0; i < count; i++) {
      const m = motes[i];
      const woken = clamp(1 - (elapsed - flash[i]) / 700);
      const alpha = Math.min(1, ((0.3 + 0.66 * p) * (0.65 + 0.35 * Math.sin(t * m.twinkle + m.phase)) + woken * 0.5) * clear[i]
        + (m.tone === 0 ? 0.12 : 0));
      ctx.fillStyle = `rgba(${TONES[m.tone].core},${alpha.toFixed(3)})`;
      ctx.beginPath(); ctx.arc(px[i], py[i], m.r * (1 + 0.3 * p), 0, Math.PI * 2); ctx.fill();
    }

    if (copy) {
      const fade = clamp((p - 0.5) / 0.32);
      const opacity = String(1 - fade);
      if (copy.style.opacity !== opacity) copy.style.opacity = opacity;
      // The introduction dissolves into the field instead of simply fading.
      const soften = width > 760 && fade > 0.001;
      const filter = soften ? `blur(${(fade * 9).toFixed(2)}px)` : "";
      if (copy.style.filter !== filter) copy.style.filter = filter;
      const lift = fade > 0.001 ? `translateY(${(-fade * 26).toFixed(1)}px)` : "";
      if (copy.style.transform !== lift) copy.style.transform = lift;
      setInert(opacity === "0");
    }
    if (hint) hint.style.opacity = String(1 - clamp(p / 0.12));
    if (caption) {
      const shown = clamp((p - 0.84) / 0.14);
      const opacity = shown.toFixed(3);
      if (caption.style.opacity !== opacity) caption.style.opacity = opacity;
      const settle = `translate(-50%, ${((1 - shown) * 12).toFixed(1)}px)`;
      if (caption.style.transform !== settle) caption.style.transform = settle;
    }
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
      root.hasAttribute("data-motion-paused") ? "ready" : "static";
    // Restore semantics even offscreen, where sync deliberately skips drawing.
    if (wrap.dataset.constellationMorph === "static" && copy) {
      copy.style.opacity = "1";
      copy.style.filter = "";
      copy.style.transform = "";
      setInert(false);
    }
    const rect = canvas.getBoundingClientRect();
    width = rect.width; height = rect.height;
    // Memory pins need room beside the headline and the pinned sequence.
    pinsOn = pins.length > 0 && width >= 1100 && wrap.dataset.constellationMorph === "ready";
    wrap.dataset.memoryPins = pinsOn ? "on" : "off";
    if (caption) {
      const scale = Math.min(width, height) * (width <= 760 ? 0.66 : 0.46) / 128;
      caption.style.top = `${Math.round(height / 2 + 46 * scale + 26)}px`;
    }
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
