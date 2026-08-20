# Thought Pins Local Device Storage

Thought Pins should be server-canonical for multi-device memory, but app-grade clients need a small encrypted local layer for resilience and review quality.

## Storage Boundary

Local app storage may hold:

- Access token in memory only when practical.
- Refresh token in platform secure storage.
- Offline draft queue for unsent journal/chat/library messages.
- Upload retry metadata for user-selected files.
- Recent conversation and memory-card cache for fast navigation.
- Legal acceptance cache and non-sensitive preferences.
- Last-known maintenance/client-config state.

Local app storage must not hold:

- Provider API keys.
- Permanent backend API keys for normal users.
- Other users' data.
- Unbounded full-memory mirrors unless the user explicitly chooses a local export/offline mode.
- Hidden owner/test controls.

## Current Code Hooks

- iOS session storage: `mobile/ios/ThoughtPinsCore/Sources/ThoughtPinsCore/SessionStore.swift`.
- iOS draft queue: `mobile/ios/ThoughtPinsCore/Sources/ThoughtPinsCore/DraftStore.swift`.
- Android session/draft integration: `mobile/android/thoughtpins-app/src/main/kotlin/com/thoughtpins/app/AndroidSecureStores.kt`.
- Android draft queue contract: `mobile/android/thoughtpins-core/src/main/kotlin/com/thoughtpins/core/DraftQueue.kt`.
## iOS

- Store refresh tokens in Keychain with the narrowest access group possible.
- Store offline drafts in an encrypted SQLite/Core Data store or protected app-container files using `NSFileProtectionComplete` where practical.
- Mark sensitive caches as excluded from iCloud backup unless the user explicitly enables platform backup/sync behavior.
- Keep the access token in memory; refresh on launch from Keychain.
- Use user-selected document/photo pickers rather than broad library access.
- Queue writes while offline or during maintenance and replay after `GET /v1/client-config` and `/health` recover.

## Android

- Store refresh tokens in Android Keystore-backed encrypted preferences or an equivalent secure store.
- Store offline drafts in Room with SQLCipher or encrypted app-private files.
- Exclude sensitive caches from Auto Backup unless the user explicitly opts in.
- Keep access tokens in memory; refresh on launch from secure storage.
- Use Android Photo Picker / Storage Access Framework for user-selected imports.
- Queue writes while offline or during maintenance and replay after client-config/health recovery.

## Web

- Store sessions in browser storage only for the closed beta reference client; production web should prefer short sessions and hardened cookie/session strategy if deployed publicly.
- Keep offline drafts small and user-visible.
- Never store provider keys in frontend code.

## Export Mode

Export is explicit user action, not a background local mirror. The Obsidian-compatible vault export should contain Markdown notes, indexes, source metadata, provenance, and attachments needed to open the export in Obsidian without Thought Pins.

## Review Implication

This local-storage boundary supports Apple data minimization: the app requests only data and permissions relevant to the core memory workflow, keeps sensitive authentication material in platform-secure storage, and provides export/delete controls from inside the app.