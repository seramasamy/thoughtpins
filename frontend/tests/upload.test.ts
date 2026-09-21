import assert from "node:assert/strict";
import test from "node:test";
import { UPLOAD_MAX_BYTES, uploadOutcome, validateUpload } from "../src/core/upload.ts";
import type { UploadIngestResponse } from "../src/types.ts";

const ready: UploadIngestResponse = {
  status: "processed", route_type: "library_upload", filename: "note.txt", media_kind: "document",
  destination: "library", extraction_status: "processed", extracted_chars: 42,
  attachment_saved: true, document_id: "source-1", metadata: {},
};

test("HTTP success without readable text is never presented as ready", () => {
  const outcome = uploadOutcome({ ...ready, status: "needs_text", document_id: null, extracted_chars: 0 });
  assert.equal(outcome.tone, "warn");
  assert.equal(outcome.saved, false);
  assert.match(outcome.text, /not available for recall/);
});

test("a retained caption cannot hide failed file extraction", () => {
  const outcome = uploadOutcome({ ...ready, extraction_status: "unsupported_binary_document" });
  assert.equal(outcome.title, "Partially read");
  assert.equal(outcome.tone, "warn");
  assert.match(outcome.text, /accompanying note/);
});

test("PDF truncation warnings survive status presentation", () => {
  const outcome = uploadOutcome({ ...ready, extraction_status: "partial", metadata: {
    extraction: { warnings: ["Only the first 100 of 101 pages were read.", 12] },
  } });
  assert.equal(outcome.text, "Only the first 100 of 101 pages were read.");
  assert.equal(outcome.tone, "warn");
});

test("queued, failed and unknown states cannot become a ready claim", () => {
  assert.equal(uploadOutcome({ ...ready, status: "queued", job_id: "job-1" }).title, "Saved, still processing");
  assert.equal(uploadOutcome({ ...ready, status: "failed", document_id: null }).tone, "error");
  assert.equal(uploadOutcome({ ...ready, status: "paused" }).tone, "warn");
  assert.equal(uploadOutcome({ ...ready, document_id: null }).tone, "warn");
  assert.equal(uploadOutcome(ready).title, "Ready");
});

test("file validation rejects unsupported and oversized inputs before encoding", () => {
  for (const name of ["essay.docx", "lecture.pptx", "camera.heic", "archive.zip", "unknown"]) {
    assert.throws(() => validateUpload({ name, size: 10 }), /format is not supported/);
  }
  assert.throws(() => validateUpload({ name: "scan.pdf", size: 0 }), /empty/);
  assert.throws(() => validateUpload({ name: "scan.pdf", size: UPLOAD_MAX_BYTES + 1 }), /25 MB/);
  assert.doesNotThrow(() => validateUpload({ name: "NOTES.PDF", size: UPLOAD_MAX_BYTES }));
});
