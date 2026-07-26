# Thought Pins Mobile API Contract

This is the first mobile contract for iOS, Android, and the web client. Keep it
stable for native app work. Add new behavior under `/v1` without changing
existing response shapes unless a migration note is added here.

## Product Navigation

The iOS, Android, and web shells use the same five primary destinations, in
this order: Recap, People, Chat, Places, and Pins. Chat occupies the center tab.
Settings, export and deletion, legal links, explicit capture, and operational
activity remain secondary actions. Native platform controls are preferred for
authentication, navigation, file selection, notifications, accessibility, and
maps handoff.

## Product Surfaces

- iOS app: SwiftUI client against `/v1`.
- Android app: Kotlin/Jetpack Compose client against `/v1`.
- Web client: backend-served `/app` reference client.
- Founder Telegram mode: local test adapter using the same ingestion, memory,
  query, and private-entry guard paths. It is not the production product UI.

## Session Model

Mobile clients use JWT sessions only:

1. `POST /v1/auth/register` when registration is open.
2. `POST /v1/auth/login` for email/password login.
3. `POST /v1/auth/oauth` for Google or Apple OIDC login.
4. Store `access_token` in memory when possible.
5. Store `refresh_token` in Keychain on iOS and EncryptedSharedPreferences or
   equivalent secure storage on Android.
6. On `401`, call `POST /v1/auth/refresh` once, retry the original request once,
   then sign out if refresh fails.
7. `POST /v1/auth/logout` revokes the refresh token.

Production clients must not use permanent user API keys. `X-API-Key` is for
local/bootstrap/server workflows only.

## Required Client Screens

- Auth: login, register, Apple sign-in, Google sign-in, logout.
- Capture: create journal entry, keep offline draft until submit succeeds.
- Processing: job list, job detail, retry failed/dead-letter jobs, cancel pending
  jobs.
- Timeline: paginated entries, optional 1-5 importance rating, delete entry.
- Chat: primary message surface for chat, journal saves, memory questions,
  article/document links, search, undo, and command-like natural requests.
- Status: basic service status for support/debug builds.
- Account: export account data, delete account data.
- Legal: privacy policy, terms, AI disclosure, support contact, safety report form.
  The web reference client reads these URLs from `GET /v1/client-config`.

## Core Endpoints

### Runtime

- `GET /health`: public uptime check.
- `GET /v1/client-config`: public safe runtime flags for client setup,
  including `memory_context_mode` for support/debug display.
- `GET /v1/errors`: error envelope catalog.
- `GET /v1/health/deep`: authenticated support/debug health.

### Auth

- `POST /v1/auth/register`
- `POST /v1/auth/login`
- `POST /v1/auth/oauth`
- `POST /v1/auth/refresh`
- `POST /v1/auth/logout`
- `GET /v1/me`
- `DELETE /v1/me`
- `GET /v1/preferences`
- `PATCH /v1/preferences`
- `POST /v1/legal/acceptances`
- `GET /v1/devices`
- `POST /v1/devices`
- `DELETE /v1/devices/{installation_id}`
- `POST /v1/safety/reports`

### Journal

- `POST /v1/chat`
- `GET /v1/chat/conversations?page=1&limit=50`
- `GET /v1/chat/conversations/{conversation_id}/messages?page=1&limit=100`
- `POST /v1/entries`
- `GET /v1/entries?page=1&limit=50`
- `GET /v1/entries/{entry_id}`
- `GET /v1/entries/{entry_id}/status`
- `PATCH /v1/entries/{entry_id}/importance`
- `DELETE /v1/entries/{entry_id}`

### Jobs

- `GET /v1/jobs?page=1&limit=50&status=failed`
- `GET /v1/jobs/{job_id}`
- `POST /v1/jobs/{job_id}/retry`
- `POST /v1/jobs/{job_id}/cancel`

### Memory and Export

- `GET /v1/ask?q=...`
- `POST /v1/library`
- `POST /v1/uploads`
- `GET /v1/library`
- `GET /v1/library/{source_ref}`
- `POST /v1/import/obsidian`
- `GET /v1/status`
- `GET /v1/export`
- `POST /v1/export/obsidian`
- `GET /v1/export/vault/download`
- `GET /v1/personality`
- `GET /v1/context`
- `GET /v1/people/{name}`
- `GET /v1/places/{name}`
- `GET /v1/reports`
- `GET /v1/graph`

