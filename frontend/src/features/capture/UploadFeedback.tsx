import type { UploadIngestResponse } from "../../types";
import { uploadOutcome } from "../../core/upload";

export function UploadFeedback({ result }: { result: UploadIngestResponse | null }) {
  if (!result) return null;
  const outcome = uploadOutcome(result);
  return <div className={`upload-feedback ${outcome.tone}`} role="status" aria-live="polite">
    <strong>{outcome.title}</strong>
    <div>{result.filename}</div>
    <p>{outcome.text}</p>
  </div>;
}
