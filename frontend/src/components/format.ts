export function formatDate(value: string | null | undefined) {
  if (!value) return "none";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function formatConversationDay(value: string | null | undefined, now = new Date()) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  const day = new Date(date.getFullYear(), date.getMonth(), date.getDate()).valueOf();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).valueOf();
  const dayDelta = Math.round((today - day) / 86_400_000);
  if (dayDelta === 0) return "Today";
  if (dayDelta === 1) return "Yesterday";
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: date.getFullYear() === now.getFullYear() ? undefined : "numeric",
  });
}

export function formatConversationTime(value: string | null | undefined) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

export function compactNumber(value: number | null | undefined) {
  return typeof value === "number" ? value.toLocaleString() : "0";
}

export function statusLine(value: Record<string, unknown>) {
  const parts = ["pending", "retry", "queued", "running", "dead_letter"]
    .filter((key) => typeof value[key] === "number" && value[key] !== 0)
    .map((key) => `${key}:${value[key]}`);
  return parts.length ? parts.join(" ") : String(value.status || "ok");
}

export function truncate(text: string, limit = 220) {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (normalized.length <= limit) return normalized;
  return `${normalized.slice(0, limit - 1).trimEnd()}...`;
}

const DISPLAY_LABELS: Record<string, string> = {
  associated_with: "Associated with",
  discussed: "Discussed",
  high_confidence: "High confidence",
  inferred_by_model: "AI inferred",
  met_at: "Met at",
  observed_by_user: "From your journal",
  source_document: "Source document",
};

const STATUS_LABELS: Record<string, string> = {
  completed: "Ready",
  configured: "Ready",
  dead_letter: "Needs attention",
  failed: "Needs attention",
  not_attempted: "Not started",
  pending: "In progress",
  processed: "Ready",
  processing: "Processing",
  queued: "Queued",
  retry: "Retrying",
  running: "Processing",
};

export function humanizeIdentifier(value: string | null | undefined) {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) return "Not specified";
  if (DISPLAY_LABELS[normalized]) return DISPLAY_LABELS[normalized];
  return normalized
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
    .replace(/\bAi\b/g, "AI")
    .replace(/\bApi\b/g, "API")
    .replace(/\bUrl\b/g, "URL");
}

export function displayStatus(value: string | null | undefined) {
  const normalized = String(value || "").trim().toLowerCase();
  return STATUS_LABELS[normalized] || humanizeIdentifier(normalized);
}

export function cleanDisplayText(value: string | null | undefined) {
  let text = String(value || "")
    .replace(/\[TP_DEMO_CORPUS\]\s*:?\s*/gi, "")
    .replace(/\bTP_DEMO_CORPUS\s*:\s*/gi, "")
    .replace(/\bTP_DEMO_CORPUS\b/gi, "demo reference")
    .replace(/\s+/g, " ")
    .trim();
  if (/^User\b/.test(text)) text = `You${text.slice(4)}`;
  return text;
}

export function displayEntityName(value: string | null | undefined) {
  const name = cleanDisplayText(value);
  return name.toLowerCase() === "user" ? "You" : name || "Untitled";
}

export function displayReferenceTitle(path: string | null | undefined, fallback = "Saved note") {
  if (!path) return fallback;
  const stem = path.split(/[\\/]/).pop()?.replace(/\.md$/i, "").replace(/[_-]+/g, " ").trim();
  return stem || fallback;
}

export function formatShortDate(value: string | null | undefined) {
  if (!value) return "Not dated";
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const date = dateOnly
    ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]))
    : new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
