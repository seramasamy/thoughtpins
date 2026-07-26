import { api } from "../api";
import type { CaptureDraft } from "./draftQueue";
import { syncDraftQueue, type DraftQueueLike, type DraftSyncSummary } from "./sync";

export type SyncScheduler = {
  start: () => void;
  stop: () => void;
  runNow: () => Promise<DraftSyncSummary>;
};

export function createDraftSyncScheduler(
  queue: DraftQueueLike,
  tokenProvider: () => string,
  intervalMs = 30_000,
): SyncScheduler {
  let timer: number | null = null;
  let inFlight: Promise<DraftSyncSummary> | null = null;

  const runNow = () => {
    if (inFlight) return inFlight;
    inFlight = syncDraftQueue(
      queue,
      (draft: CaptureDraft) => api.ingest(tokenProvider(), draft.text, null, draft.id),
    ).finally(() => {
      inFlight = null;
    });
    return inFlight;
  };

  const handleOnline = () => {
    void runNow();
  };

  return {
    start() {
      if (timer !== null) {
        return;
      }
      timer = window.setInterval(() => {
        void runNow();
      }, intervalMs);
      window.addEventListener("online", handleOnline);
      if (navigator.onLine) void runNow();
    },
    stop() {
      if (timer !== null) {
        window.clearInterval(timer);
        timer = null;
      }
      window.removeEventListener("online", handleOnline);
    },
    runNow,
  };
}
