import { useEffect, useRef, useState } from "react";
import { api, type ApiSession } from "../api";
import type { TokenResponse } from "../types";
import { messageFromError, type Notice } from "./types";

type AuthMethod = "password" | "google" | "apple" | "email" | "code" | "link";

/** One authentication operation owns the form, including before React rerenders. */
export function useAuthRequest(
  setSession: (session: ApiSession | null) => void,
  setNotice: (notice: Notice | null) => void,
) {
  const [magicToken] = useState(() => new URLSearchParams(window.location.search).get("magic")?.trim() || null);
  const [pending, setPending] = useState<AuthMethod | null>(magicToken ? "link" : null);
  const locked = useRef(Boolean(magicToken));
  const mounted = useRef(false);
  const linkRequest = useRef<Promise<TokenResponse> | null>(null);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    if (!magicToken) return;
    let active = true;
    const url = new URL(window.location.href);
    url.searchParams.delete("magic");
    window.history.replaceState({}, "", url);
    // Strict Mode replays effects. Subscribe again to the same request: a
    // single-use token must neither be consumed twice nor lose its result.
    const request = linkRequest.current ??= api.consumeMagicLink(magicToken);
    request.then(tokens => {
      if (active) setSession({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token });
    }).catch(error => {
      if (active) setNotice(messageFromError(error));
    }).finally(() => {
      if (active) {
        locked.current = false;
        setPending(null);
      }
    });
    return () => { active = false; };
  }, [magicToken, setSession, setNotice]);

  async function run<T>(
    method: AuthMethod,
    task: () => Promise<T>,
    onSuccess: (result: T) => void,
    onFailure?: () => void,
  ): Promise<void> {
    if (locked.current || !mounted.current) return;
    locked.current = true;
    setPending(method);
    setNotice(null);
    try {
      const result = await task();
      if (mounted.current) onSuccess(result);
    } catch (error) {
      if (mounted.current) {
        setNotice(messageFromError(error));
        onFailure?.();
      }
    } finally {
      locked.current = false;
      if (mounted.current) setPending(null);
    }
  }

  return { pending, run };
}
