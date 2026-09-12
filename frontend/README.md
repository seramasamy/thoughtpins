# Thought Pins Frontend

This is the backend-served React web app for Thought Pins. It shares its
navigation and API contracts with the native clients.

## Module Map

- `src/app/`: app orchestration, auth screen, shell, navigation, shared view
  types.
- `src/components/`: shared UI primitives and formatting helpers.
- `src/features/chat/`: primary conversational surface backed by `/v1/chat`.
- `src/features/memory/`: people/place/project/organization/thing memory cards.
- `src/features/capture/`: explicit journal capture.
- `src/features/library/`: article, link, and document source ingestion.
- `src/features/entries/`: journal timeline and deletion.
- `src/features/jobs/`: job queue operations.
- `src/features/account/`: preferences, devices, export, deletion, legal
  acceptance.
- `src/features/dashboard/`: health/status panels.
- `src/features/legal/`: legal, support, store, and disclosure links.
- `src/core/`: UI-free primitives for session, storage, validation, drafts,
  sync, installation, runtime, and version policy.

Keep fetch logic in `src/api.ts`. Feature modules should consume typed API
methods instead of hardcoding endpoints.

## Responsive Contract

The primary information architecture is identical on every product surface:
Recap, People, Chat, Places, and Pins. Chat is the centered, emphasized action.
Desktop uses a persistent side rail that can move left or right; tablet uses a
compact icon rail; mobile uses a five-item bottom tab bar with safe-area
spacing. Account, explicit capture, the full source library, all entries,
processing activity, health, and legal controls live in the utility menu so the
primary product remains personal rather than administrative.

- `Recap` renders daily, weekly, and monthly journal periods plus synthesized
  report sections from `/v1/reports`.
- `People` and `Places` use the typed memory-card API and retain provenance,
  relationship, and timeline detail.
- `Chat` is the only composer on its route and supports natural routing, file
  attachment, confirmations, maintenance behavior, and memory-backed history.
- `Pins` is the human-facing source library for links, books, documents, and
  notes. Source memories remain distinct from lived journal memories.

The ember mark and primary action sit on cool mineral surfaces. A violet
secondary accent connects the memory motif, profiles, and reflection panels.
`styles/140-modern.css` owns the shared visual composition; the preceding
feature layers own layout and behavior. Native sans typography and explicit
light/dark semantic pairs are defined in `DESIGN.md`.
Animations honor `prefers-reduced-motion`.

## Local Checks

```powershell
npm run check
npm run test:unit
npm run build
npm run smoke:web
npm run smoke:pwa
npm run smoke:site:ui
npm run smoke:ios
npm run smoke:firefox
```

On locked Windows hosts, `npm run build` may validate the static fallback when
Vite cannot spawn its child process. A successful unrestricted build writes
`dist/.thoughtpins-build.json`; the backend only serves `dist` when that marker
exists.

Authentication recovery lives in `src/app/useAuthRequest.ts`; a shared guard
owns pending password, provider and email operations. Single-use emailed links
retain their request through React Strict Mode effect replay.
`src/app/passwordAuthentication.ts` resumes a server-confirmed registration
after a later login or consent failure. `src/components/PasswordField.tsx`
owns AutoFill, creation-only length validation and reversible visibility.
`e2e/auth-recovery.spec.ts` exercises these boundaries, consent retry, compact
layouts and accessibility in Chromium, WebKit and Firefox. Browser screenshots
and results are retained by CI; test fixtures contain fictional data.

`src/core/sessionRecovery.ts` coordinates one refresh per session for JSON and
download requests. Late responses may reuse a rotation of the same session,
but cannot restore a signed-out account or adopt a different account's token.
Direct unit tests cover those races and rejected/transient refresh failures;
`e2e/session-recovery.spec.ts` covers the browser/API boundary.

## OAuth Builds

Google and Apple web client IDs are compile-time Vite values. Set
`VITE_GOOGLE_CLIENT_ID` and `VITE_APPLE_CLIENT_ID` for a production build when
the matching backend provider is enabled. The Dockerfile and Compose builds
forward both values explicitly; changing either ID requires rebuilding the web
bundle. Production validation rejects enabled providers whose web ID is absent
or missing from the backend allowlist.
