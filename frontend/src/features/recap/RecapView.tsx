import { CalendarDays, ChevronRight, RefreshCw, Sparkles, Sun } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import type { ScreenProps } from "../../app/types";
import type { EntriesPageResponse, EntryResponse, ReportResponse } from "../../types";
import { ContentSkeleton, EmptyState, IconButton, Panel, StatusPill, useContentSwap } from "../../components/ui";
import { ImportanceRating } from "../../components/ImportanceRating";

type RecapPeriod = "daily" | "weekly" | "monthly";

const PERIODS: Array<{ id: RecapPeriod; label: string }> = [
  { id: "daily", label: "Day" },
  { id: "weekly", label: "Week" },
  { id: "monthly", label: "Month" },
];

export function RecapView({ token, run }: ScreenProps) {
  const [period, setPeriod] = useState<RecapPeriod>("daily");
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [entries, setEntries] = useState<EntriesPageResponse | null>(null);
  const swap = useContentSwap(entries !== null);

  const load = useCallback(async () => {
    const [nextReport, nextEntries] = await Promise.all([
      run(() => api.report(token, period)),
      run(() => api.entries(token, 1, 100)),
    ]);
    if (nextReport) setReport(nextReport);
    if (nextEntries) setEntries(nextEntries);
  }, [period, run, token]);

  useEffect(() => {
    void load();
  }, [load]);

  const periodEntries = useMemo(
    () => (entries?.items || []).filter((entry) => isInsidePeriod(entry, period)),
    [entries, period],
  );
  const digest = useMemo(() => parseReport(report?.markdown || ""), [report]);
  const insightSections = useMemo(() => digest.sections.filter((section) => section.items.length), [digest.sections]);

  return (
    <section className="recap-view">
      <div className="recap-heading">
        <div>
          <span className="eyebrow"><Sun size={14} /> Your life, in view</span>
          <h2>{periodTitle(period)}</h2>
          <p>{periodRange(period)}</p>
        </div>
        <div className="recap-actions">
          <div className="segmented period-switcher" role="group" aria-label="Recap period">
            {PERIODS.map((item) => (
              <button key={item.id} type="button" aria-pressed={period === item.id} className={period === item.id ? "active" : ""} onClick={() => setPeriod(item.id)}>
                {item.label}
              </button>
            ))}
          </div>
          <IconButton onClick={load} aria-label="Refresh recap" title="Refresh recap"><RefreshCw size={17} /></IconButton>
        </div>
      </div>

      <div className="recap-metrics stagger" aria-label="Period summary">
        <div><strong>{digest.stats.entries ?? periodEntries.length}</strong><span>entries</span></div>
        <div><strong>{digest.stats.events ?? 0}</strong><span>events</span></div>
        <div><strong>{digest.stats.memories ?? 0}</strong><span>memories</span></div>
      </div>

      <div className={`recap-layout${insightSections.length ? "" : " no-insights"}`}>
        <Panel className="timeline-panel">
          <div className="section-heading">
            <div><CalendarDays size={18} /><h2>Journal recap</h2></div>
            <span>{periodEntries.length} saved</span>
          </div>
          <div className="recap-timeline content-swap">
            {swap !== "ready" && <ContentSkeleton rows={4} label="Loading journal recap" leaving={swap === "leaving"} />}
            {swap !== "loading" && (
              <>
                {periodEntries.map((entry) => <RecapEntry key={entry.id} entry={entry} />)}
                {swap === "ready" && !periodEntries.length && <EmptyState title={`Nothing saved ${emptyPeriodLabel(period)}`} detail="Your conversations and journal notes will gather here naturally." />}
              </>
            )}
          </div>
        </Panel>

        {insightSections.length > 0 && <aside className="recap-insights">
          <div className="insight-title"><Sparkles size={17} /><span>Synthesized memory</span></div>
          {insightSections.slice(0, 4).map((section) => (
            <section className="insight-section" key={section.title}>
              <h3>{section.title}</h3>
              {section.items.slice(0, 6).map((item, index) => (
                <p key={`${section.title}-${index}`}><ChevronRight size={14} />{item}</p>
              ))}
            </section>
          ))}
        </aside>}
      </div>
    </section>
  );
}

function RecapEntry({ entry }: { entry: EntryResponse }) {
  const time = entry.local_time ? entry.local_time.slice(0, 5) : "";
  return (
    <article className="recap-entry">
      <div className="timeline-rail"><span /></div>
      <div className="recap-entry-body">
        <header>
          <time>{friendlyDate(entry.local_date || entry.created_at_utc)}{time ? `, ${time}` : ""}</time>
          <StatusPill status={entry.processed_status} />
        </header>
        <p>{entry.raw_text}</p>
        {entry.user_importance !== null && <ImportanceRating value={entry.user_importance} readOnly compact />}
      </div>
    </article>
  );
}

function isInsidePeriod(entry: EntryResponse, period: RecapPeriod) {
  const raw = entry.local_date || entry.created_at_utc;
  const value = new Date(raw.includes("T") ? raw : `${raw}T12:00:00`);
  if (Number.isNaN(value.getTime())) return false;
  const start = periodStart(period);
  const end = new Date();
  end.setHours(23, 59, 59, 999);
  return value >= start && value <= end;
}

function periodStart(period: RecapPeriod) {
  const value = new Date();
  value.setHours(0, 0, 0, 0);
  if (period === "weekly") value.setDate(value.getDate() - ((value.getDay() + 6) % 7));
  if (period === "monthly") value.setDate(1);
  return value;
}

function periodTitle(period: RecapPeriod) {
  if (period === "daily") return "Today";
  if (period === "weekly") return "This week";
  return new Intl.DateTimeFormat(undefined, { month: "long" }).format(new Date());
}

function periodRange(period: RecapPeriod) {
  const formatter = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" });
  const start = periodStart(period);
  const end = new Date();
  return period === "daily" ? formatter.format(end) : `${formatter.format(start)} - ${formatter.format(end)}`;
}

function emptyPeriodLabel(period: RecapPeriod) {
  return period === "daily" ? "today" : period === "weekly" ? "this week" : "this month";
}

function friendlyDate(value: string) {
  const date = new Date(value.includes("T") ? value : `${value}T12:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric" }).format(date);
}

function parseReport(markdown: string) {
  const stats: Record<string, number> = {};
  const sections: Array<{ title: string; items: string[] }> = [];
  let current: { title: string; items: string[] } | null = null;

  for (const rawLine of markdown.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("# ")) continue;
    const stat = line.match(/^\*\*(Entries|Events|Memories extracted):\*\*\s*(\d+)/i);
    if (stat) {
      const key = stat[1].toLowerCase().startsWith("memories") ? "memories" : stat[1].toLowerCase();
      stats[key] = Number(stat[2]);
      continue;
    }
    if (line.startsWith("## ")) {
      current = { title: line.slice(3), items: [] };
      sections.push(current);
      continue;
    }
    if (line.startsWith("- ") && current) {
      current.items.push(cleanMarkdown(line.slice(2)));
      continue;
    }
    if (current && current.items.length && !line.startsWith("**")) {
      current.items[current.items.length - 1] += ` ${cleanMarkdown(line)}`;
    }
  }
  return { stats, sections: sections.filter((section) => section.title !== "Sensitivity Warnings") };
}

function cleanMarkdown(value: string) {
  return value
    .replace(/\[\[([^\]]+)\]\]/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}
