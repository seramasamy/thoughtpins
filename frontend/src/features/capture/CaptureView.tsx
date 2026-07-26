import { RefreshCw, Send, Trash2 } from "lucide-react";
import type { FormEvent } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import type { ScreenProps } from "../../app/types";
import { EmptyState, IconButton, KeyValue, PrimaryButton, SecondaryButton, StatusPill } from "../../components/ui";
import { truncate } from "../../components/format";
import { EncryptedDraftQueue, browserStorage, syncDraftQueue, type CaptureDraft, type DraftSyncSummary } from "../../core";

export function CaptureView({ token, run }: ScreenProps) {
  const [text, setText] = useState("");
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [drafts, setDrafts] = useState<CaptureDraft[]>([]);
  const [syncSummary, setSyncSummary] = useState<DraftSyncSummary | null>(null);
  const [queueMessage, setQueueMessage] = useState<string | null>(null);

  const queue = useMemo(() => {
    const storage = browserStorage();
    return storage ? new EncryptedDraftQueue(storage) : null;
  }, []);

  const refreshDrafts = useCallback(async () => {
    setDrafts(queue ? await queue.list() : []);
  }, [queue]);

  useEffect(() => {
    void refreshDrafts();
  }, [refreshDrafts]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const body = text.trim();
    if (!body) return;

    const result = await run(() => api.ingest(token, body), "Entry saved");
    if (result) {
      setSavedAt(new Date());
      setText("");
      setQueueMessage(null);
      void refreshDrafts();
      return;
    }

    if (!queue) return;
    await queue.create(body, "queued");
    setText("");
    setQueueMessage("Saved locally. Sync queued drafts when the connection or backend is healthy.");
    void refreshDrafts();
  };

  const syncQueued = async () => {
    if (!queue) return;
    const summary = await run(
      () => syncDraftQueue(queue, (draft) => api.ingest(token, draft.text, null, draft.id)),
      "Draft sync complete",
    );
    if (summary) {
      setSyncSummary(summary);
      setQueueMessage(summary.failed ? "Some local drafts still need attention." : "Queued drafts synced.");
      void refreshDrafts();
    }
  };

  const removeDraft = async (id: string) => {
    await queue?.remove(id);
    await refreshDrafts();
  };

  return (
    <section className="capture-surface">
      <form className="capture-editor" onSubmit={submit}>
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          maxLength={50000}
          rows={10}
          autoFocus
          placeholder="What do you want to remember?"
          aria-label="Journal entry text"
        />
        <div className="capture-editor-foot">
          <span className="capture-saved">{savedAt ? `Last saved ${savedAt.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}` : "Not saved yet"}</span>
          <div className="capture-editor-actions">
            <span className="subtle">{text.length.toLocaleString()} / 50,000</span>
            <PrimaryButton disabled={!text.trim()}>
              <Send size={16} />
              Save
            </PrimaryButton>
          </div>
        </div>
      </form>

      <section className="capture-drafts">
        <header className="capture-drafts-head">
          <div>
            <h2>Draft queue</h2>
            <p>Notes kept on this device when a save could not reach the server.</p>
          </div>
          <SecondaryButton onClick={syncQueued} disabled={!queue || !drafts.some((draft) => ["queued", "failed"].includes(draft.status))}>
            <RefreshCw size={15} />
            Sync queued
          </SecondaryButton>
        </header>
        {queueMessage && <p className="inline-help">{queueMessage}</p>}
        {syncSummary && (
          <div className="draft-summary" aria-live="polite">
            <KeyValue label="Attempted" value={syncSummary.attempted} />
            <KeyValue label="Synced" value={syncSummary.synced} />
            <KeyValue label="Failed" value={syncSummary.failed} />
          </div>
        )}
        {drafts.length ? (
          <div className="draft-list">
            {drafts.map((draft) => (
              <article className="draft-item" key={draft.id}>
                <div className="draft-meta">
                  <span className="draft-time">{new Date(draft.updatedAtUtc).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</span>
                  <StatusPill status={draft.status} />
                  <IconButton className="draft-delete" onClick={() => { void removeDraft(draft.id); }} aria-label="Remove local draft" title="Remove local draft">
                    <Trash2 size={15} />
                  </IconButton>
                </div>
                <p className="draft-text">{firstLine(draft.text)}</p>
                {draft.lastError && <p className="inline-help">{draft.lastError}</p>}
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="No local drafts" detail="If saving fails while offline or during maintenance, Thought Pins keeps a local queued draft here." />
        )}
      </section>
    </section>
  );
}

function firstLine(value: string) {
  const line = value.split("\n").find((part) => part.trim()) || "";
  return truncate(line, 140);
}
