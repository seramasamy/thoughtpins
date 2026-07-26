# Thought Pins Platform Codebase Strategy

## Naming

- Human-facing app name: **Thought Pins**.
- Social/GitHub/org slug: `thoughtpins`.
- Production domain: `thoughtpins.com`.
- Python package and command module: `thoughtpins`.
- Native code identifiers: `ThoughtPinsCore`, `ThoughtPinsAPIClient`, and
  `com.thoughtpins.*`.
- Production bundle/package IDs should reserve `com.thoughtpins.app` unless a
  different legal entity/domain is chosen before store submission.

## Repository Shape

Keep a single monorepo until the API contract and product loop stabilize:

- `src/thoughtpins/`: backend API, memory engine, ingestion, auth, worker,
  shared domain logic, and legacy local runtime hooks kept disabled in production.
- `frontend/`: backend-served web app, responsive React shell, feature modules,
  and reusable web client primitives.
- `mobile/ios/ThoughtPinsCore/`: UI-free Swift package for auth, session,
  version policy, drafts, sync, and API contracts.
- `mobile/android/thoughtpins-core/`: UI-free Kotlin core with the same
  contracts.
- `alembic/`, `scripts/`, `deploy/`, `load/`, `tests/`: migrations,
  validation, release gates, deployment templates, load tests, and coverage.
- `site/`: static public/legal site for `thoughtpins.com`.
- `../thoughtpins-founder-telegram-adapter/`: private mini-PC chat adapter that calls the public `/v1` API and stays outside store builds/public exports.

Do not split iOS/Android into separate repositories until the backend API is
stable enough for v1 app builds. When native UI work starts, add:

- `mobile/ios/ThoughtPinsApp/` for the SwiftUI application target.
- `mobile/android/thoughtpins-app/` for the Android application target.

## What Goes To GitHub

Upload the sanitized `thoughtpins` repository root:

- Include backend source, frontend source/static UI, mobile core scaffolds,
  migrations, tests, scripts, deploy templates, load tests, static public site,
  and docs.
- Exclude `.env`, `.venv/`, `.deps/`, `.tmp/`, `data/`, `logs/`, `vault/`,
  `reports/`, `backups/`, generated cache folders, generated build outputs, and
  `founder/private/`.
- Run `python scripts/forbidden_scan.py` and `python scripts/release_check.py`
  before any push.

The founder Telegram test code can remain open-source because it contains no
personal data or secrets and is production-disabled. Personal test notes,
screenshots, backups, local exports, and credentials must stay in ignored local
state only.

## Web App Path

The web app should remain the first full UI because it can exercise the entire
backend without App Store review latency:

1. Keep `/app` as the backend-served functional UI.
2. Keep the source organized as `frontend/src/app`, `frontend/src/components`,
   `frontend/src/features/*`, and UI-free primitives in `frontend/src/core`.
3. Use `/v1/chat` as the default UX, with memory cards, sources, entries, jobs,
   legal, account export/delete, and device registration as secondary tabs.
4. Preserve `frontend/static` as a recovery fallback, but serve `frontend/dist`
   first only when `npm run build` writes `.thoughtpins-build.json`.
5. Keep responsive breakpoints aligned with the future native app tabs: Chat,
   Memory, Capture, Library, Account.
6. Use `thoughtpins.com` for public/legal pages and `app.thoughtpins.com` for
   the web app.
7. Deploy web staging before native TestFlight or Play internal testing.

## iOS App Store Path

Prepare iOS in this order:

1. Reserve bundle ID `com.thoughtpins.app`.
2. Build `mobile/ios/ThoughtPinsApp/` on top of `ThoughtPinsCore`.
3. Implement email/phone login, Sign in with Apple if any third-party auth is
   offered, account deletion, privacy/legal links, AI disclosure, export, and
   support.
4. Provide a review test account and notes explaining that AI processes private
   journal content for memory/search/chat.
5. Keep private local-adapter controls unavailable in production builds.

## Play Store Path

Prepare Android in this order:

1. Reserve package `com.thoughtpins.app`.
2. Build `mobile/android/thoughtpins-app/` on top of `thoughtpins-core`.
3. Implement the same account deletion, privacy/legal links, AI disclosure,
   export, and support flows.
4. Complete the Data Safety form for user content, account data, diagnostics,
   LLM processing, OAuth providers, and Sentry if enabled.
5. Run closed testing after web staging is stable.

## Release Rule

Ship web first, then native beta:

1. Backend release gate passes.
2. PostgreSQL RLS verification passes against a non-owner app role.
3. Staging smoke and k6 tests pass.
4. Public privacy, terms, support, AI disclosure, and account deletion URLs are
   live.
5. Secrets are rotated and stored in managed infrastructure.
6. Web app is stable enough to exercise every user journey.
7. Native apps are built from the shared mobile core and pointed at the same
   `/v1` API contract.
