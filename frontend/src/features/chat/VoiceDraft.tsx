import { useEffect, useMemo, useState } from "react";
import { PrimaryButton, SecondaryButton } from "../../components/ui";
import { useExclusiveAction } from "../../components/useExclusiveAction";

export function VoiceDraft({ file, onSave, onDiscard, busy }: {
  file: File; busy: boolean;
  onSave: (destination: "journal" | "library", key: string) => Promise<void>;
  onDiscard: () => void;
}) {
  const [url, setUrl] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [destination, setDestination] = useState<"journal" | "library">("journal");
  const { pending, perform } = useExclusiveAction();
  const key = useMemo(() => crypto.randomUUID(), [file, destination]);
  useEffect(() => {
    const preview = URL.createObjectURL(file);
    setUrl(preview);
    return () => URL.revokeObjectURL(preview);
  }, [file]);
  return <section className="voice-draft" aria-label="Review voice note">
    <strong>Review your recording</strong>
    <p>{attempted ? "Your recording stays here until saving succeeds or you discard it." : "Nothing has been uploaded yet. Listen back, then save for transcription or discard."}</p>
    <audio controls src={url || undefined} aria-label="Recording preview" />
    <label>Save recording as<select value={destination} disabled={pending || busy}
      onChange={event => setDestination(event.target.value as "journal" | "library")}>
      <option value="journal">Personal journal</option><option value="library">Reference source or lecture</option>
    </select></label>
    <div className="row-actions">
      <SecondaryButton aria-label="Discard recording" disabled={pending || busy} onClick={onDiscard}>Discard</SecondaryButton>
      <PrimaryButton disabled={pending || busy} onClick={() => void perform(async () => { setAttempted(true); await onSave(destination, key); })}>
        {pending ? "Transcribing…" : "Save recording"}
      </PrimaryButton>
    </div>
  </section>;
}
