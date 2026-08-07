// ------------------------------------------------------------------
// Theme: header toggle switching light <-> dark. With no stored choice
// the site follows the system (the inline head script only sets
// data-theme from storage; no attribute = prefers-color-scheme wins).
// Once the visitor chooses, the choice is stored and beats the system.
// ------------------------------------------------------------------
function setupTheme() {
  const KEY = "tp-theme";
  const root = document.documentElement;
  const buttons = Array.from(document.querySelectorAll("[data-theme-toggle]"));
  if (!buttons.length) return;
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

  const ICONS = {
    light: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.6v2.1M12 19.3v2.1M2.6 12h2.1M19.3 12h2.1M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19"/></svg>',
    dark: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20.3 14.1A8.4 8.4 0 1 1 9.9 3.7a7 7 0 1 0 10.4 10.4z"/></svg>',
  };

  function stored() {
    try {
      const value = window.localStorage.getItem(KEY);
      return value === "light" || value === "dark" ? value : null;
    } catch {
      return null;
    }
  }
  const effective = () => stored() || (systemDark.matches ? "dark" : "light");

  function render() {
    const mode = effective();
    for (const button of buttons) {
      button.innerHTML = ICONS[mode];
      const label = mode === "dark"
        ? "Theme: dark. Switch to light."
        : "Theme: light. Switch to dark.";
      button.setAttribute("aria-label", label);
      button.title = label;
      button.dataset.themeState = mode;
    }
  }

  function choose(mode) {
    root.dataset.theme = mode;
    try {
      window.localStorage.setItem(KEY, mode);
    } catch {
      // ignore storage failures; the toggle still works for this visit
    }
    render();
  }

  for (const button of buttons) {
    button.addEventListener("click", () => {
      choose(effective() === "dark" ? "light" : "dark");
    });
  }
  // An explicit legacy "auto" value clears itself; system changes only
  // matter while no choice is stored.
  if (stored() === null) {
    root.removeAttribute("data-theme");
    try { window.localStorage.removeItem(KEY); } catch { /* noop */ }
  }
  if (systemDark.addEventListener) systemDark.addEventListener("change", render);

  render();
}

setupTheme();

// The backend serves the web app at /app on whichever host it is reached
// through, so link to it on the current origin. Pointing at a fixed subdomain
// broke every sign-up and log-in link in production, because that subdomain was
// part of a planned multi-host layout that was never provisioned.
function appHref(mode) {
  const url = new URL("/app/", window.location.origin);
  if (mode) url.searchParams.set("auth", mode);
  return url.toString();
}

for (const link of document.querySelectorAll("[data-app-link]")) {
  link.href = appHref(link.dataset.appLink || "");
}

// Only a developer machine ever runs with auth turned off, so the "open test
// session" affordance is gated on the host rather than on the API's answer.
const isLocalHost = new Set(["127.0.0.1", "localhost", "[::1]"]).has(window.location.hostname);

