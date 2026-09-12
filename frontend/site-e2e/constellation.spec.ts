import { expect, test } from "@playwright/test";

type MotionReview = {
  points: number[][];
  edges: number[][];
  frames: number;
  advance: (time: number) => void;
};

declare global {
  interface Window { constellationReview: MotionReview }
}

for (const width of [390, 1440]) {
  test(`original floating density, pace and changing connections at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.addInitScript(() => {
      // Fixed initial positions and a display clock make displacement observable
      // without turning a slow CI machine into an animation-speed failure.
      let seed = 731, id = 0;
      Math.random = () => ((seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0) / 4294967296);
      const callbacks = new Map<number, FrameRequestCallback>();
      window.requestAnimationFrame = callback => { callbacks.set(++id, callback); return id; };
      window.cancelAnimationFrame = handle => { callbacks.delete(handle); };
      const review: MotionReview = {
        points: [], edges: [], frames: 0,
        advance(time) {
          const pending = [...callbacks.values()];
          callbacks.clear();
          pending.forEach(callback => callback(time));
        },
      };
      window.constellationReview = review;
      const prototype = CanvasRenderingContext2D.prototype;
      const clear = prototype.clearRect, arc = prototype.arc;
      const move = prototype.moveTo, line = prototype.lineTo, stroke = prototype.stroke;
      let start: number[] = [], end: number[] = [];
      prototype.clearRect = function (...args) {
        if (this.canvas.matches("[data-constellation]")) {
          review.points = []; review.edges = []; review.frames++;
        }
        return clear.apply(this, args);
      };
      prototype.arc = function (...args) {
        if (this.canvas.matches("[data-constellation]")) review.points.push([args[0], args[1]]);
        return arc.apply(this, args);
      };
      prototype.moveTo = function (...args) {
        if (this.canvas.matches("[data-constellation]")) start = args;
        return move.apply(this, args);
      };
      prototype.lineTo = function (...args) {
        if (this.canvas.matches("[data-constellation]")) end = args;
        return line.apply(this, args);
      };
      prototype.stroke = function (...args: [Path2D?]) {
        if (this.canvas.matches("[data-constellation]")) review.edges.push([...start, ...end]);
        return Reflect.apply(stroke, this, args);
      };
    });
    await page.goto("/");
    await expect.poll(() => page.evaluate(() =>
      window.constellationReview.points.length)).toBe(135);
    const result = await page.evaluate(() => {
      const review = window.constellationReview;
      const connections = () => {
        const indices = new Map(review.points.map((point, index) => [point.join(","), index]));
        return new Set(review.edges.map(edge => {
          const a = indices.get(edge.slice(0, 2).join(","))!;
          const b = indices.get(edge.slice(2).join(","))!;
          return `${Math.min(a, b)}:${Math.max(a, b)}`;
        }));
      };
      review.advance(0);
      const initial = review.points;
      const before = review.frames;
      const oldConnections = connections();
      for (let frame = 1; frame <= 120; frame++) review.advance(frame * 1000 / 60);
      const distances = review.points.map((point, index) =>
        Math.hypot(point[0] - initial[index][0], point[1] - initial[index][1])).sort((a, b) => a - b);
      const newConnections = connections();
      return {
        count: review.points.length,
        frames: review.frames - before,
        medianTravel: distances[Math.floor(distances.length / 2)],
        changedConnections: [...oldConnections].filter(edge => !newConnections.has(edge)).length +
          [...newConnections].filter(edge => !oldConnections.has(edge)).length,
      };
    });
    expect(result.count).toBe(135);
    expect(result.frames).toBe(120);
    // The recovered backup travels a median 24px in these two seconds.
    expect(result.medianTravel).toBeGreaterThan(18);
    expect(result.medianTravel).toBeLessThan(32);
    expect(result.changedConnections).toBeGreaterThan(0);
  });
}
