/* The sign-in pane's night sky: a small memory network with a few fictional
   remembered fragments resting on it, echoing the homepage. Purely
   decorative, so it is hidden from assistive technology, and it only moves
   when motion is allowed (154-luminous-auth.css). */

type SkyNode = readonly [x: number, y: number, radius: number, ember?: boolean];

const NODES: readonly SkyNode[] = [
  [26, 112, 2.2],
  [84, 64, 2.8, true],
  [146, 100, 2.4],
  [198, 40, 2.2],
  [258, 86, 2.6, true],
  [314, 34, 2],
  [110, 138, 1.8],
  [236, 134, 2],
  [40, 22, 1.6],
  [166, 12, 1.8, true],
];

/** Pairs of node indexes; the signal links carry a travelling light. */
const LINKS: readonly (readonly [number, number])[] = [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [2, 6], [4, 7], [1, 8], [3, 9], [2, 7]];
const SIGNALS: readonly (readonly [number, number])[] = [[1, 2], [3, 4], [2, 7]];

function segment([from, to]: readonly [number, number]) {
  const [x1, y1] = NODES[from] ?? [0, 0];
  const [x2, y2] = NODES[to] ?? [0, 0];
  return { x1, y1, x2, y2 };
}

export function AuthSky() {
  return (
    <div className="auth-sky" aria-hidden="true">
      <svg className="auth-sky-web" viewBox="0 0 336 150" preserveAspectRatio="xMidYMid slice" focusable="false">
        <g className="auth-sky-links">
          {LINKS.map((link) => <line key={link.join("-")} {...segment(link)} />)}
        </g>
        <g className="auth-sky-signals">
          {SIGNALS.map((link) => <line key={link.join("-")} pathLength={1} {...segment(link)} />)}
        </g>
        <g className="auth-sky-nodes">
          {NODES.map(([cx, cy, r, ember]) => <circle key={`${cx}-${cy}`} className={ember ? "is-ember" : undefined} cx={cx} cy={cy} r={r} />)}
        </g>
      </svg>
      <span className="auth-memory-chip auth-memory-chip--one"><i />Nora got the job</span>
      <span className="auth-memory-chip auth-memory-chip--two"><i />The copper lantern at Atlas Cafe</span>
      <span className="auth-memory-chip auth-memory-chip--three"><i />That idea on the 7:40 train</span>
    </div>
  );
}
