import { AlertCircle, ArrowRight, CheckCircle2, XCircle } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Notice } from "../app/types";
import { displayStatus } from "./format";
import "./notice.css";

// Custom speech-bubble glyph, drawn to sit optically centered inside a circle
// (the Lucide bubble's tail pulls its visual mass off-center). Its body and the
// three "thought" dots are balanced on the 24x24 box. Used for the featured
// Chat navigation tile and the assistant message avatar so the mark reads the
// same everywhere.
export function ChatGlyph({ className, size = 24 }: { className?: string; size?: number }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5.6 5h12.8a2.6 2.6 0 0 1 2.6 2.6v6.2a2.6 2.6 0 0 1 -2.6 2.6h-5.9l-3.7 3v-3H5.6A2.6 2.6 0 0 1 3 13.8V7.6A2.6 2.6 0 0 1 5.6 5Z" />
      <circle cx="8.7" cy="10.7" r="1.05" fill="currentColor" stroke="none" />
      <circle cx="12" cy="10.7" r="1.05" fill="currentColor" stroke="none" />
      <circle cx="15.3" cy="10.7" r="1.05" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className={compact ? "brand brand-compact" : "brand"}>
      <img className="brand-icon" src={`${import.meta.env.BASE_URL}assets/thought-pins-mark.svg?v=20260712-memory-pin-v4`} alt="" width="38" height="38" />
      <div>
        <strong>Thought Pins</strong>
        {!compact && <span>private memory layer</span>}
      </div>
    </div>
  );
}

export function LoadingScreen() {
  return (
    <main className="auth-layout">
      <section className="auth-panel">
        <BrandMark />
        <div className="loading-line">
          <span className="thinking-dots" aria-hidden="true"><i /><i /><i /></span>
          <span>Opening your memory</span>
        </div>
      </section>
    </main>
  );
}

export function NoticeBanner({ notice, clear }: { notice: Notice; clear: () => void }) {
  const Icon = notice.tone === "ok" ? CheckCircle2 : notice.tone === "warn" ? AlertCircle : XCircle;
  const clearRef = useRef(clear);
  const [dismissing, setDismissing] = useState(false);

  useEffect(() => {
    clearRef.current = clear;
  }, [clear]);

  useEffect(() => {
    setDismissing(false);
    if (notice.tone !== "ok") return undefined;
    const fadeTimer = window.setTimeout(() => setDismissing(true), 3000);
    const clearTimer = window.setTimeout(() => clearRef.current(), 3600);
    return () => {
      window.clearTimeout(fadeTimer);
      window.clearTimeout(clearTimer);
    };
  }, [notice]);

  return (
    <div className={`notice ${notice.tone}${dismissing ? " is-dismissing" : ""}`} role="status">
      <Icon size={18} />
      <span>{notice.text}</span>
      {notice.requestId && <small className="notice-reference">Reference {notice.requestId}</small>}
      <button className="icon-button" onClick={clear} aria-label="Dismiss" title="Dismiss">
        <XCircle size={16} />
      </button>
    </div>
  );
}

export function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`.trim()}>{children}</section>;
}

export function PanelTitle({ icon, title, action }: { icon: ReactNode; title: string; action?: ReactNode }) {
  return (
    <div className="panel-title">
      <div>{icon}<h2>{title}</h2></div>
      {action}
    </div>
  );
}

export function Metric({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <section className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {hint && <small>{hint}</small>}
    </section>
  );
}

export function KeyValue({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="key-value">
      <span>{label}</span>
      <strong>{value ?? "none"}</strong>
    </div>
  );
}

export function StatusPill({ status }: { status: string }) {
  return <span className={`status ${statusClass(status)}`}>{displayStatus(status)}</span>;
}

export function EmptyState({ title, detail, action }: { title: string; detail?: string; action?: { label: string; onClick: () => void } }) {
  return (
    <div className="empty-state">
      <div className="empty-state-halo" aria-hidden="true">
        <img className="empty-state-mark" src={`${import.meta.env.BASE_URL}assets/thought-pins-mark.svg?v=20260712-memory-pin-v4`} alt="" width="56" height="56" />
      </div>
      <strong>{title}</strong>
      {detail && <span>{detail}</span>}
      {action && (
        <button className="empty-state-action" type="button" onClick={action.onClick}>
          {action.label}
          <ArrowRight size={15} aria-hidden="true" />
        </button>
      )}
    </div>
  );
}

export function ContentSkeleton({ rows = 3, label = "Loading content", leaving = false }: { rows?: number; label?: string; leaving?: boolean }) {
  return (
    <div className={`skeleton-stack${leaving ? " is-leaving" : ""}`} role="status" aria-label={label} aria-hidden={leaving || undefined}>
      <span className="skeleton skeleton-title" />
      {Array.from({ length: rows }, (_, index) => (
        <span className={`skeleton skeleton-line skeleton-line-${(index % 3) + 1}`} key={index} />
      ))}
      <span className="visually-hidden">{label}</span>
    </div>
  );
}

/** Keeps the skeleton mounted for a 160ms fade-out once content is ready, so
    loading hands off to real content as a crossfade instead of a hard cut. */
export function useContentSwap(loaded: boolean): "loading" | "leaving" | "ready" {
  const [phase, setPhase] = useState<"loading" | "leaving" | "ready">(loaded ? "ready" : "loading");

  useEffect(() => {
    if (!loaded) {
      if (phase !== "loading") setPhase("loading");
      return;
    }
    if (phase !== "loading") return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) setPhase("ready");
    else setPhase("leaving");
  }, [loaded, phase]);

  useEffect(() => {
    if (phase !== "leaving") return undefined;
    const timer = window.setTimeout(() => setPhase("ready"), 160);
    return () => window.clearTimeout(timer);
  }, [phase]);

  return phase;
}

export function PrimaryButton({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { className = "", ...buttonProps } = props;
  return <button className={`primary-button ${className}`.trim()} {...buttonProps}>{children}</button>;
}

export function SecondaryButton({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { className = "", ...buttonProps } = props;
  return <button className={`secondary-button ${className}`.trim()} {...buttonProps}>{children}</button>;
}

export function IconButton({ children, danger = false, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { danger?: boolean }) {
  const { className = "", ...buttonProps } = props;
  return <button className={`${danger ? "icon-button danger" : "icon-button"} ${className}`.trim()} {...buttonProps}>{children}</button>;
}

export function statusClass(status: string) {
  if (["ok", "completed", "processed", "replied", "stored", "journal", "chat", "conversation", "stored_private", "synced"].includes(status)) return "good";
  if (["configured", "pending", "queued", "submitting", "retry", "running", "processing", "needs_confirmation"].includes(status)) return "work";
  if (["disabled", "canceled", "not_attempted"].includes(status)) return "muted";
  return "bad";
}
