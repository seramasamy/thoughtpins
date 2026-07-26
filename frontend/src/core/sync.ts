import type { IngestResponse } from "../types";
import type { CaptureDraft, DraftQueue } from "./draftQueue";

export type DraftSyncResult = {
  draftId: string;
  status: "synced" | "failed";
  entryId?: string;
  jobId?: string | null;
  error?: string;
};

export type DraftSyncSummary = {
  attempted: number;
  synced: number;
  failed: number;
  results: DraftSyncResult[];
};

export type DraftIngestFn = (draft: CaptureDraft) => Promise<IngestResponse>;

export type DraftQueueLike = Pick<DraftQueue, "pending" | "update"> | {
  pending: () => Promise<CaptureDraft[]>;
  update: (
    id: string,
    patch: Partial<Omit<CaptureDraft, "id" | "createdAtUtc">>,
  ) => Promise<CaptureDraft | null>;
};

export async function syncDraftQueue(queue: DraftQueueLike, ingest: DraftIngestFn): Promise<DraftSyncSummary> {
  const pending = await queue.pending();
  const results: DraftSyncResult[] = [];

  for (const draft of pending) {
    await queue.update(draft.id, {
      status: "submitting",
      attemptCount: draft.attemptCount + 1,
      lastError: undefined,
    });
    try {
      const response = await ingest(draft);
      await queue.update(draft.id, {
        status: "synced",
        entryId: response.entry_id,
        jobId: response.job_id,
      });
      results.push({
        draftId: draft.id,
        status: "synced",
        entryId: response.entry_id,
        jobId: response.job_id,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Sync failed";
      await queue.update(draft.id, {
        status: "failed",
        lastError: message,
      });
      results.push({ draftId: draft.id, status: "failed", error: message });
    }
  }

  return {
    attempted: results.length,
    synced: results.filter((result) => result.status === "synced").length,
    failed: results.filter((result) => result.status === "failed").length,
    results,
  };
}
