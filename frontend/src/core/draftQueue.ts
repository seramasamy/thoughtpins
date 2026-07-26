import type { KeyValueStorage } from "./storage";
import { normalizeJournalText, validateJournalText } from "./validation";

export type DraftStatus = "draft" | "queued" | "submitting" | "failed" | "synced";

export type CaptureDraft = {
  id: string;
  text: string;
  status: DraftStatus;
  createdAtUtc: string;
  updatedAtUtc: string;
  attemptCount: number;
  lastError?: string;
  entryId?: string;
  jobId?: string | null;
};

type DraftQueueOptions = {
  storageKey?: string;
  now?: () => Date;
  newId?: () => string;
};

export class DraftQueue {
  private readonly storageKey: string;
  private readonly now: () => Date;
  private readonly newId: () => string;

  constructor(private readonly storage: KeyValueStorage, options: DraftQueueOptions = {}) {
    this.storageKey = options.storageKey || "thoughtpins.captureDrafts.v1";
    this.now = options.now || (() => new Date());
    this.newId = options.newId || (() => crypto.randomUUID());
  }

  list(): CaptureDraft[] {
    try {
      const raw = this.storage.getItem(this.storageKey);
      const parsed = raw ? (JSON.parse(raw) as CaptureDraft[]) : [];
      return parsed.sort((a, b) => a.createdAtUtc.localeCompare(b.createdAtUtc));
    } catch {
      return [];
    }
  }

  create(text: string, status: DraftStatus = "draft"): CaptureDraft {
    const normalized = normalizeJournalText(text);
    const issues = validateJournalText(normalized);
    if (issues.length) {
      throw new Error(issues[0].message);
    }
    const now = this.now().toISOString();
    const draft: CaptureDraft = {
      id: this.newId(),
      text: normalized,
      status,
      createdAtUtc: now,
      updatedAtUtc: now,
      attemptCount: 0,
    };
    this.write([...this.list(), draft]);
    return draft;
  }

  update(id: string, patch: Partial<Omit<CaptureDraft, "id" | "createdAtUtc">>): CaptureDraft | null {
    let updated: CaptureDraft | null = null;
    const drafts = this.list().map((draft) => {
      if (draft.id !== id) {
        return draft;
      }
      updated = {
        ...draft,
        ...patch,
        updatedAtUtc: this.now().toISOString(),
      };
      return updated;
    });
    this.write(drafts);
    return updated;
  }

  remove(id: string): void {
    this.write(this.list().filter((draft) => draft.id !== id));
  }

  pending(): CaptureDraft[] {
    return this.list().filter((draft) => ["queued", "failed"].includes(draft.status));
  }

  private write(drafts: CaptureDraft[]): void {
    const retained = drafts
      .filter((draft) => draft.status !== "synced")
      .slice(-250);
    this.storage.setItem(this.storageKey, JSON.stringify(retained));
  }
}