`/v1/chat` is the preferred app surface. `/v1/entries`, `/v1/library`, and
`/v1/ask` remain stable lower-level endpoints for explicit flows and admin/debug
tools. Chat clients should send the user's natural message as:

```json
{
  "text": "today I met Maya at Koyo and we talked about the launch",
  "conversation_id": "main",
  "surface": "ios"
}
```

Responses include `route_type`, `status`, `reply`, optional `entry_id` /
`job_id` / `document_id`, and `requires_confirmation` for risky actions such as
undo. If `requires_confirmation` is true, the response metadata includes
`pending_action_id`. Send the user's confirmation with:

```json
{
  "text": "confirm",
  "conversation_id": "main",
  "surface": "ios",
  "pending_action_id": "pending_abc123",
  "confirm_action": true
}
```

Clients can restore a thread by listing conversations, finding the desired
`conversation_key` such as `ios:main`, then fetching that conversation's
messages. These chat transcript rows are separate from journal entries; journal
memory still lives in entries, extracted memories, entities, and document
sources.

### Entry Importance

- `POST /v1/entries` accepts optional `user_importance` from 1 to 5.
- Entry responses include nullable `user_importance`, `importance_source`, and
  `importance_updated_at`.
- `PATCH /v1/entries/{entry_id}/importance` accepts a number from 1 to 5, or
  `null` to clear the rating. The endpoint is tenant-scoped.
- Clients must label this as user-selected importance, not confidence,
  accuracy, sentiment, or an AI-generated score.
- Optional post-save prompts use `importance_prompts_enabled` in preferences
  and remain off by default.
- Natural chat phrases such as "rate that five stars", "clear that rating",
  and "undo that rating" work without slash commands.
- Ratings modestly break retrieval ties and more strongly order recaps. They
  do not override direct textual evidence.
- Obsidian export/import preserves the plain YAML `importance` property.

### Obsidian Portability

Current clients use the resumable transfer protocol. Create a session with
`POST /v1/import/obsidian/uploads`, append sequential SHA-256-verified chunks
with `PUT .../{transfer_id}/chunks`, request `POST .../preview`, poll the
tenant-scoped session, and require explicit confirmation before
`POST .../apply`. `POST .../cancel` is valid during upload, preview, or apply.
The server persists offsets, progress, conflict policy, and bounded preview
rows so interrupted clients can resume by selecting the same file. Use
`mode: "auto"` in normal UI and offer `skip` or `append` for changed notes.

`POST /v1/import/obsidian` remains a bounded compatibility endpoint for old
clients and dry-run tooling; new clients must not buffer a large archive into a
single request. The final response separates new, changed, unchanged,
conflicting, duplicate, skipped, and imported notes. Journal imports continue
through the normal extraction queue. Native clients should use a document
picker and security-scoped read access; web clients should use a ZIP file
input. Export uses the authenticated `GET /v1/export/vault/download` binary
response and the platform share/save sheet. Responses also expose
`canvases_discovered`,
`canvas_documents_imported`, and `structural_files_skipped`; user-authored
Canvas content enters the library while Base definitions remain structural.
Do not unpack user archives on the client.

### Response Voice

- `GET /v1/preferences` returns `response_style`.
- `PATCH /v1/preferences` accepts `friendly`, `clear`, or `mirror`.
- Clients should label these choices `Friendly & professional`,
  `Clear & concise`, and `Match my style`.
- The default is `friendly`; style matching must remain an explicit user choice.
- Native chat surfaces should keep a visible, accessibility-announced
  `Thinking with your memory` state until the request completes.
- A send-key action submits a non-empty chat message; multiline clients reserve
  Shift+Enter for a line break where the platform supports it.

### Voice Notes and Personal Archive

- Clients show a concise disclosure before the first microphone permission
  prompt and keep a visible recording state while capture is active.
- Web captures Opus/WebM or AAC/MP4 where supported. Native clients capture
  mono AAC/M4A. Temporary client files are removed after bytes are read.
