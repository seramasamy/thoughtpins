# Thought Pins App Core Foundation

This is the non-UI substrate for the future web, iOS, and Android clients. It
should stay stable while screens are designed.

## Backend Core

- `GET /v1/client-config`: runtime flags, legal URLs, OAuth availability, store
  URLs, minimum supported versions, and recommended client versions.
- `GET/PATCH /v1/preferences`: user preferences for notifications, reminder
  hour, timezone, private-entry ask policy, digest/product email flags, and
  preferred name.
- `POST /v1/legal/acceptances`: records accepted privacy, terms, and AI
  disclosure versions.
- `GET/POST/DELETE /v1/devices`: registers app installations and future push
  notification tokens without returning raw token material.
- `POST /v1/entries`, `GET /v1/jobs`, `GET /v1/entries`: capture, processing,
  and timeline primitives for every client.

## Frontend Core Modules

Pure TypeScript modules live under `frontend/src/core`:

- `storage.ts`: local, memory, and prefixed storage abstraction.
- `session.ts`: stored JWT session controller and local-mode detection.
- `webSession.ts`: browser session controller that keeps access tokens in
  memory and persists only refresh tokens.
- `validation.ts`: email, password, and journal-entry validation.
- `draftQueue.ts`: local capture draft queue with statuses and retry metadata.
- `encryptedDraftQueue.ts`: Web Crypto backed encrypted draft queue.
- `sync.ts`: draft queue sync runner over the ingestion API.
- `backgroundSync.ts`: periodic draft sync scheduler.
- `installation.ts`: stable web installation ID and device-registration
  payload builder.
- `runtime.ts`: startup bootstrap for client config, version gate, session, and
  device registration.
- `versionPolicy.ts`: minimum/recommended client version evaluation.

These modules intentionally contain no React components or visual styling. A
native client should mirror the same contracts with platform-secure storage:
Keychain on iOS and EncryptedSharedPreferences or equivalent on Android.

## Native Core Scaffolds

- `mobile/ios/ThoughtPinsCore`: Swift Package with API client, Keychain session
  storage, file-protected draft store, device registration models, and version
  policy.
- `mobile/android/thoughtpins-core`: Kotlin core module with API client, session
  store contracts, draft queue, device registration models, and version policy.

The release gate validates these scaffolds exist and remain UI-free through
`scripts/check_mobile_core.py`.

## Capture Flow Contract

1. Validate text locally.
2. Save a local draft before submitting.
3. Mark draft `queued`.
4. Submit to `POST /v1/entries`.
5. If the API returns `202`, keep the `job_id` and show processing state later.
6. Mark draft `synced` only after the API accepts it.
7. Retain failed drafts with `lastError` and `attemptCount`.

## Device Flow Contract

1. Generate one stable `installation_id` per install.
2. Register with `POST /v1/devices` after login or local-mode startup.
3. Send platform, app version, build number, OS version, locale, timezone, and
   notification state.
4. Send APNs/FCM/Web Push token only after platform permission is granted.
5. Revoke with `DELETE /v1/devices/{installation_id}` on logout or account
   deletion.

## Version Gate Contract

Every client reads `/v1/client-config` at startup:

- If current version is below `minimum_supported_clients[platform]`, block with
  an update-required state.
- If below `recommended_clients[platform]`, allow usage but surface an update
  recommendation.
- Use `store_urls[platform]` for update links when available.
