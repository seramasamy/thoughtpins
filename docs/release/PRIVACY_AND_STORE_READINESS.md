# Thought Pins Privacy and Store Readiness

This is the launch-readiness checklist for App Store and Play Store submission.
It is not legal advice; it is the engineering checklist the product must satisfy
before beta or public launch.

Official references checked on 2026-07-13:

- Apple App Privacy Details: https://developer.apple.com/help/app-store-connect/manage-app-information/provide-app-privacy-details
- Apple User Privacy and Data Use: https://developer.apple.com/app-store/user-privacy-and-data-use/
- Apple account deletion guidance: https://developer.apple.com/support/offering-account-deletion-in-your-app/
- Apple App Review Guidelines: https://developer.apple.com/app-store/review/guidelines/
- Google Play User Data policy: https://support.google.com/googleplay/android-developer/answer/10144311
- Google Play account deletion requirements: https://support.google.com/googleplay/android-developer/answer/13327111
- Google Play Data safety form guidance: https://support.google.com/googleplay/android-developer/answer/10787469

## Machine-Checked Store Packet

The store submission packet lives at `deploy/store/submission-packet.json` and is validated by `python scripts/check_store_submission_packet.py`. The generated traceability artifact is `reports/store-readiness-matrix-*.md`; create it with `python scripts/generate_store_readiness_matrix.py` after evidence collection and validate the generator with `python scripts/check_store_readiness_matrix.py --self-test`. The machine-readable policy map lives at `deploy/store/store-policy-requirements.json` and ties current Apple/Google requirements to local gates for review access, live backend, privacy disclosures, account deletion, login parity, data safety, secure handling, and no founder/test leakage. Together they cover public URLs, review-account procedure, Apple/Google gates, data-safety inventory, permission rationale, AI/provider disclosure, public-build exclusions, and evidence commands. They intentionally store no review password or provider secrets. The reviewer-facing notes template lives at `deploy/store/review-notes-template.md` and is validated by `python scripts/check_review_notes_packet.py`; it explains demo access, live-backend expectations, AI/provider behavior, export/delete paths, maintenance behavior, and the native handoff status without storing credentials.

## Initial Commerce Posture

The initial public release is entirely free: no subscription, in-app purchase,
external checkout, advertising, or paid-feature switch ships in any client.
`deploy/store/commerce-policy.json` records that contract and
`scripts/check_free_launch.py` scans dependency manifests and user interfaces
for accidental paid-product plumbing. Operational rate limits may protect the
service but cannot unlock a paid tier. See `FREE_LAUNCH_POLICY.md` for the change
control required before any future monetized release.

## Data Inventory

Thought Pins currently handles:

- Account data: email, display name, auth sessions, OAuth profile identifiers.
- Journal content: raw entries, private/confidential flags, extracted memories,
  people, places, events, relationships, action items, and expenses.
- Operational data: request IDs, audit events, job status, rate-limit state,
  health metrics, crash/error telemetry when Sentry is enabled.
- Optional Telegram adapter data: Telegram chat/user IDs and Telegram message
  metadata in local test mode or explicit Telegram deployments.
- Optional export data: JSON account export and Obsidian files.
- User-imported Obsidian data: Markdown note text, paths, bounded typed
  properties, wikilinks, and readable content/connections from user-authored
  JSON Canvas files. Base query definitions and non-note attachments are not
  imported as content.
- Optional Audio Data: user-initiated voice notes are temporary in the public
  store configuration. Recognizable recordings can be retained only in an
  explicitly enabled private/self-hosted deployment after separate versioned
  consent, encrypted under a tenant-scoped opaque reference, and excluded from normal
  JSON and Obsidian exports.

Microphone access is implemented only for user-initiated voice notes, with an
in-app disclosure before the platform permission prompt. Do not add analytics,
advertising SDKs, contact upload, location, broad photo access, or notification
tracking unless the privacy policy and store forms are updated first.

## Required User Controls

Already supported by the backend:

