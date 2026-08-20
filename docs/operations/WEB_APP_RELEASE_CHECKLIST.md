# Thought Pins Web App Release Checklist

The production web app is the Vite/React client in `frontend/src`. The backend
serves `/app` from `frontend/dist` only when a build marker exists, then falls
back to `frontend/static` for local recovery. This prevents stale ignored build
artifacts from shadowing the maintained app shell.

## Build

```powershell
cd frontend
npm run check
npm run build
```

`npm run build` writes `frontend/dist/.thoughtpins-build.json` after a
successful Vite build. The maintained static fallback remains available for
local recovery, but a release artifact must contain the real Vite bundle.

The broader release gate is:

```powershell
python scripts/release_check.py
```

## Runtime Modes

- Local founder mode: `REQUIRE_API_AUTH=false`. The app opens without login and
  uses the same local default user as the API and Telegram adapter.
- Staging/production: `REQUIRE_API_AUTH=true`. The app requires a JWT session,
  refreshes access tokens automatically, and disables permanent API-key flows.
- Registration is hidden by policy when `SYSTEM_LOCKED=true`.
- `/v1/client-config` is the source of truth for legal links, store targets,
  registration lock, local mode, and minimum supported clients.
- Authenticated users must accept the current AI-processing disclosure before
  entering the app. The web client fails closed if preferences cannot be read.

## OAuth Build Contract

- `VITE_GOOGLE_CLIENT_ID` and `VITE_APPLE_CLIENT_ID` are compile-time web values,
  not runtime secrets. Rebuild the frontend whenever either changes.
- Enable a provider in the backend only when its Vite ID is set and included in
  the matching backend client-ID allowlist. `scripts/validate_production.py`
  enforces this parity.
- The Dockerfile and every Compose image build receive both Vite IDs as build
  arguments. Do not assume container runtime environment values can alter an
  already-built JavaScript bundle.
- Verify Google and Apple buttons, callback completion, consent gating, token
  refresh, logout, and account deletion against the real staging provider
  configuration before submission.

## Product Surface

- Chat: default surface. Uses `/v1/chat` with conversation replay, route/status
  transparency, private-context toggle, pending confirmations, and a fixed mobile
  composer. Enter sends, Shift+Enter inserts a line break, and a visible live
  status remains on screen while Thought Pins is processing.
- Memory: baseball-card style memory browser for people, places, projects,
  organizations, things, and all entities. Uses `/v1/memory/cards` and detail
  cards from `/v1/memory/cards/{id}`. Cards expose a human-readable prominence
  tier while the API retains the versioned signal breakdown for auditability.
- Capture: explicit journal save for users who want a manual entry form.
- Library: article/document/link ingestion and source detail review.
- Entries: paginated journal timeline with deletion.
- Jobs: queue list, retry, cancel, dead-letter visibility.
- Status: shallow/deep health panels for API, DB, worker, LLM, embeddings, queue,
  and graph/vector dependencies.
- Account: preferences, devices, export, logout, account deletion, legal
  acceptance, and local founder deletion guard.
- Legal: privacy, terms, support, account deletion, AI disclosure, web/app URLs.

## Responsive Contract

- Desktop: persistent sidebar, constrained content width, chat + context columns,
  memory grid + detail panel.
- Tablet: sidebar becomes a horizontal rail, dense modules collapse to fewer
  columns, chat remains primary.
- Mobile: bottom tab bar for Recap, People, Chat, Places, and Pins; operational
  and account surfaces remain reachable from the Settings menu. All views become
  single-column, the chat composer stays above the safe-area tab bar, and touch
  targets stay at least 44px high.
- Web modules should mirror the future mobile app tabs so native UI can reuse the
  same mental model: Recap, People, Chat, Places, Pins, and Settings.

## Frontend Module Layout

