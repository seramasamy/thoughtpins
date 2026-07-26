# Thought Pins App Store Approval Plan

This plan keeps the web app useful now while avoiding the common App Store trap:
submitting a thin web wrapper. The web app is the product contract and staging
surface; iOS and Android should become native-grade clients for that contract.

Official policy references checked on 2026-07-01:

- Apple App Review Guidelines: https://developer.apple.com/app-store/review/guidelines/
- Apple App Privacy Details: https://developer.apple.com/help/app-store-connect/manage-app-information/provide-app-privacy-details
- Apple account deletion guidance: https://developer.apple.com/support/offering-account-deletion-in-your-app/
- Google Play User Data policy: https://support.google.com/googleplay/android-developer/answer/10144311
- Google Play account deletion requirements: https://support.google.com/googleplay/android-developer/answer/13327111
- Google Play Data safety form guidance: https://support.google.com/googleplay/android-developer/answer/10787469

## Product Decision

Do not submit Thought Pins as a bare webview. Apple guideline 4.2 requires an app
to provide features, content, and UI beyond a repackaged website. Thought Pins
has enough product substance for approval if the native client feels like a real
private memory app: chat, capture, memory cards, reading library, export,
deletion, device/session state, notifications, and clear AI privacy controls.

Use the web app to finish and prove the product loop first:

1. Chat-first assistant over journal and library memory.
2. Memory cards for people, places, projects, organizations, and things.
3. Capture and library ingestion flows.
4. Account export, deletion, legal, AI disclosure, and support links.
5. Responsive desktop/tablet/mobile layout.
6. Staging backend with review account and seeded safe data.

Then build native shells that use the same `/v1` API contract.

## Package Choices

Use now:

- Playwright: https://github.com/microsoft/playwright
  Responsive smoke tests for `/app` across desktop, tablet, and mobile widths.
- axe-core: https://github.com/dequelabs/axe-core
  Accessibility checks before native UI work.

Use later:

- Capacitor: https://github.com/ionic-team/capacitor
  Optional hybrid runtime if we decide a web-tech shell is still app-like enough.
  Do not treat this as a shortcut around native product quality.
- fastlane: https://github.com/fastlane/fastlane
  Screenshots, signing, TestFlight, Play internal testing, and store metadata
  once native projects and signing exist.

Avoid for now:

- Heavy analytics SDKs. They complicate privacy labels and Data Safety.
- Ad/tracking SDKs. They are not needed for v1 and increase review risk.
- Tools that defeat publisher access controls. Library ingestion must remain rights-aware.


## Maintenance And Review Safety

Set `MAINTENANCE_MODE=true` when the backend is intentionally paused for a short
upgrade. `/app`, public legal pages, `/health`, and `/v1/client-config` remain
reachable; write actions such as chat, capture, login, and account mutation return
`503 maintenance_mode` with `Retry-After`. The web app shows a top banner and
chat replies with the maintenance message instead of failing silently.

For real server reboots, a process that is fully offline cannot serve a new web
page. Before App Review, host the web bundle or a maintenance page at the edge
(CDN/static host/load balancer) so reviewers still see a normal page while the
API restarts. The API-side maintenance mode handles planned pauses while the
process is alive; edge hosting handles hard restarts.
## Review Account Seed

Create review credentials in staging only, using a password supplied by the
runtime environment and never committed to source control:

```powershell
$env:THOUGHTPINS_REVIEW_EMAIL="review@thoughtpins.com"
$env:THOUGHTPINS_REVIEW_PASSWORD="<store-review-password>"
python scripts/seed_review_account.py --export-vault --zip-vault
```

The seeded account is fictional and exercises login, chat history, memory cards,
library/article data, jobs, export, deletion, and Obsidian vault export. Include
the email and password in App Review / Play Console review notes only after the
staging backend is live. Keep founder Telegram credentials and private data out
of public builds and review accounts. Use `deploy/store/review-notes-template.md` as the sanitized base for App Store Connect and Play Console review notes, validate it with `python scripts/check_review_notes_packet.py`, and add the private review password only inside the store console.
## Apple Approval Gates

- Native-grade functionality beyond a website.
- App tested for crashes and bugs.
- Backend live during review.
- Demo account or full demo mode supplied in Review Notes.
- Privacy policy URL in metadata and inside the app.
- In-app account deletion if account creation exists.
- Sign in with Apple parity if third-party/social login is offered.
- Final app metadata, screenshots, support URL, age rating, and AI disclosure.

## Google Play Approval Gates

- Privacy policy on a public, non-PDF URL.
- In-app account deletion path.
- Web account deletion URL for users who uninstalled the app.
- Data Safety form covering account data, journal/user content, identifiers,
  diagnostics, AI provider processing, and any crash reporting SDK.
- Accurate declarations for all SDKs and third-party processing.
- Internal testing release before broader tracks.

## Engineering Order

1. Add Playwright + axe responsive tests for the current web app.
2. Add a seeded review/demo mode for staging only.
3. Add store data-inventory generation from runtime config.
4. Build native iOS/Android UI targets on top of the existing mobile core.
5. Add fastlane after signing and store accounts exist.
6. Submit TestFlight and Play internal testing before public review.