- Account export: `GET /v1/export`.
- Account deletion: `DELETE /v1/me` with `{"confirm":"DELETE"}`.
- Entry deletion: `DELETE /v1/entries/{entry_id}`.
- Logout: `POST /v1/auth/logout`.
- Safety report creation: `POST /v1/safety/reports` for unsafe AI output, harmful content, privacy, rights, abuse, self-harm/crisis, security, or other concerns.
- Obsidian vault download: `GET /v1/export/vault/download`.
- Obsidian vault import: `POST /v1/import/obsidian`; imported data is included
  in normal account export and deletion boundaries.
- Deployment-gated personal voice archive status: `GET /v1/voice-archive`.
- Explicit voice retention consent: `POST /v1/voice-archive/consent`.
- Stop future voice retention: `DELETE /v1/voice-archive/consent`.
- Delete retained audio and derived voice data: `DELETE /v1/voice-archive` with
  `{"confirm":"DELETE VOICE ARCHIVE"}`.

Still required before store submission:

- Public privacy policy URL.
- Public account deletion URL for Google Play, even if deletion also exists in
  the app.
- Final legal review and deployment of the existing in-app privacy, account
  deletion, support, and AI disclosure paths.
- Support email or support web form.
- Store review test account.
- Production values for `PRIVACY_POLICY_URL`, `TERMS_URL`, `SUPPORT_URL`,
  `ACCOUNT_DELETION_URL`, and `AI_DISCLOSURE_URL`.

## Privacy Policy Commitments

The public policy should state:

- Journal content is used to provide journaling, memory extraction, search,
  context, exports, and AI answers.
- Journal content is sent to the configured LLM provider for processing unless a
  future local-only mode is selected.
- Journal content is not sold.
- Journal content is not used for advertising.
- Journal content is not used to train third-party foundation models by
  Thought Pins.
- Voice recordings are discarded after transcription by default. Optional
  encrypted retention requires separate consent and is limited to future
  personal voice features for the same account, never a shared or other-user
  model.
- Users can export and delete their account data.
- User-provided vault notes are processed for journal/library classification,
  retrieval, and memory extraction under the same policy as directly entered
  content.
- Private entries and every object derived solely from them are omitted from
  portable Obsidian exports, including generated views and the memory Canvas.
- Some operational logs and audit events may be retained for security,
  reliability, fraud prevention, and legal compliance.
- Private/confidential entries receive additional backend controls and should not
  be exposed to normal Ask context unless explicitly allowed by policy.

## Local Device Storage Boundary

Native clients should be server-canonical and store only a narrow encrypted local layer: refresh tokens in Keychain or Android Keystore-backed storage, offline draft queues, upload retry metadata, recent conversation/cache data, legal acceptance cache, and last-known maintenance/client-config state. Do not store provider API keys, permanent backend API keys for normal users, other users' data, or an unbounded full-memory mirror unless the user explicitly exports or opts into a future local-only mode.

Detailed implementation rules live in `../architecture/LOCAL_DEVICE_STORAGE.md`.
## Web Readiness Before Native

Before starting store submission work, the backend-served web app must exercise
all user-visible compliance flows: signup/login, chat, explicit capture, memory
cards, library ingestion, export, account deletion, legal links, safety reporting, AI disclosure,
and version/minimum-client policy. The Playwright review harness must prove
article-link ingestion, file upload, memory provenance/vault paths, export, and
in-app account deletion against the public UI. This keeps iOS and Android UI work
focused on native presentation instead of discovering missing backend/product
contracts during review.
## Review Account Procedure

Seed a non-founder review account in staging after migrations are current and
before submitting TestFlight or Play internal testing notes:

```powershell
$env:THOUGHTPINS_REVIEW_EMAIL="review@thoughtpins.com"
$env:THOUGHTPINS_REVIEW_PASSWORD="<store-review-password>"
python scripts/seed_review_account.py --export-vault --zip-vault
```

The password is read from `THOUGHTPINS_REVIEW_PASSWORD` and is not printed by the
CLI. The seeded data is fictional and covers safe journal, article, entity,
relationship, chat, export, vault, and deletion flows. Regenerate it whenever the
staging database is rebuilt, then put the credentials only in the private store
review notes. Validate the sanitized notes before submission with `python scripts/check_review_notes_packet.py`; then copy the template into App Store Connect or Play Console and add only the private password in the store console.

