/* Luminous homepage details: a scroll signal in the header, the section you
   are reading, cards that catch the pointer's light, headings that come into
   focus, and the product frame settling flat as it arrives. Everything here is
   decoration layered over a finished page: without this script, motion or an
   observer, every element is already visible and in place. */
(() => {
  const root = document.documentElement;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const finePointer = matchMedia("(pointer: fine)");
  const animated = () => !reduced.matches && root.dataset.motionPaused === "false";

  // Header: condense once the page moves and draw reading progress.
  const nav = document.querySelector(".lab-nav");
  const bar = document.querySelector("[data-scroll-progress]");
  const stage = document.querySelector(".showcase-stage");
  let scheduled = 0;
  function onScroll() {
    scheduled = 0;
    const max = Math.max(1, document.documentElement.scrollHeight - innerHeight);
    const fraction = Math.min(1, Math.max(0, scrollY / max));
    if (bar) bar.style.transform = `scaleX(${fraction.toFixed(4)})`;
    nav?.classList.toggle("is-scrolled", scrollY > 8);
    if (stage) tiltStage();
  }
  const schedule = () => { if (!scheduled) scheduled = requestAnimationFrame(onScroll); };
  addEventListener("scroll", schedule, { passive: true });
  addEventListener("resize", schedule, { passive: true });

  // The product frame arrives tilted back and settles flat as it scrolls in.
  function tiltStage() {
    if (!animated()) {
      stage.style.removeProperty("--lum-tilt");
      return;
    }
    const rect = stage.getBoundingClientRect();
    const arrival = Math.min(1, Math.max(0, (innerHeight - rect.top) / (innerHeight * 0.75)));
    stage.style.setProperty("--lum-tilt", (1 - arrival).toFixed(3));
  }

  // Name the section being read in the header.
  const links = new Map();
  document.querySelectorAll('.lab-nav-links a[href^="#"]').forEach(link => {
    const section = document.querySelector(link.getAttribute("href"));
    if (section) links.set(section, link);
  });
  if (links.size && "IntersectionObserver" in window) {
    const current = new Set();
    const spy = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (entry.isIntersecting) current.add(entry.target);
        else current.delete(entry.target);
      }
      const active = [...links.keys()].find(section => current.has(section));
      links.forEach((link, section) => link.classList.toggle("is-current", section === active));
    }, { rootMargin: "-45% 0px -50% 0px" });
    links.forEach((_, section) => spy.observe(section));
  }

  // Surfaces catch the pointer's light along their edge.
  const glowing = ".lab-card, .lab-keep-list > li, .showcase-story, .lum-lit";
  if (finePointer.matches) {
    addEventListener("pointermove", event => {
      const surface = event.target instanceof Element ? event.target.closest(glowing) : null;
      if (!surface) return;
      const rect = surface.getBoundingClientRect();
      surface.style.setProperty("--mx", `${(event.clientX - rect.left).toFixed(0)}px`);
      surface.style.setProperty("--my", `${(event.clientY - rect.top).toFixed(0)}px`);
    }, { passive: true });
  }

  // Section introductions and objects come into focus once, as they arrive.
  const focusables = document.querySelectorAll(
    ".lab-week-head, .showcase-heading, .lab-keep-head, .lab-card, .showcase-workspace, .showcase-story, .lab-keep-list > li, .lum-orbit"
  );
  if ("IntersectionObserver" in window && focusables.length) {
    const reveal = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        entry.target.classList.add("lum-in");
        reveal.unobserve(entry.target);
      }
    }, { threshold: 0.14, rootMargin: "0px 0px -6% 0px" });
    focusables.forEach((element, index) => {
      element.classList.add("lum-reveal");
      element.style.setProperty("--lum-order", String(index % 5));
      reveal.observe(element);
    });
    root.classList.add("lum-reveals");
  }

  document.addEventListener("thoughtpins:motionchange", schedule);
  reduced.addEventListener("change", schedule);
  onScroll();
})();
