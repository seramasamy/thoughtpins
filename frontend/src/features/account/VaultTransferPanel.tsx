import { FileUp, RotateCcw, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, api } from "../../api";
import { KeyValue, PrimaryButton, SecondaryButton, StatusPill } from "../../components/ui";
import type { VaultConflictPolicy, VaultImportSessionResponse } from "../../types";

const CHUNK_BYTES = 512 * 1024;
const MAX_VAULT_BYTES = 100 * 1024 * 1024;
const STORAGE_KEY = "thoughtpins.vault_import_session.v1";
const TERMINAL = new Set(["completed", "failed", "canceled", "expired"]);

export function VaultTransferPanel({ token }: { token: string }) {
  const [transfer, setTransfer] = useState<VaultImportSessionResponse | null>(null);
  const [conflictPolicy, setConflictPolicy] = useState<VaultConflictPolicy>("skip");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);

  useEffect(() => {
    const transferId = localStorage.getItem(STORAGE_KEY);
    if (!transferId) return undefined;
    const restoreController = new AbortController();
    void api.vaultImportSession(token, transferId, restoreController.signal)
      .then((restored) => {
        setTransfer(restored);
        setConflictPolicy(restored.conflict_policy);
        if (["completed", "canceled", "expired", "failed"].includes(restored.status)) {
          localStorage.removeItem(STORAGE_KEY);
        }
      })
      .catch((reason) => {
        if (!(reason instanceof DOMException && reason.name === "AbortError")) {
          localStorage.removeItem(STORAGE_KEY);
        }
      });
    return () => restoreController.abort();
  }, [token]);

  useEffect(() => () => controller.current?.abort(), []);

  const remember = useCallback((next: VaultImportSessionResponse) => {
    setTransfer(next);
    if (["completed", "canceled", "expired", "failed"].includes(next.status)) {
      localStorage.removeItem(STORAGE_KEY);
    } else {
      localStorage.setItem(STORAGE_KEY, next.id);
    }
    return next;
  }, []);

  const waitFor = useCallback(async (
    transferId: string,
    targets: Set<string>,
    signal: AbortSignal,
  ) => {
    const deadline = Date.now() + 30 * 60 * 1000;
    while (Date.now() < deadline) {
      const current = remember(await api.vaultImportSession(token, transferId, signal));
      if (targets.has(current.status)) return current;
      if (TERMINAL.has(current.status)) {
        throw new Error(current.error || `Vault import ended with status ${current.status}`);
      }
      await delay(700, signal);
    }
    throw new Error("Vault processing is still running. You can safely return to this page later.");
  }, [remember, token]);

  const beginUpload = async (file: File | null) => {
    if (!file || busy) return;
    if (!file.name.toLocaleLowerCase().endsWith(".zip")) {
      setError("Choose an Obsidian vault ZIP archive.");
      return;
    }
    if (file.size < 1 || file.size > MAX_VAULT_BYTES) {
      setError("Vault ZIPs must be between 1 byte and 100 MB.");
      return;
    }

    controller.current?.abort();
    const nextController = new AbortController();
    controller.current = nextController;
    setBusy(true);
    setError("");
    try {
      let current = transfer;
      if (
        !current
        || current.status !== "uploading"
        || current.filename !== file.name
        || current.expected_bytes !== file.size
      ) {
        if (current && !TERMINAL.has(current.status)) {
          await api.cancelVaultImport(token, current.id).catch(() => undefined);
        }
        current = remember(await api.createVaultImportUpload(
          token,
          file,
          "auto",
          conflictPolicy,
          nextController.signal,
        ));
      }
      let offset = current.received_bytes;
      while (offset < file.size) {
        const chunk = file.slice(offset, Math.min(file.size, offset + CHUNK_BYTES));
        current = remember(await api.appendVaultImportChunk(
          token,
          current.id,
          offset,
          chunk,
          nextController.signal,
        ));
        offset = current.received_bytes;
      }
      current = remember(await api.previewVaultImport(
        token,
        current.id,
        conflictPolicy,
        nextController.signal,
      ));
      if (current.status !== "preview_ready") {
        await waitFor(current.id, new Set(["preview_ready"]), nextController.signal);
      }
    } catch (reason) {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) {
        setError(errorMessage(reason));
      }
    } finally {
      setBusy(false);
    }
  };

  const applyImport = async () => {
    if (!transfer || transfer.status !== "preview_ready" || busy) return;
    controller.current?.abort();
    const nextController = new AbortController();
    controller.current = nextController;
    setBusy(true);
    setError("");
    try {
      const queued = remember(await api.applyVaultImport(
        token,
        transfer.id,
        conflictPolicy,
        nextController.signal,
      ));
      await waitFor(queued.id, new Set(["completed"]), nextController.signal);
    } catch (reason) {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) {
        setError(errorMessage(reason));
      }
    } finally {
      setBusy(false);
    }
  };

  const cancelImport = async () => {
    controller.current?.abort();
    setBusy(false);
    if (!transfer || TERMINAL.has(transfer.status)) return;
    try {
      remember(await api.cancelVaultImport(token, transfer.id));
    } catch (reason) {
      setError(errorMessage(reason));
    }
  };

  const result = transfer?.result;
  return (
    <div className="form-stack vault-transfer">
      <div className="two-col">
        <label>
          Changed notes
          <select
            value={conflictPolicy}
            disabled={busy || transfer?.status === "preview_ready"}
            onChange={(event) => setConflictPolicy(event.target.value as VaultConflictPolicy)}
          >
            <option value="skip">Skip for review</option>
            <option value="append">Add as revisions</option>
          </select>
        </label>
        <label>
          Import Obsidian vault
          <input
            aria-label="Import Obsidian vault ZIP"
            type="file"
            accept=".zip,application/zip"
            disabled={busy}
            onChange={(event) => {
              void beginUpload(event.target.files?.[0] || null);
              event.currentTarget.value = "";
            }}
          />
        </label>
      </div>
      <span className="field-help"><FileUp size={14} /> ZIP archives only. Thought Pins previews every change before saving it.</span>
      {transfer && (
        <div className="vault-transfer-progress" role="status" aria-live="polite">
          <div className="button-row wrap">
            <StatusPill status={transfer.status} />
            <span>{humanStage(transfer.progress_stage)}</span>
            <strong>{Math.round(transfer.progress_percent)}%</strong>
          </div>
          <progress max={100} value={transfer.progress_percent} aria-label="Vault import progress" />
          {transfer.status === "uploading" && (
            <span className="field-help">Choose the same file again to resume from {formatBytes(transfer.received_bytes)}.</span>
          )}
        </div>
      )}
      {result && (
        <div className="import-summary" role="status">
          <KeyValue label="Detected" value={result.thoughtpins_export ? "Thought Pins vault" : "Obsidian vault"} />
          <KeyValue label="New" value={result.new_notes} />
          <KeyValue label="Changed" value={result.changed_notes} />
          <KeyValue label="Unchanged" value={result.unchanged_notes} />
          <KeyValue label="Journal" value={result.journal_notes} />
          <KeyValue label="Library" value={result.library_notes} />
          <KeyValue label="Canvases" value={result.canvases_discovered} />
          <KeyValue label="Conflicts" value={result.conflicts} />
        </div>
      )}
      {result?.preview_items.length ? (
        <div className="vault-preview-list" aria-label="Vault import preview">
          {result.preview_items.slice(0, 8).map((item) => (
            <div className="device-row" key={`${item.path}:${item.action}`}>
              <div><strong>{item.title}</strong><span>{humanAction(item.action)} - {item.kind}</span></div>
              <StatusPill status={item.state} />
            </div>
          ))}
          {result.preview_items.length > 8 && <span className="field-help">Showing 8 of {result.preview_items.length} preview rows.</span>}
        </div>
      ) : null}
      {error && <p className="inline-error" role="alert">{error}</p>}
      <div className="button-row wrap">
        {transfer?.status === "preview_ready" && (
          <PrimaryButton onClick={applyImport} disabled={busy}>Apply import</PrimaryButton>
        )}
        {transfer && !TERMINAL.has(transfer.status) && (
          <SecondaryButton onClick={cancelImport}><X size={16} /> {transfer.status === "preview_ready" ? "Discard" : "Cancel"}</SecondaryButton>
        )}
        {transfer && TERMINAL.has(transfer.status) && (
          <SecondaryButton onClick={() => { setTransfer(null); setError(""); localStorage.removeItem(STORAGE_KEY); }}>
            <RotateCcw size={16} /> New import
          </SecondaryButton>
        )}
      </div>
    </div>
  );
}

function delay(milliseconds: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const onAbort = () => {
      window.clearTimeout(timeout);
      reject(new DOMException("Canceled", "AbortError"));
    };
    const timeout = window.setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, milliseconds);
    if (signal.aborted) {
      onAbort();
      return;
    }
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

function errorMessage(error: unknown) {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Vault processing failed. Your existing memories were not changed.";
}

function humanStage(stage: string) {
  return stage.replaceAll("_", " ").replace(/^./, (value) => value.toUpperCase());
}

function humanAction(action: string) {
  return ({
    import: "Will import",
    skip_duplicate: "Already imported",
    skip_conflict: "Needs review",
    append_revision: "Will add revision",
  } as Record<string, string>)[action] || humanStage(action);
}

function formatBytes(value: number) {
  if (value < 1024 * 1024) return `${Math.max(0, Math.round(value / 1024))} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}
