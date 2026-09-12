/* Modern homepage: progressive reveals and native example scrolling. */
(() => {
  const root = document.documentElement;

  // Without JS, an observer, or motion, every heading and action stays visible.
  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(entries => {
      for (const { target, isIntersecting } of entries) {
        if (!isIntersecting) continue;
        target.classList.add("lab-in");
        observer.unobserve(target);
      }
    }, { threshold: 0.1 });
    document.querySelectorAll("[data-reveal-line]").forEach(line => {
      line.classList.add("lab-reveal-ready");
      observer.observe(line);
    });
  }

  // Equal groups include their trailing gap so the loop joins without a jump.
  const marquee = document.querySelector("[data-marquee-track]");
  if (marquee) {
    const group = document.createElement("div");
    group.className = "lab-marquee-group";
    group.append(...marquee.childNodes);
    marquee.append(group, group.cloneNode(true));
    marquee.dataset.loopReady = "true";
    let inView = true;
    const syncMarquee = () => { marquee.style.animationPlayState = document.hidden || !inView ? "paused" : ""; };
    document.addEventListener("visibilitychange", syncMarquee);
    if ("IntersectionObserver" in window) new IntersectionObserver(entries => {
      inView = entries[0].isIntersecting;
      syncMarquee();
    }).observe(marquee.parentElement);
    syncMarquee();
  }

  const track = document.querySelector("[data-week-track]");
  const controls = document.querySelector("[data-example-controls]");
  if (!track || !controls) return;
  const cards = Array.from(track.children);
  const previous = controls.querySelector("[data-example-prev]");
  const next = controls.querySelector("[data-example-next]");
  const position = controls.querySelector("[data-example-position]");
  const progress = controls.querySelector("[data-week-progress]");
  let index = 0;
  let frame = 0;
  const offsets = () => cards.map(card => card.offsetLeft - cards[0].offsetLeft);
  function syncExamples() {
    frame = 0;
    const travel = Math.max(0, track.scrollWidth - track.clientWidth);
    const left = Math.max(0, track.scrollLeft);
    const atEnd = left >= travel - 2;
    index = atEnd && travel > 0 ? cards.length - 1 : offsets().reduce((best, offset, i, all) =>
      Math.abs(offset - left) < Math.abs(all[best] - left) ? i : best, 0);
    previous.disabled = left <= 2;
    next.disabled = atEnd;
    position.textContent = `${index + 1} / ${cards.length}`;
    progress.style.width = `${travel ? Math.max(4, Math.min(100, left / travel * 100)) : 100}%`;
  }
  function move(left) {
    track.scrollTo({ left,
      behavior: root.dataset.motionPaused !== "false" ? "instant" : "smooth" });
  }
  function step(direction) {
    const end = Math.max(0, track.scrollWidth - track.clientWidth);
    const stops = [...offsets().filter(offset => offset < end), end];
    // The last position is often a partial step when several cards fit.
    // Step from the actual scroll position so Previous always leaves the end.
    if (direction > 0) move(stops.find(offset => offset > track.scrollLeft + 2) ?? end);
    else move(stops.reverse().find(offset => offset < track.scrollLeft - 2) ?? 0);
  }
  previous.addEventListener("click", () => step(-1));
  next.addEventListener("click", () => step(1));
  track.addEventListener("keydown", event => {
    if (event.target !== track) return;
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    if (event.key === "Home") move(0);
    else if (event.key === "End") move(track.scrollWidth);
    else step(event.key === "ArrowLeft" ? -1 : 1);
  });
  const schedule = () => { if (!frame) frame = requestAnimationFrame(syncExamples); };
  track.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("resize", schedule);
  if ("ResizeObserver" in window) new ResizeObserver(schedule).observe(track);
  controls.hidden = false;
  syncExamples();
})();
