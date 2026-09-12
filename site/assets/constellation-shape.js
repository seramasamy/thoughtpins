/* Canonical mark geometry, sampled synchronously so the hero has no loading
   jump. The scroll browser test compares every point with thought-pins-mark.svg. */
export function sampleConstellationMark() {
  const paths = [
    "M64 17C39.7 17 22 34.4 22 57.5c0 20.8 15.7 37.4 42 63.5 26.3-26.1 42-42.7 42-63.5C106 34.4 88.3 17 64 17Z",
    "M64 29v64",
    "M53 29c-8-3-13 2-13 9 0 6 4 9 10 10",
    "M39 41c-7 4-8 13-4 19 4 5 9 5 15 2",
    "M35 63c-2 9 2 17 10 19 7 2 10 6 10 11",
    "M75 29c8-3 13 2 13 9 0 6-4 9-10 10",
    "M89 41c7 4 8 13 4 19-4 5-9 5-15 2",
    "M93 63c2 9-2 17-10 19-7 2-10 6-10 11",
  ];
  const namespace = "http://www.w3.org/2000/svg";
  const holder = document.createElementNS(namespace, "svg");
  holder.setAttribute("aria-hidden", "true");
  holder.style.cssText = "position:absolute;width:0;height:0;overflow:hidden;pointer-events:none";
  document.body.append(holder);
  try {
    return paths.flatMap((d, index) => {
      const path = document.createElementNS(namespace, "path");
      path.setAttribute("d", d);
      holder.append(path);
      const length = path.getTotalLength();
      const count = index === 0 ? 72 : 9;
      return Array.from({ length: count }, (_, i) => {
        const point = path.getPointAtLength(length * i / count);
        return { x: 8.96 + 0.86 * point.x, y: 4.88 + 0.86 * point.y };
      });
    });
  } catch {
    // Keep the floating field and ordinary layout if SVG geometry is unavailable.
    return null;
  } finally {
    holder.remove();
  }
}
