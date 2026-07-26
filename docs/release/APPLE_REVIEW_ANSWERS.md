# Thought Pins Apple Review Answers

Last reviewed: 2026-07-13 against Apple's App Review Guidelines, User Privacy and Data Use guidance, App Privacy guidance, privacy-manifest guidance, and account-deletion support guidance.

## What does the app do?

Thought Pins is a private journaling and memory app. A user writes chat-style notes, journal entries, source links, and uploaded documents. The app turns those into a private searchable memory layer with chat, memory cards, export, and deletion.

## Does the submitted app include hidden, beta, or owner-only features?

No. Store builds expose the normal public product surface only: account creation, login, chat, capture, library ingestion, memory cards, export, support, legal pages, safety reporting, and account deletion. Private/local adapters are separate client software outside the submitted iOS, Android, and web app bundles; they use the same public `/v1` API and are not shipped to reviewers or users.

## What login methods are supported?

Email/password and phone/password are supported. Google and Apple OAuth are supported when production client IDs are configured. On iOS, Sign in with Apple must be enabled whenever Google or another third-party identity provider is shown.

## Can a reviewer fully use the app?

Yes, after staging is deployed. The review account is seeded with `python scripts/seed_review_account.py --export-vault --zip-vault`. The password is provided only in App Store Connect review notes. Backend services must be live during review.

## Does the app use third-party AI?

Yes. User-provided journal, chat, article, and document content may be sent to configured third-party AI and embedding providers to classify messages, extract memories, search, and generate replies. Account creation and existing-user onboarding present the AI disclosure and require explicit permission before these content-processing features are available. The runtime is provider-neutral; the actual production processors and their terms must be reflected in App Store privacy answers and final policy copy before submission.

## Is user content public or user-generated content for other users?

User content is private by default and is not posted to a public feed. The app still includes a safety report endpoint and support path for unsafe AI output, harmful imported content, privacy concerns, copyright concerns, harassment/abuse, security concerns, and other reports.

## How is account deletion handled?

Users can initiate full account deletion inside the app through `DELETE /v1/me`, and a web resource exists at `https://thoughtpins.com/account/delete`. Deletion removes account data and associated private content except minimal security/audit records that must be retained by law or legitimate security need and are disclosed in the privacy policy.

## What happens during backend maintenance?

The public client config exposes maintenance state. The UI shows a normal maintenance/offline banner and write requests receive a structured `maintenance_mode` error instead of crashing or exposing diagnostics.

## Does article ingestion defeat publisher access controls?

No. Users may submit links or files they have the right to process. The source policy respects publisher controls, never impersonates crawler identities, and retains only metadata or authorized user-provided material when public text is unavailable.

## What local data is stored on-device?

Native apps store only what is required for app functionality: refresh/session material in platform secure storage, offline draft queues, cached recent conversations, memory-card cache, user preferences, and upload retry state. Full server memory remains in the backend unless a user explicitly exports a vault.

## What permissions are required?

The native apps request microphone access only after the user opens the voice-note disclosure and chooses Continue. The recording state remains visible while capture is active. File import uses the platform's user-selected document picker. The apps do not request camera, broad photo-library, location, contacts, or notification permission in v1.

## How are voice notes handled?

The submitted public build transcribes user-initiated voice notes and discards the audio after processing; the transcript becomes ordinary journal content. `VOICE_ARCHIVE_ENABLED` is false, so no retention control or retained-audio collection path is exposed in the App Store build. Private/self-hosted deployments can enable a separately consented encrypted archive, but that capability is not part of this submission. Full account deletion still includes any tenant-owned voice data if a user moves from such a deployment. Normal account and Obsidian exports never include audio bytes, integrity fingerprints, or internal storage references.

## How is data export handled?

Users can export account data through `GET /v1/export` and export an Obsidian-compatible vault through the vault export flow. Exports are generated for the authenticated user only.

## What code is submitted to stores?

The submitted app uses the Thought Pins public API and native client code. The iOS target is defined in `mobile/ios/ThoughtPinsNative/project.yml` and includes an App Store icon, Sign in with Apple entitlement, and privacy manifest. Private local adapter code, local `.env` files, provider keys, review passwords, local vaults, logs, reports, and backups are excluded from submitted builds and public source exports.