## App Store Readiness

Before TestFlight:

- Apple Developer account is active.
- Bundle ID is reserved.
- Privacy policy URL is live.
- Sign in with Apple entitlement and UI are present; complete a signed end-to-end
  token exchange test on macOS before enabling third-party login in review.
- Account deletion is available inside the app if account creation is available.
- App Privacy Details in App Store Connect match actual data collection.
- Review notes include a test account and a short explanation of AI processing.
- No owner-only local adapter controls are exposed in production builds.

Apple privacy label draft:

- Data Linked to User: contact info/account email, user content/journal entries,
  user-initiated Audio Data during transcription, identifiers/user ID, diagnostics if
  Sentry is enabled.
- Not Used for Tracking: no advertising tracking or cross-app tracking in v1.
- Data Not Collected: precise location, contacts, broad photo-library data,
  camera data, health data, and payment information. Microphone audio is
  collected only when the user records a voice note.

## Play Store Readiness

Before internal testing:

- Google Play developer account is active.
- Package name is reserved.
- Privacy policy URL is live and public.
- Account deletion web URL is live and references Thought Pins clearly.
- Data Safety form matches actual backend, LLM, crash reporting, and auth SDK
  behavior.
- In-app account deletion path is implemented.
- Review credentials are available.

Google Data safety draft:

- Data collected: account email, user content, app interactions/diagnostics when
  enabled, user-initiated audio during transcription, identifiers for auth/session/account
  linkage.
- Data shared: configured AI and transcription processors for user-requested
  processing, Sentry if enabled, and OAuth providers for sign-in. Do not list
  unused providers.
- Security practices: encrypted in transit, account deletion available, data
  export available.

## Production Secrets

Rotate before beta:

- Configured LLM API key.
- Private local adapter token, if any.
- JWT secret.
- API bootstrap key.
- Fernet `DATA_ENCRYPTION_KEY` if it was ever exposed.
- Hosted `TRANSCRIPTION_API_KEY`, if external transcription is enabled.

Rules:

- Never commit `.env`.
- Never paste production tokens into chat or issue trackers.
- Use provider-managed secret storage for staging and production.
- Sentry must scrub request bodies and authorization headers.

## Store Build Profiles

Use separate runtime flags:

- Local founder test: Telegram enabled, founder test mode enabled, no public
  signup.
- Staging mobile: private local adapters disabled, OAuth enabled,
  Sentry enabled, PostgreSQL/Redis/Celery enabled.
- Production mobile: same as staging, with public signup rules finalized and
  production privacy policy URLs live.

## Platform Launch Order

Use a web-first path, then native beta:

1. Ship the backend and `/app` web client as the first production surface.
   This proves signup, chat, capture, memory recall, export/delete, legal links,
   and operations without App Store or Play Store review latency.
2. Build iOS and Android UI apps on top of the existing shared mobile core
   modules only after the web app exercises the full `/v1` contract cleanly.
3. Keep the personal mini-PC adapter as a separate private project that calls
   the public `/v1` API. It must not appear in production mobile or public web
   builds.
4. Use one sanitized monorepo for GitHub: backend, frontend, mobile core,
   migrations, tests, deploy templates, docs, and public store artifacts. Do not
   include `.env`, local data, logs, vaults, backups, caches, private adapter
   configuration, or private run logs.
5. Before any native store submission, complete public legal URLs, account
   deletion, review credentials, privacy/data safety declarations, and AI
   disclosure in both app UI and store metadata.

## Launch Blockers

Do not submit to App Store or Play Store until:

- `python scripts/release_check.py` passes.
- PostgreSQL RLS verification passes against the exact non-owner app role.
- Staging smoke test passes.
- k6 health and API flow tests pass against staging.
- Backup restore drill has been completed.
- Privacy policy and account deletion web URL are live.
- Review/test accounts are documented.
- The pasted local model-provider and private-adapter credentials have been rotated.