- `POST /v1/uploads` transcribes audio. Audio is ephemeral by default;
  `attachment_saved` is false and no filesystem reference is returned.
- `/v1/client-config` exposes `voice_archive_enabled`. Store clients hide every
  archive control when it is false; public release deployments keep it false.
- In a private/self-hosted deployment, `GET /v1/voice-archive` returns current
  consent, archive count, and byte totals.
- `POST /v1/voice-archive/consent` requires all four explicit acknowledgement
  fields. No checkbox may be preselected.
- `DELETE /v1/voice-archive/consent` stops future retention without silently
  deleting existing recordings.
- `DELETE /v1/voice-archive` with `DELETE VOICE ARCHIVE` permanently removes
  retained encrypted audio and future derived voice data. Journal transcripts
  remain ordinary entries until the user deletes them or the account.
- A successful retained upload returns only `voice_asset_id`; storage paths,
  hashes, binary data, and provider model names are never client-facing.
- Deleting the linked journal entry removes its retained recording. Account
  deletion removes every retained recording and future derived account-scoped
  voice artifact before the user record is removed. JSON and Obsidian exports
  contain transcripts and safe metadata, never audio bytes or storage details.

## Error Handling

All API errors use:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "request_id": "request-id",
    "details": []
  }
}
```

Mobile clients should show the message, log the `request_id` locally, and never
show raw stack traces. Treat these status codes specially:

- `401`: refresh token once, then sign out.
- `403`: show blocked/authz message.
- `413`: tell the user the entry is too large.
- `422`: client validation bug or invalid input.
- `429`: back off using `Retry-After` when present.
- `500`: show a generic retryable error and include request ID in support logs.

## Offline and Retry Rules

- Capture drafts locally before POST.
- If the device is offline, keep drafts in an encrypted local queue.
- Submit queued drafts in chronological order when connectivity returns.
- Do not run LLM extraction on-device in v1.
- If `POST /v1/entries` returns `202`, show processing state with the returned
  `job_id`.
- Poll job status with exponential backoff while the screen is visible.
- Use push notifications later for completed extraction; do not block launch on
  push.
- Register app installations with `/v1/devices`; only submit push tokens after
  user permission is granted.

## Privacy Defaults

- Private memories must use the backend private-entry policy.
- Keep private memories out of Ask unless the user explicitly enables private
  recall and the backend policy permits it.
- Do not log raw journal text in mobile analytics or crash reports.
- Do not send journal content to third-party mobile SDKs.
- Do not use journal data for model training.
- Do not expose raw APNs/FCM/Web Push tokens in client logs or account export.

## Versioning Rules

- Keep `/v1` stable through the first public release.
- Additive fields are allowed.
- Removing or renaming fields requires `/v2` or a documented deprecation period.
- iOS: increment both the marketing version and build string according to App
  Store Connect rules.
- Android: increment `versionCode` for every Play upload and keep
  `versionName` aligned with public release notes.
- Regenerate OpenAPI before each mobile release:

```powershell
python scripts/export_openapi.py --check
```

## Native Build Gate

Before writing native clients, the backend must pass:

```powershell
python scripts/release_check.py
```

Before public beta, also pass PostgreSQL RLS and staging smoke checks:

```powershell
python scripts/release_check.py --with-postgres-rls --api-base-url https://staging.example.com
```

## Native Core Scaffolds

- iOS starts from `mobile/ios/ThoughtPinsCore`, a Swift Package with no screens.
- Android starts from `mobile/android/thoughtpins-core`, a Kotlin core module
  with no Activity or Compose code.
- UI work should depend on these core modules for API, auth, draft, device, and
  version behavior.
## Native Review Handoff

The native store handoff lives at `deploy/store/native-review-handoff.json` and is checked by `python scripts/check_native_review_handoff.py`. It intentionally separates three states:

- web closed-beta handoff ready;
- native core modules ready;
- native App Store / Play Store submission not ready until real iOS and Android UI shells, signing, screenshots, and device tests exist.

Keep this file honest. Do not mark native store submission ready until the native apps implement the required review flows from the handoff JSON.