async function configureLocalSession() {
  if (!isLocalHost) return;

  try {
    const response = await fetch("/v1/client-config", {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) return;
    const config = await response.json();
    if (config.auth_required !== false) return;

    const primary = document.querySelector("[data-primary-cta]");
    if (primary) {
      primary.textContent = "Open test session";
      primary.href = appHref("");
    }
    const note = document.querySelector("[data-test-session-note]");
    if (note) note.hidden = false;
    document.documentElement.dataset.testSession = "available";
  } catch {
    // The landing page remains usable while the API is starting or offline.
  }
}

void configureLocalSession();

// Rising memory-motes: soft warm points that drift upward and fade, evoking
// thoughts surfacing. Progressive enhancement only — the hero looks finished
// without it, and it stays still when the visitor prefers reduced motion.
function startHeroParticles() {
  const canvas = document.querySelector("[data-hero-particles]");
  if (!canvas || typeof canvas.getContext !== "function") return;

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const ctx = canvas.getContext("2d");
  let width = 0;
  let height = 0;
  let dpr = 1;
  let motes = [];
  let frame = 0;

  // Focus point: the visitor's pointer while it hovers the hero; otherwise a
  // slow "surge" drifting on a lissajous path so the field keeps forming and
  // dissolving constellations at idle. Motes and links near the focus glow.
  const pointer = { x: 0, y: 0, active: false };
  const hero = canvas.closest(".hero") || canvas;
  hero.addEventListener("pointermove", (event) => {
    const rect = canvas.getBoundingClientRect();
    pointer.x = event.clientX - rect.left;
    pointer.y = event.clientY - rect.top;
    pointer.active = true;
  });
  hero.addEventListener("pointerleave", () => {
    pointer.active = false;
  });

  function focusPoint(t) {
    if (pointer.active) return pointer;
    return {
      x: width * (0.5 + 0.38 * Math.sin(t * 0.11)),
      y: height * (0.46 + 0.3 * Math.sin(t * 0.073 + 1.7)),
      active: true,
    };
  }

  function clearanceAt(x, y) {
    const nx = Math.abs(x - width * 0.5) / (width * 0.34);
    const ny = Math.abs(y - height * 0.46) / (height * 0.32);
    return Math.min(1, Math.max(0, (Math.max(nx, ny) - 0.4) / 0.6));
  }

  const COLORS = ["232, 147, 108", "244, 214, 194", "217, 178, 148"];
  const rand = (min, max) => min + Math.random() * (max - min);

  function makeMote(seeded) {
    return {
      x: rand(0, width),
      y: seeded ? rand(0, height) : height + rand(4, 60),
      r: rand(0.9, 2.9),
      speed: rand(7, 22),
      drift: rand(-8, 8),
      phase: rand(0, Math.PI * 2),
      twinkle: rand(0.6, 1.6),
      base: rand(0.28, 0.72),
      color: COLORS[Math.floor(rand(0, COLORS.length))],
    };
  }

  /* Rebuilding the field puts every mote somewhere new, which reads as the
     whole background flinching. On a phone that is not rare: scrolling
     collapses the URL bar, the viewport height changes, and `resize` fires
     mid-scroll. So the canvas is always resized, but the field is only
     regenerated when the *width* changed enough to want a different density —
     which is a real layout change, not a scroll artefact. */
  let lastWidth = -1;

  function resize() {
    const rect = canvas.getBoundingClientRect();
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = rect.width;
    height = rect.height;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const target = Math.round(Math.min(58, Math.max(20, width / 21)));
    if (motes.length === target && Math.abs(width - lastWidth) < 24) return;
    lastWidth = width;
    motes = Array.from({ length: target }, () => makeMote(true));
  }

  let last = 0;
  function tick(now) {
    if (document.hidden) { frame = 0; return; }
    const staticField = reduceMotion.matches;
    const dt = staticField ? 0 : (last ? Math.min((now - last) / 1000, 0.05) : 0.016);
    last = now;
    const t = now / 1000;
    ctx.clearRect(0, 0, width, height);
    const focus = staticField ? { x: -9999, y: -9999, active: false } : focusPoint(t);
    const FOCUS_RADIUS = 150;

    // Advance each mote upward with a gentle sideways drift, and compute how
    // present it is (fades in from the bottom, out toward the top).
    for (const m of motes) {
      m.y -= m.speed * dt;
      m.x += Math.sin(t * m.twinkle + m.phase) * m.drift * dt;
      if (m.y < -14) Object.assign(m, makeMote(false));
      const lifeTop = Math.max(0, Math.min(1, (m.y / height) * 1.5));
      // Keep the field clear of the centered headline so nothing bright ever
      // sits behind the type; the motes stay vivid toward the edges.
      const clearance = clearanceAt(m.x, m.y);
      // Glow near the focus point; a live pointer also nudges motes aside.
      const fdx = m.x - focus.x;
      const fdy = m.y - focus.y;
      const fd = Math.hypot(fdx, fdy);
      const boost = focus.active ? Math.max(0, 1 - fd / FOCUS_RADIUS) * (0.25 + 0.75 * clearance) : 0;
      if (pointer.active && fd > 0.001 && fd < FOCUS_RADIUS) {
        const push = (1 - fd / FOCUS_RADIUS) * 16 * dt;
        m.x += (fdx / fd) * push * 60 * dt;
        m.y += (fdy / fd) * push * 60 * dt;
      }
      m.boost = boost;
      m.alpha = m.base * lifeTop * (0.72 + 0.28 * Math.sin(t * m.twinkle + m.phase)) * (0.1 + 0.9 * clearance);
      m.alpha = Math.min(1, m.alpha * (1 + boost * 1.1));
    }

    // Pulsing links between nearby motes — a living neural net / power grid
    // drifting upward. Additive blending gives the lines a faint glow where
    // they cross; a slow falloff lets connections reach farther dots so the
    // web reads clearly without crowding the type.
    const linkDistance = Math.min(210, Math.max(130, width * 0.17));
    const pulse = 0.5 + 0.5 * Math.sin(t * 0.5);
    ctx.globalCompositeOperation = "lighter";
    ctx.lineCap = "round";
    ctx.lineWidth = 0.9;
    for (let i = 0; i < motes.length; i++) {
      const a = motes[i];
      for (let j = i + 1; j < motes.length; j++) {
        const c = motes[j];
        const dx = a.x - c.x;
        const dy = a.y - c.y;
        const d2 = dx * dx + dy * dy;
        if (d2 > linkDistance * linkDistance) continue;
        const closeness = 1 - Math.sqrt(d2) / linkDistance;
        const midBoost = focus.active
          ? Math.max(0, 1 - Math.hypot((a.x + c.x) / 2 - focus.x, (a.y + c.y) / 2 - focus.y) / (FOCUS_RADIUS * 1.35))
          : 0;
        const alpha = Math.min(0.5,
          Math.pow(closeness, 1.35) * 0.24 * (0.72 + 0.28 * pulse) * Math.min(a.alpha + c.alpha, 1) * (1 + midBoost * 1.5));
        if (alpha < 0.004) continue;
        ctx.strokeStyle = `rgba(236, 158, 118, ${alpha.toFixed(3)})`;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(c.x, c.y);
        ctx.stroke();
      }
    }
    ctx.globalCompositeOperation = "source-over";

    // Glowing motes on top of the links.
    for (const m of motes) {
      if (m.alpha <= 0.003) continue;
      ctx.beginPath();
      ctx.arc(m.x, m.y, m.r, 0, Math.PI * 2);
      ctx.shadowColor = `rgba(${m.color}, ${Math.min(m.alpha * 1.15, 0.85).toFixed(3)})`;
      ctx.shadowBlur = 7;
      ctx.fillStyle = `rgba(${m.color}, ${m.alpha.toFixed(3)})`;
      ctx.fill();
    }
    ctx.shadowBlur = 0;

    frame = staticField ? 0 : window.requestAnimationFrame(tick);
  }

  function play() {
    if (frame) return;
    last = 0;
    frame = window.requestAnimationFrame(tick);
  }

  function pause() {
    if (!frame) return;
    window.cancelAnimationFrame(frame);
    frame = 0;
  }

  resize();
  play();
  window.addEventListener("resize", () => { resize(); play(); }, { passive: true });
  document.addEventListener("visibilitychange", () => { if (document.hidden) pause(); else play(); });
  if (reduceMotion.addEventListener) reduceMotion.addEventListener("change", play);

  /* Once the hero has scrolled away there is nothing to animate, and a canvas
     repainting sixty times a second behind the fold costs battery and competes
     with the scroll itself for main-thread time. */
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(
      (entries) => (entries[0].isIntersecting ? play() : pause()),
      { threshold: 0 }
    ).observe(canvas);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", startHeroParticles);
} else {
  startHeroParticles();
}

function setupProductPreview() {
  const root = document.querySelector("[data-product-demo]");
  if (!(root instanceof HTMLElement)) return;

  // The tabs sit in the section header on this page and inside the demo on the
  // classic page, so search the whole section rather than only the demo box.
  const scope = root.closest("section") || document;
  const tabs = Array.from(scope.querySelectorAll("[data-preview-tab]"));
  const panels = Array.from(root.querySelectorAll("[data-preview-panel]"));
  if (!tabs.length || !panels.length) return;

  // Tells the inline no-module fallback to stop syncing mode to viewport width,
  // so a resize cannot silently undo the device the visitor picked.
  root.dataset.previewControlled = "true";

  const setMode = (mode, moveFocus = false) => {
    root.dataset.previewMode = mode;
    tabs.forEach((tab) => {
      const active = tab.dataset.previewTab === mode;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
      if (active && moveFocus) tab.focus();
    });
    panels.forEach((panel) => {
      const active = panel.dataset.previewPanel === mode;
      panel.hidden = !active;
      panel.classList.toggle("is-active", active);
    });
    window.dispatchEvent(new CustomEvent("tp:preview-mode", { detail: mode }));
  };

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => setMode(tab.dataset.previewTab || "desktop"));
    tab.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const nextIndex = event.key === "Home"
        ? 0
        : event.key === "End"
          ? tabs.length - 1
          : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
      setMode(tabs[nextIndex].dataset.previewTab || "desktop", true);
    });
  });

  const prefersMobile = window.matchMedia("(max-width: 680px)").matches;
  setMode(prefersMobile ? "mobile" : "desktop");
}

