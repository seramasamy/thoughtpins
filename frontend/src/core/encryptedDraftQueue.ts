import type { KeyValueStorage } from "./storage";
import type { CaptureDraft, DraftStatus } from "./draftQueue";
import { decryptJson, encryptJson, generateAesKey, importAesKey, exportAesKey, hasWebCrypto } from "./crypto";
import { normalizeJournalText, validateJournalText } from "./validation";

type EncryptedDraftQueueOptions = {
  storageKey?: string;
  keyStorageKey?: string;
  legacyStorageKey?: string;
  now?: () => Date;
  newId?: () => string;
};

export class EncryptedDraftQueue {
  private readonly storageKey: string;
  private readonly keyStorageKey: string;
  private readonly legacyStorageKey: string;
  private readonly now: () => Date;
  private readonly newId: () => string;

  constructor(private readonly storage: KeyValueStorage, options: EncryptedDraftQueueOptions = {}) {
    this.storageKey = options.storageKey || "thoughtpins.encryptedCaptureDrafts.v1";
    this.keyStorageKey = options.keyStorageKey || "thoughtpins.encryptedCaptureDrafts.key.v1";
    this.legacyStorageKey = options.legacyStorageKey || "thoughtpins.captureDrafts.v1";
    this.now = options.now || (() => new Date());
    this.newId = options.newId || (() => crypto.randomUUID());
  }

  async list(): Promise<CaptureDraft[]> {
    if (!hasWebCrypto()) {
      return [];
    }
    await this.migrateLegacyDrafts();
    const raw = this.storage.getItem(this.storageKey);
    if (!raw) {
      return [];
    }
    try {
      const key = await this.getKey();
      const drafts = await decryptJson<CaptureDraft[]>(JSON.parse(raw), key);
      return drafts.sort((a, b) => a.createdAtUtc.localeCompare(b.createdAtUtc));
    } catch {
      return [];
    }
  }

  async create(text: string, status: DraftStatus = "draft"): Promise<CaptureDraft> {
    if (!hasWebCrypto()) {
      throw new Error("Secure local drafts are not available in this browser.");
    }
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
    await this.write([...(await this.list()), draft]);
    return draft;
  }

  async update(id: string, patch: Partial<Omit<CaptureDraft, "id" | "createdAtUtc">>): Promise<CaptureDraft | null> {
    let updated: CaptureDraft | null = null;
    const drafts = (await this.list()).map((draft) => {
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
    await this.write(drafts);
    return updated;
  }

  async pending(): Promise<CaptureDraft[]> {
    return (await this.list()).filter((draft) => ["queued", "failed"].includes(draft.status));
  }

  async remove(id: string): Promise<void> {
    await this.write((await this.list()).filter((draft) => draft.id !== id));
  }

  async clear(): Promise<void> {
    this.storage.removeItem(this.storageKey);
    this.storage.removeItem(this.keyStorageKey);
    this.storage.removeItem(this.legacyStorageKey);
  }

  private async write(drafts: CaptureDraft[]): Promise<void> {
    const retained = drafts
      .filter((draft) => draft.status !== "synced")
      .slice(-250);
    const envelope = await encryptJson(retained, await this.getKey());
    this.storage.setItem(this.storageKey, JSON.stringify(envelope));
  }

  private async getKey(): Promise<CryptoKey> {
    const existing = this.storage.getItem(this.keyStorageKey);
    if (existing) {
      return importAesKey(existing);
    }
    const key = await generateAesKey();
    this.storage.setItem(this.keyStorageKey, await exportAesKey(key));
    return key;
  }

  private async migrateLegacyDrafts(): Promise<void> {
    if (this.storage.getItem(this.storageKey)) return;
    const legacy = this.storage.getItem(this.legacyStorageKey);
    if (!legacy) return;
    try {
      const parsed = JSON.parse(legacy) as CaptureDraft[];
      if (!Array.isArray(parsed)) return;
      await this.write(parsed);
      this.storage.removeItem(this.legacyStorageKey);
    } catch {
      // Keep the legacy value intact so a transient crypto failure cannot lose a draft.
    }
  }
}
