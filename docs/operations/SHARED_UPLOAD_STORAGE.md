# Shared upload storage

Original files and resumable vault imports use PostgreSQL as their canonical
storage from migration `0027_vault_import_chunks`. API and worker instances do
not need a shared filesystem. Keep the database and its encryption key in the
existing backup and restore procedure.

| Data | Ownership and lifetime | Portability |
| --- | --- | --- |
| Original non-audio uploads | `stored_attachments`, explicit user FK and PostgreSQL RLS; tenant-scoped encrypted payload; random reference prevents filename collisions. Removed by account deletion, including uploads with no extractable text. | Account JSON includes a manifest; the vault ZIP includes the original bytes under `Attachments/`. |
| Resumable import bytes | `vault_import_chunks`, user and transfer scope; encrypted chunks, ordered offsets and digest checks. API and worker read the same committed bytes. Removed on apply, cancellation, expiry or account deletion. | Temporary input, not a separate user library. |
| Ordinary voice uploads | Ephemeral transcription; optional encrypted voice archive still requires separate consent. | Existing voice-archive controls apply. |
| Derived source processing | Source and enrichment job commit together before graph/model work. Broker interruptions leave a retryable durable job. | Source text and metadata remain available while enrichment runs. |

Encryption fails closed in production if the data key is unavailable. A failed
original-file cleanup cannot produce a successful account-deletion response.
Export also fails if original bytes cannot be decrypted or verified.

Automatic vault projections run only during synchronous local processing.
Production and asynchronous workers do not materialize them: the API cannot
delete a different host's decrypted `Attachments/` copy. Explicit API vault
exports remain available and their account-owned projection is covered by the
API filesystem cleanup. Inventory those projections on every host during
upgrades, including workers that ran earlier versions.

## Upgrading an existing deployment

1. Back up PostgreSQL and the original API filesystem before replacing any
   container. Inventory every API replica and worker. The historical path is
   `vault/09_Attachments/<category>/<timestamp>_<filename>`; these files did not
   contain reliable tenant identity and could collide within a second.
   Also inspect generated `vault/<user-id>/` projections and ZIPs on workers;
   earlier journal processing regenerated them automatically, including
   decrypted originals. Reconcile and remove obsolete generated copies before
   declaring the old worker filesystem retired. Preserve separately owned local
   vaults and user-edited material.
2. Match a legacy file to its owning source's `metadata_json.upload.attachment_ref`.
   Verify the bytes against any known original before copying them through
   `media.attachments.save_media_attachment` under the confirmed user's tenant
   context. Keep a private migration manifest. Do not assign ownership from the
   filename, and do not expose an ambiguous file through any account's export.
   Unattributed originals need operator reconciliation before discarding the
   old filesystem. For already-deleted accounts, remove verified residual bytes.
3. Apply migration 0027 with the migration role, then deploy API and worker from
   the same revision. RLS and application-role grants cover both new tables.
   Check database capacity: originals and staging bytes now count toward its
   storage and backups. Encrypted bytes consume more space than the input.
4. For an active legacy vault upload, keep the old API filesystem until the
   transfer has resumed or requested preview. That API adopts its staged bytes
   into shared storage. Preview on an independent worker verifies the handoff.
5. Export an original, import a generated vault, delete a disposable account,
   and check both tables under tenant A and tenant B.

Downgrade refuses to drop either populated table. Cancel or expire staged
transfers; migrate and verify originals in replacement storage before removing
their rows. Keeping the forward schema while rolling back application code is
preferable to dropping durable user uploads. Never bypass the refusal with a
forced table drop.

## Runtime extraction

The production lock includes pypdf and Pillow. The image includes Tesseract and
its English language data; OCR uses a 30-second subprocess budget and one CPU
thread. No OCR model is downloaded on a person's first upload. Images above
25 million pixels are rejected for extraction; the existing 25 MB upload limit
still applies. Text PDFs are read up to the existing 100-page limit. Scanned
PDFs without a text layer need a text transcript; image OCR currently reads
English, not every writing system.

The container build runs `python scripts/check_media_runtime.py` against a
generated PDF and image. A package merely importing is insufficient evidence
that either format can actually be read.

Regression coverage lives in `tests/test_attachment_ownership.py`,
`tests/test_vault_chunk_storage.py`, `tests/test_vault_import.py`,
`tests/test_shared_storage_migration.py`, and `tests/test_library_enrichment.py`.
`tests/test_worker_vault_privacy.py` verifies the automatic-projection boundary,
explicit export and deletion across separate API and worker filesystem roots.
The live PostgreSQL isolation verifier also checks both storage tables.
