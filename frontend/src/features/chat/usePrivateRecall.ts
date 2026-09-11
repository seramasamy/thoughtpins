import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import type { Runner } from "../../app/types";

/** The saved default never overrides a choice made for this conversation. */
export function usePrivateRecall(token: string, run: Runner) {
  const [enabled, setEnabled] = useState(false);
  const explicitlySelected = useRef(false);
  useEffect(() => {
    let active = true;
    void run(() => api.preferences(token)).then(preferences => {
      if (active && preferences && !explicitlySelected.current) {
        setEnabled(preferences.private_entries_in_ask);
      }
    });
    return () => { active = false; };
  }, [run, token]);

  function select(value: boolean) {
    explicitlySelected.current = true;
    setEnabled(value);
  }
  return [enabled, select] as const;
}
