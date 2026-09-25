import { useEffect } from "react";

/** Selectable surfaces whose lit edge follows the pointer (151-luminous-controls.css). */
const LIT_SURFACES = ".memory-card, .pin-card, .starter-list button, .source-row, .tool-card, .legal-row";

/**
 * Surfaces catch the pointer's light along their edge: one delegated listener
 * writes the pointer position into --mx/--my on the surface under it, at most
 * once per frame. Fine pointers only; touch never hovers, and without this the
 * edge simply stays lit from above.
 */
export function usePointerLight() {
  useEffect(() => {
    if (!window.matchMedia("(pointer: fine)").matches) return undefined;
    let frame = 0;
    let latest: PointerEvent | null = null;

    const paint = () => {
      frame = 0;
      const event = latest;
      latest = null;
      if (!event || !(event.target instanceof Element)) return;
      const surface = event.target.closest<HTMLElement>(LIT_SURFACES);
      if (!surface) return;
      const rect = surface.getBoundingClientRect();
      surface.style.setProperty("--mx", `${Math.round(event.clientX - rect.left)}px`);
      surface.style.setProperty("--my", `${Math.round(event.clientY - rect.top)}px`);
    };

    const track = (event: PointerEvent) => {
      latest = event;
      if (!frame) frame = window.requestAnimationFrame(paint);
    };

    window.addEventListener("pointermove", track, { passive: true });
    return () => {
      window.removeEventListener("pointermove", track);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, []);
}