- `frontend/src/app/`: orchestration, navigation, shell, auth, view typing.
- `frontend/src/components/`: shared primitives and formatting helpers only.
- `frontend/src/features/chat/`: conversational product surface.
- `frontend/src/features/memory/`: people/places/projects/things cards.
- `frontend/src/features/capture/`: explicit journal capture.
- `frontend/src/features/library/`: articles, links, documents, sources.
- `frontend/src/features/entries/`: timeline and deletion.
- `frontend/src/features/jobs/`: worker/queue operations.
- `frontend/src/features/account/`: settings, export, devices, deletion.
- `frontend/src/features/dashboard/`: operational status.
- `frontend/src/features/legal/`: policy/store/support links.
- `frontend/src/core/`: UI-free session, storage, validation, drafts, sync,
  installation, runtime, and version-policy primitives.

Keep API calls centralized in `frontend/src/api.ts`; feature views should not
hardcode fetch paths.

## Domain Targets

- Public site/legal pages: `https://thoughtpins.com`.
- Production web app: `https://app.thoughtpins.com/app`.
- Production API: `https://api.thoughtpins.com/v1`.
- Staging web app: `https://staging.thoughtpins.com/app`.
- Staging API: `https://api-staging.thoughtpins.com/v1`.

## Maintenance Mode

- `MAINTENANCE_MODE=true` keeps `/app`, legal pages, health, and client config reachable while returning structured `503 maintenance_mode` errors for writes.
- The web app shows a banner from `/v1/client-config` and chat returns a local maintenance reply when the user sends a message.
- A full server reboot still needs an edge/static host or load balancer maintenance page because a down backend cannot serve new HTML.

## Safety Rules

- The app calls the API on the same origin by default. Set `VITE_API_BASE_URL`
  only for a separately hosted web build.
- Local founder mode disables account deletion in the web UI to avoid deleting
  the local vault by accident.
- Raw journal text must not be sent to analytics, crash SDKs, or third-party web
  scripts.
- Legal URLs come from `/v1/client-config`; production validation fails if they
  are missing.
- OAuth identity tokens are verified by the backend. Provider client secrets
  and signing credentials must never be included in the frontend bundle.
- Never expose Telegram/founder-only controls in public web, iOS, or Android
  builds.

## Automated Web Review Smoke

`python scripts/check_web_app_contract.py` is the local static product-contract gate. It verifies the maintained React app and static fallback expose chat, memory cards, capture, library/uploads, entries, jobs, status, account export/delete, legal/store links, maintenance states, and responsive mobile navigation even when browser spawning is blocked.

The Playwright/axe harness lives in `frontend/e2e` and verifies responsive
review flows with mocked `/v1` API responses:

```powershell
cd frontend
npm run install:playwright
npm run smoke:web
npm run smoke:cross-browser
```

It checks desktop, tablet, and mobile layouts, login/signup visibility,
maintenance-mode chat behavior, Enter/Shift+Enter behavior, cross-view chat
handoff, visible processing state, response-voice persistence, offline config
failure messaging, no founder-control leakage, no horizontal page overflow,
and serious/critical axe violations. Screenshots are written to
`reports/web-smoke/`.

The cross-browser audit runs the live public site and authenticated app shell
in Chromium, Firefox, and WebKit at 1440x960, 390x844, and 320x568. It fails on
runtime errors, serious/critical accessibility findings, horizontal overflow,
missing assets, or composer/navigation overlap. Evidence is written to
`reports/cross-browser/`.

If this Windows shell reports `spawn EPERM`, run the same command in an
unrestricted shell, Docker/Linux, or CI. The local release gate still runs
`python scripts/check_web_review_harness.py` to ensure the harness is present
and wired even when browser spawning is blocked by the host sandbox.

## Manual Smoke Test

1. Open `http://127.0.0.1:8420/app`.
2. Confirm local mode opens without login when auth is disabled.
3. Send a normal chat message and confirm it routes through `/v1/chat`.
4. Save a short entry through Capture.
5. Ask about that entry in Chat.
6. Add a link/document in Library and confirm it appears in memory context.
7. Open Memory and confirm people/places/projects/things cards render.
8. Check Jobs and Entries.
9. Export account data from Account.
10. Open Legal and confirm all production URLs are configured before staging.

## Native App Preparation

Before iOS/Android UI work starts, the web app must prove the same app contract:
chat-first capture, memory cards, library ingestion, export/delete, legal links,
version policy, and auth/session flows. Native apps should use the existing
mobile core modules and duplicate this tab structure rather than inventing a
separate product flow.
