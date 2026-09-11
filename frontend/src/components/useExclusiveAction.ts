import { useRef, useState } from "react";

/** Guard immediately, including two events before React's next render. */
export function useExclusiveAction() {
  const active = useRef(false);
  const [pending, setPending] = useState(false);
  async function perform(action: () => Promise<void>) {
    if (active.current) return;
    active.current = true;
    setPending(true);
    try { await action(); }
    finally { active.current = false; setPending(false); }
  }
  return { pending, perform };
}
