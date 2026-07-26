import { ChevronLeft, ChevronRight, FileText, RefreshCw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import type { ScreenProps } from "../../app/types";
import type { EntriesPageResponse, EntryResponse } from "../../types";
import { formatDate } from "../../components/format";
import { ImportanceRating } from "../../components/ImportanceRating";
import { ContentSkeleton, EmptyState, IconButton, Panel, PanelTitle, StatusPill, useContentSwap } from "../../components/ui";

export function EntriesView({ token, run }: ScreenProps) {
  const [page, setPage] = useState(1);
  const [entries, setEntries] = useState<EntriesPageResponse | null>(null);
  const [ratingEntryId, setRatingEntryId] = useState<string | null>(null);
  const swap = useContentSwap(entries !== null);

  const load = useCallback(async () => {
    const result = await run(() => api.entries(token, page));
    if (result) setEntries(result);
  }, [page, run, token]);

  useEffect(() => {
    void load();
  }, [load]);

  const remove = async (entryId: string) => {
    const result = await run(() => api.deleteEntry(token, entryId), "Entry deleted");
    if (result) void load();
  };

  const setImportance = async (entryId: string, value: number | null) => {
    setRatingEntryId(entryId);
    try {
      const result = await run(
        () => api.updateEntryImportance(token, entryId, value),
        value === null ? "Importance cleared" : `Importance set to ${value} of 5`,
      );
      if (result) {
        setEntries((current) => current ? {
          ...current,
          items: current.items.map((entry) => entry.id === entryId ? result : entry),
        } : current);
      }
    } finally {
      setRatingEntryId(null);
    }
  };

  return (
    <Panel>
      <PanelTitle icon={<FileText size={18} />} title="Entries" action={<IconButton onClick={load} aria-label="Refresh entries" title="Refresh entries"><RefreshCw size={17} /></IconButton>} />
      <div className="entry-timeline content-swap stagger">
        {swap !== "ready" && <ContentSkeleton rows={5} label="Loading journal entries" leaving={swap === "leaving"} />}
        {swap !== "loading" && (entries?.items || []).map((entry) => {
          const rail = railDate(entry);
          return (
            <article className="entry-row" key={entry.id}>
              <div className="entry-rail">
                <span className="entry-rail-day">{rail.day}</span>
                <span className="entry-rail-month">{rail.monthYear}</span>
              </div>
              <div className="entry-card">
                <div className="entry-head">
                  <div>
                    <strong>{entry.local_time || "Journal entry"}</strong>
                    <span>{entry.source}</span>
                  </div>
                  <StatusPill status={entry.processed_status} />
                </div>
                <p>{entry.raw_text}</p>
                <div className="entry-foot">
                  <ImportanceRating value={entry.user_importance} disabled={ratingEntryId === entry.id} onChange={(value) => void setImportance(entry.id, value)} />
                  <IconButton danger className="entry-delete" onClick={() => remove(entry.id)} aria-label="Delete entry" title="Delete entry"><Trash2 size={16} /></IconButton>
                </div>
              </div>
            </article>
          );
        })}
        {swap === "ready" && entries !== null && !entries.items.length && <EmptyState title="No entries yet" detail="Use Chat or Capture to save your first journal note." />}
      </div>
      <div className="pager">
        <button className="quiet-button" type="button" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}><ChevronLeft size={15} aria-hidden="true" /> Previous</button>
        <span>Page {page}</span>
        <button className="quiet-button" type="button" onClick={() => setPage((p) => p + 1)} disabled={!entries?.has_next}>Next <ChevronRight size={15} aria-hidden="true" /></button>
      </div>
    </Panel>
  );
}

function railDate(entry: EntryResponse) {
  const raw = entry.local_date || entry.created_at_utc;
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw);
  const date = dateOnly
    ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]))
    : new Date(raw);
  if (Number.isNaN(date.valueOf())) {
    return { day: formatDate(entry.created_at_utc), monthYear: "" };
  }
  return {
    day: String(date.getDate()),
    monthYear: date.toLocaleDateString(undefined, { month: "short", year: "numeric" }),
  };
}
