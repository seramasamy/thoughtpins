# Thought Pins Review Notes

Thought Pins is a private memory and journaling app. The review build should exercise the same public product surface that a normal user sees: account creation, login, chat, journal capture, article/document ingestion, memory cards, export, and account deletion.

## Review Access

- App name: Thought Pins
- Review account email: `review@thoughtpins.com`
- Email override environment variable: `THOUGHTPINS_REVIEW_EMAIL`
- Password source environment variable: `THOUGHTPINS_REVIEW_PASSWORD`
- Seed command: `python scripts/seed_review_account.py --export-vault --zip-vault`

The review password is stored only in the private App Store Connect or Play Console review notes for the submitted build. It is never committed to the repository, printed by the seed CLI, or included in public artifacts.

## URLs

- Marketing site: https://thoughtpins.com
- Web app: https://app.thoughtpins.com/app
- API base URL: https://api.thoughtpins.com/v1
- Privacy Policy: https://thoughtpins.com/privacy
- Terms: https://thoughtpins.com/terms
- Support: https://thoughtpins.com/support
- Account deletion: https://thoughtpins.com/account/delete
- AI disclosure: https://thoughtpins.com/ai-disclosure

The backend must remain live during review. If a maintenance window is active, the app shows a normal maintenance/offline banner and sends return a maintenance message instead of crashing or exposing diagnostics.

## Review Flow

1. Log in with the review account. The public app supports email or phone account login, and Apple/Google OAuth can be enabled with configured client IDs. On iOS, Sign in with Apple must be offered whenever Google sign-in is offered.
2. Open chat and send a normal message. Chat uses `POST /v1/chat` and should reply with remembered context when relevant.
3. Save a journal-style note. The app auto-routes likely journal text into the memory system and shows status instead of requiring manual commands.
4. Add an article/document link or upload. Link ingestion uses `POST /v1/library`; file upload uses `POST /v1/uploads`.
5. Open memory cards. People, places, concepts, events, and articles are available through `/v1/memory/cards` with provenance back to source memories.
6. Export account data. The export flow uses `GET /v1/export` and includes an Obsidian-compatible vault.
7. Delete the account. In-app deletion uses `DELETE /v1/me`; the web deletion resource is available at https://thoughtpins.com/account/delete.
8. Check Privacy, Terms, Support, and AI disclosure links from the app.

## AI And Data Handling

Thought Pins sends user-provided journal, chat, article, and document content to the configured AI provider for classification, extraction, embeddings, retrieval, and responses. The runtime is provider-neutral; production policy copy and store disclosures must name the provider configuration used by the submitted build.

Journal content is not sold. Advertising SDKs and tracking are not used for the v1 review build. Export and deletion are available to the user from inside the app.

## Public Build Scope

Private local adapters are separate from the submitted app and are not exposed in public web or native builds. Owner-only controls, local credentials, and local adapter controls are excluded from public export checks.

The web product, shared mobile core, and native UI projects are review-handoff ready. Android has a locally compiled and linted release bundle; production signing remains private release work. iOS has an XcodeGen app target, privacy manifest, Sign in with Apple entitlement, final icon, and source gate, but still requires a current macOS/Xcode archive, signing, native screenshots, and simulator/device testing. Push notifications and other unused permissions are intentionally absent from the initial review targets. The remaining native evidence is tracked in `deploy/store/native-review-handoff.json`.

## Support

Use https://thoughtpins.com/support, `support@thoughtpins.com`, or in-app `POST /v1/safety/reports` for review questions, account-deletion help, privacy requests, unsafe AI output, harmful imported content, and backend availability issues.
