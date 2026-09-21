import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api";
import type { Runner } from "../../app/types";
import type { LibrarySourceResponse } from "../../types";

const PAGE_SIZE = 100;

export function useLibrarySources(token: string, run: Runner) {
  const [sources, setSources] = useState<LibrarySourceResponse[]>([]);
  const [query, setQuery] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [pending, setPending] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const offset = useRef(0);
  const loadedQuery = useRef<string | null>(null);
  const generation = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const inFlight = useRef(false);

  const fetchPage = useCallback(async (append = false) => {
    if (append && (inFlight.current || loadedQuery.current !== query)) return;
    const current = ++generation.current;
    controller.current?.abort();
    const active = new AbortController();
    controller.current = active;
    inFlight.current = true;
    setPending(true);
    const start = append ? offset.current : 0;
    try {
      const result = await run(() => api.librarySources(token, PAGE_SIZE, { offset: start, query, signal: active.signal }));
      if (result && current === generation.current) {
        setSources(previous => {
          const combined = append ? [...previous, ...result] : result;
          return [...new Map(combined.map(source => [source.id, source])).values()];
        });
        offset.current = start + result.length;
        loadedQuery.current = query;
        setHasMore(result.length === PAGE_SIZE);
      }
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) throw error;
    } finally {
      if (current === generation.current) {
        inFlight.current = false;
        setPending(false);
        setLoaded(true);
      }
    }
  }, [query, run, token]);

  useEffect(() => {
    setHasMore(false);
    setPending(true);
    const timer = window.setTimeout(() => void fetchPage(), query ? 200 : 0);
    return () => {
      window.clearTimeout(timer);
      generation.current += 1;
      controller.current?.abort();
      inFlight.current = false;
    };
  }, [fetchPage, query]);

  return { sources, query, setQuery, loaded, pending, hasMore,
    load: () => fetchPage(), loadMore: () => fetchPage(true) };
}
