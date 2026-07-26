import { useSyncExternalStore } from "react";

export type ThemeMode = "auto" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

const THEME_STORAGE_KEY = "tp-theme";

export const THEME_MODES: ThemeMode[] = ["auto", "light", "dark"];

const systemDark = window.matchMedia("(prefers-color-scheme: dark)");
let currentMode: ThemeMode = readStoredMode();
const listeners = new Set<() => void>();

function readStoredMode(): ThemeMode {
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY);
    return value === "light" || value === "dark" ? value : "auto";
  } catch {
    return "auto";
  }
}

function emit() {
  listeners.forEach((listener) => listener());
}

systemDark.addEventListener?.("change", emit);

export function getThemeMode(): ThemeMode {
  return currentMode;
}

/** The theme actually on screen: the stored choice, or the system when unset. */
export function getResolvedTheme(): ResolvedTheme {
  return currentMode === "auto" ? (systemDark.matches ? "dark" : "light") : currentMode;
}

/** Persists the choice and points <html data-theme> at it. "auto" removes the
    attribute so the prefers-color-scheme media query decides. */
export function applyThemeMode(mode: ThemeMode): void {
  currentMode = mode;
  try {
    if (mode === "auto") localStorage.removeItem(THEME_STORAGE_KEY);
    else localStorage.setItem(THEME_STORAGE_KEY, mode);
  } catch {
    // Storage may be unavailable in a private browser; the choice still applies.
  }
  if (mode === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = mode;
  emit();
}

/** Two-state toggle for header buttons: flips the effective theme. */
export function toggleTheme(): ResolvedTheme {
  const next: ResolvedTheme = getResolvedTheme() === "dark" ? "light" : "dark";
  applyThemeMode(next);
  return next;
}

function subscribeTheme(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useTheme(): ThemeMode {
  return useSyncExternalStore(subscribeTheme, getThemeMode);
}

export function useResolvedTheme(): ResolvedTheme {
  return useSyncExternalStore(subscribeTheme, getResolvedTheme);
}
