import type { UploadIngestResponse } from "../types";

export const UPLOAD_MAX_BYTES = 25 * 1024 * 1024;
export const UPLOAD_ACCEPT = ".txt,.md,.markdown,.csv,.json,.log,.pdf,.jpg,.jpeg,.png,.webp,.bmp,.tif,.tiff,.ogg,.oga,.mp3,.m4a,.wav,.webm,.aac,.flac";
export const UPLOAD_HELP = "PDF with selectable text, text notes, images, or audio. Up to 25 MB per file.";

export function validateUpload(file: Pick<File, "name" | "size">): void {
  if (!file.size) throw new Error("This file is empty. Choose a file with content.");
  if (file.size > UPLOAD_MAX_BYTES) throw new Error("This file exceeds 25 MB. Choose a smaller file.");
  const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
  if (!UPLOAD_ACCEPT.split(",").includes(extension)) {
    throw new Error("This file format is not supported yet. Export it to a PDF with selectable text, or paste its text.");
  }
}

export type UploadOutcome = { tone: "ok" | "warn" | "error"; title: string; text: string; saved: boolean };

export function uploadOutcome(result: UploadIngestResponse): UploadOutcome {
  const saved = Boolean(result.document_id || result.entry_id || result.job_id);
  if (["failed", "error", "dead_letter"].includes(result.status)) {
    return { tone: "error", title: "Processing failed", saved,
      text: result.error || "Processing failed. Check Processing activity before relying on recall." };
  }
  if (result.status === "needs_text" || !saved) {
    return { tone: "warn", title: "Readable text needed", saved: false,
      text: result.error || "No readable text was extracted. Add the text or choose a clearer file. This file is not available for recall." };
  }
  const destination = result.destination === "journal" ? "journal" : "source library";
  const metadata = result.metadata?.extraction;
  const warnings = metadata && typeof metadata === "object" && "warnings" in metadata && Array.isArray(metadata.warnings)
    ? metadata.warnings.filter((value): value is string => typeof value === "string") : [];
  if (result.extraction_status !== "processed" && result.extraction_status !== "ok") {
    return { tone: "warn", title: "Partially read", saved: true,
      text: warnings.join(" ") || `Saved to your ${destination}, but some file content could not be read. Only the extracted text or your accompanying note is available.` };
  }
  if (["queued", "pending", "processing", "running"].includes(result.status) || result.job_id) {
    return { tone: "ok", title: "Saved, still processing", saved: true,
      text: `Saved to your ${destination}. It will be available for recall once processing finishes.` };
  }
  if (!["processed", "ok", "completed"].includes(result.status)) {
    return { tone: "warn", title: "Check processing status", saved,
      text: "Your source was received, but readiness is not confirmed. Check Processing activity before relying on recall." };
  }
  return { tone: "ok", title: "Ready", saved: true,
    text: `Read ${result.extracted_chars.toLocaleString()} characters and saved to your ${destination}.` };
}