setupProductPreview();

// ------------------------------------------------------------------
// Scroll reveal: sections rise once as they enter the viewport. JS opts
// in via html.js-reveal so no-JS and reduced-motion visitors simply see
// the finished page.
// ------------------------------------------------------------------
function setupScrollReveal() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (!("IntersectionObserver" in window)) return;
  const items = document.querySelectorAll(".reveal");
  if (!items.length) return;
  document.documentElement.classList.add("js-reveal");
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      }
    },
    { threshold: 0.12, rootMargin: "0px 0px -6% 0px" }
  );
  items.forEach((item) => observer.observe(item));
}

setupScrollReveal();

// ------------------------------------------------------------------
// Self-playing product demo: a scripted chat vignette inside the browser
// frame / phone shell. The static screenshot stays for no-JS, reduced
// motion, and print; the scene itself is aria-hidden decoration.
// ------------------------------------------------------------------
function setupDemoLive() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const scenes = Array.from(document.querySelectorAll("[data-demo-live]"));
  if (!scenes.length) return;

  const USER_TEXT = "What did I decide about the music festival?";

  function createScene(root) {
    const typed = root.querySelector("[data-dl-typed]");
    const userMsg = root.querySelector('[data-dl-step="user"]');
    const thinking = root.querySelector('[data-dl-step="thinking"]');
    const assistant = root.querySelector('[data-dl-step="assistant"]');
    const frame = root.closest(".browser-frame") || root.closest(".phone-screen");
    let timers = [];
    let running = false;

    const later = (fn, ms) => timers.push(window.setTimeout(fn, ms));
    const clear = () => {
      timers.forEach((id) => window.clearTimeout(id));
      timers = [];
    };

    function play() {
      if (!running) return;
      root.dataset.dlPhase = "reset";
      for (const el of [userMsg, thinking, assistant]) el.classList.remove("is-on");
      if (typed) typed.textContent = "";
      later(() => {
        root.dataset.dlPhase = "typing";
        userMsg.classList.add("is-on");
        let i = 0;
        const typeNext = () => {
          if (!running) return;
          if (typed) typed.textContent = USER_TEXT.slice(0, i + 1);
          i += 1;
          if (i < USER_TEXT.length) {
            later(typeNext, 22 + Math.random() * 30);
          } else {
            later(() => {
              root.dataset.dlPhase = "thinking";
              thinking.classList.add("is-on");
              later(() => {
                root.dataset.dlPhase = "answering";
                thinking.classList.remove("is-on");
                assistant.classList.add("is-on");
                later(() => {
                  root.dataset.dlPhase = "holding";
                  later(play, 3600);
                }, 650);
              }, 1150);
            }, 300);
          }
        };
        typeNext();
      }, 420);
    }

    return {
      start() {
        if (running) return;
        running = true;
        root.classList.add("is-live");
        if (frame) frame.classList.add("demo-running");
        play();
      },
      stop() {
        running = false;
        clear();
        root.classList.remove("is-live");
        if (frame) frame.classList.remove("demo-running");
      },
    };
  }

  const controllers = scenes.map((scene) => ({
    key: scene.dataset.demoLive,
    run: createScene(scene),
  }));

  function sync() {
    const demo = document.querySelector("[data-product-demo]");
    const visibleMode = demo ? demo.dataset.previewMode : null;
    for (const controller of controllers) {
      const sceneVisible = controller.key === visibleMode && !document.hidden;
      if (sceneVisible) controller.run.start();
      else controller.run.stop();
    }
  }

  window.addEventListener("tp:preview-mode", sync);
  document.addEventListener("visibilitychange", sync);
  sync();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", setupDemoLive);
} else {
  setupDemoLive();
}

// ------------------------------------------------------------------
// Magnetic primary CTA: a barely-there pull toward the pointer.
// ------------------------------------------------------------------
function setupMagneticCta() {
  if (!window.matchMedia("(pointer: fine)").matches) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const cta = document.querySelector("[data-primary-cta]");
  if (!(cta instanceof HTMLElement)) return;
  cta.addEventListener("pointermove", (event) => {
    const rect = cta.getBoundingClientRect();
    const dx = event.clientX - (rect.left + rect.width / 2);
    const dy = event.clientY - (rect.top + rect.height / 2);
    const tx = Math.max(-3, Math.min(3, dx * 0.08));
    const ty = Math.max(-2.5, Math.min(2.5, dy * 0.14 - 1));
    cta.style.transform = `translate(${tx.toFixed(1)}px, ${ty.toFixed(1)}px)`;
  });
  cta.addEventListener("pointerleave", () => {
    cta.style.transform = "";
  });
}

setupMagneticCta();
