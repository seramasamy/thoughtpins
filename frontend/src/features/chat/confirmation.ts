export type ConfirmationIntent = "confirm" | "cancel" | null;

export const GENERAL_CONFIRMATION_PHRASES = new Set([
  "confirm",
  "yes",
  "yes please",
  "do it",
  "proceed",
  "go ahead",
]);

export const CANCEL_CONFIRMATION_PHRASES = new Set([
  "cancel",
  "cancel that",
  "never mind",
  "nevermind",
  "no",
  "nope",
  "stop",
]);

export function confirmationIntent(text: string): ConfirmationIntent {
  const normalized = normalizeConfirmationText(text);
  if (!normalized) return null;
  if (CANCEL_CONFIRMATION_PHRASES.has(normalized)) return "cancel";
  if (GENERAL_CONFIRMATION_PHRASES.has(normalized)) return "confirm";
  return null;
}

export function normalizeConfirmationText(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/[?!]+/g, "")
    .replace(/[.]+$/g, "")
    .replace(/\s+/g, " ")
    .trim();
}