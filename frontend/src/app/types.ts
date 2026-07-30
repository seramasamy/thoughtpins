import type { ReactNode } from "react";
import { ApiError } from "../api";

export type View =
  | "recap"
  | "people"
  | "chat"
  | "places"
  | "pins"
  | "memory"
  | "capture"
  | "library"
  | "entries"
  | "jobs"
  | "account"
  | "legal"
  | "status";

export type GlobalComposeMode = "chat" | "journal";

export type Notice = { tone: "ok" | "warn" | "error"; text: string; requestId?: string };

// `success` may be derived from the result so a caller can report what actually
// happened (for example "saved" versus "queued") instead of one fixed message.
export type Runner = <T>(task: () => Promise<T>, success?: string | ((result: T) => string)) => Promise<T | null>;

export type ScreenProps = {
  token: string;
  run: Runner;
};

export type NavItem = {
  view: View;
  label: string;
  shortLabel: string;
  icon: ReactNode;
};

export function messageFromError(error: unknown): Notice {
  if (error instanceof ApiError) {
    return {
      tone: error.status >= 500 ? "error" : "warn",
      text: error.message,
      requestId: error.requestId,
    };
  }
  if (error instanceof Error) {
    return { tone: "error", text: error.message };
  }
  return { tone: "error", text: "Unexpected error" };
}
