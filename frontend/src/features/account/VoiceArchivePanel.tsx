import { Mic2, ShieldCheck, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import type { Runner } from "../../app/types";
import type { VoiceArchiveConsentRequest, VoiceArchiveStatusResponse } from "../../types";
import { Panel, PanelTitle, PrimaryButton, SecondaryButton, StatusPill } from "../../components/ui";
import "./voice-archive.css";

const EMPTY_CONSENT: VoiceArchiveConsentRequest = {
  retain_recordings: false,
  acknowledge_sensitive_audio: false,
  acknowledge_personal_use_only: false,
  acknowledge_deletion_available: false,
};

export function VoiceArchivePanel({ token, run }: { token: string; run: Runner }) {
  const [status, setStatus] = useState<VoiceArchiveStatusResponse | null>(null);
  const [showConsent, setShowConsent] = useState(false);
  const [consent, setConsent] = useState<VoiceArchiveConsentRequest>(EMPTY_CONSENT);
  const [showDelete, setShowDelete] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");

  const load = useCallback(async () => {
    const next = await run(() => api.voiceArchive(token));
    if (next) setStatus(next);
  }, [run, token]);

  useEffect(() => {
    void load();
  }, [load]);

  const enable = async () => {
    const next = await run(() => api.enableVoiceArchive(token, consent), "Voice archive enabled");
    if (!next) return;
    setStatus(next);
    setConsent(EMPTY_CONSENT);
    setShowConsent(false);
  };

  const disable = async () => {
    const next = await run(() => api.disableVoiceArchive(token), "Future voice retention disabled");
    if (next) setStatus(next);
  };

  const deleteArchive = async () => {
    if (deleteConfirmation !== "DELETE VOICE ARCHIVE") return;
    const result = await run(() => api.deleteVoiceArchive(token), "Voice archive deleted");
    if (!result) return;
    setShowDelete(false);
    setDeleteConfirmation("");
    await load();
  };

  const allConfirmed = Object.values(consent).every(Boolean);

  return (
    <Panel className="voice-archive-panel">
      <PanelTitle
        icon={<Mic2 size={18} />}
        title="Personal voice archive"
        action={status ? <StatusPill status={status.enabled ? "enabled" : "disabled"} /> : undefined}
      />
      <p className="voice-archive-lede">
        Voice notes are transcribed and the recording is discarded by default. You can separately retain encrypted recordings for future personal voice features.
      </p>

      {status && (
        <div className="voice-archive-stats" aria-label="Voice archive status">
          <span><strong>{status.asset_count}</strong> recordings</span>
          <span><strong>{formatBytes(status.original_bytes)}</strong> original size</span>
        </div>
      )}

      {!status?.enabled && !showConsent && (
        <PrimaryButton type="button" onClick={() => setShowConsent(true)}>
          <ShieldCheck size={16} /> Review and enable
        </PrimaryButton>
      )}

      {showConsent && (
        <div className="voice-consent" role="group" aria-label="Voice archive consent">
          <strong>Review before enabling</strong>
          <p>Recordings can identify you. This archive is for features built only for your account and is not used to train a shared model or another user&apos;s model.</p>
          <ConsentCheck label="Retain future voice-note recordings after transcription." checked={consent.retain_recordings} onChange={(value) => setConsent((current) => ({ ...current, retain_recordings: value }))} />
          <ConsentCheck label="I understand voice recordings are sensitive and identifying." checked={consent.acknowledge_sensitive_audio} onChange={(value) => setConsent((current) => ({ ...current, acknowledge_sensitive_audio: value }))} />
          <ConsentCheck label="Use retained recordings only for my personal voice features." checked={consent.acknowledge_personal_use_only} onChange={(value) => setConsent((current) => ({ ...current, acknowledge_personal_use_only: value }))} />
          <ConsentCheck label="I can disable retention or permanently delete the archive at any time." checked={consent.acknowledge_deletion_available} onChange={(value) => setConsent((current) => ({ ...current, acknowledge_deletion_available: value }))} />
          <div className="button-row wrap">
            <PrimaryButton type="button" disabled={!allConfirmed} onClick={enable}>Enable archive</PrimaryButton>
            <SecondaryButton type="button" onClick={() => { setShowConsent(false); setConsent(EMPTY_CONSENT); }}>Cancel</SecondaryButton>
          </div>
        </div>
      )}

      {status?.enabled && (
        <div className="voice-archive-actions">
          <SecondaryButton type="button" onClick={disable}>Stop future retention</SecondaryButton>
          <span>Existing recordings stay encrypted until you delete them.</span>
        </div>
      )}

      {(status?.asset_count || 0) > 0 && !showDelete && (
        <button className="text-danger-button" type="button" onClick={() => setShowDelete(true)}>
          <Trash2 size={16} /> Delete retained recordings
        </button>
      )}
      {showDelete && (
        <div className="voice-delete-confirm" role="group" aria-label="Delete voice archive">
          <strong>Delete all retained recordings?</strong>
          <p>This removes encrypted audio and future derived voice data. Journal transcripts remain until you delete their entries or your account.</p>
          <label>Type DELETE VOICE ARCHIVE<input value={deleteConfirmation} onChange={(event) => setDeleteConfirmation(event.target.value)} autoComplete="off" /></label>
          <div className="button-row wrap">
            <button className="danger-button" type="button" disabled={deleteConfirmation !== "DELETE VOICE ARCHIVE"} onClick={deleteArchive}><Trash2 size={16} /> Delete archive</button>
            <SecondaryButton type="button" onClick={() => { setShowDelete(false); setDeleteConfirmation(""); }}>Cancel</SecondaryButton>
          </div>
        </div>
      )}
    </Panel>
  );
}

function ConsentCheck({ label, checked, onChange }: { label: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return <label className="voice-consent-check"><input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} /><span>{label}</span></label>;
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}
