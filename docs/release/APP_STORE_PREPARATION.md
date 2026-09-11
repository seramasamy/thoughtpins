# App Store preparation — 11 September 2026

This follow-up corrects web and native session boundaries, finishes the web
authentication presentation, and updates the submission instructions. Earlier
native and website evidence remains in
[the release review](RELEASE_POLISH_CHANGELOG.md).

## Web app corrections

- Two rapid submissions could send two login requests. A shared request guard
  now serializes password, provider, email-link and code operations, including
  the interval before React renders a disabled button. Inputs and mode changes
  remain stable while authentication is pending.
- React Strict Mode could consume an emailed link and then discard its result,
  leaving the page on “Signing you in.” Effect replay now subscribes to the
  same request. The token is removed from the address bar, and expired links
  return to an actionable form.
- A confirmed registration followed by failed login or consent delivery could
  retry account creation and hit “Account already exists.” The mounted form
  remembers confirmed contacts and resumes login/consent without recreating
  those accounts. It does not persist passwords or bypass consent.
- Login now lets the server evaluate existing credentials; the 12-character
  creation rule applies to registration. Password text, whitespace and selection
  survive showing/hiding and subsequent typing. The visibility control is
  labelled and has a 44-pixel target.
- AI-consent failures now show their error and allow retry with the checkbox
  retained. The app still waits for server acceptance before opening.
- A real-backend check found parallel requests rotating the same refresh token:
  one renewal succeeded, another was rejected, and the user was signed out.
  Session recovery now shares one renewal and reuses it for late 401 responses.
  Logout and account changes invalidate the older operation's right to set or
  clear a session. JSON and download requests use the same coordinator;
  transient failures preserve the session and report the actual renewal error.

## Native session corrections

Three new simulator tests reproduced delayed refresh responses restoring a
signed-out account, replacing a newer login, or clearing that login after an
older renewal was rejected. Native requests now retain their account identity
through renewal and retry; responses belonging to a replaced session are
cancelled. Concurrent callers share renewal, and late 401s reuse the same
account's rotation. Sign-out clears local credentials before awaiting the
server and still attempts revocation if Keychain refuses the clear.

The new `SessionRenewal.swift` owns session identity and renewal transport,
reducing the existing API client's size. Unit tests exercise the state helper
directly; URLSession boundary tests cover logout and account replacement.

## Visual finish

The web login has a compact mobile brand header, an appearance control within
that header, consistent rounded inputs and provider buttons, and visible sign-in
progress. Redundant promotional content moves out of the small-screen form's
way. Both login and signup are checked at 320, 390, 834 and 1440 pixels in light
and dark appearance, including WCAG A/AA axe checks and overflow measurements.
The existing modern homepage hero remains intact.

Browser product-preview captures now stay under ignored `reports/web-smoke/`.
Running tests no longer overwrites reviewed website/store images or invalidates
the website cache-key gate. Publishing product assets remains an explicit step.

## Repository and submission material

Commit `ac70447` restores a short David Rockefeller inspiration paragraph directly
below the README banner. The concise alternatives table links to a dated,
first-party review of 13 tools. It acknowledges overlapping memory, graph,
privacy and export capabilities; no comparative benchmark advantage is claimed.

The Apple submission README and status file now link to actual native CI and
archive evidence. They remove obsolete claims that the app has never compiled,
that the native tests are uncommitted, or that Xcode Cloud is the only release
path. Signing, live-backend validation, physical-device checks, current store
screenshots and hosted deployment remain explicit release steps.

## Verification

The new browser regressions reproduced the original emailed-link and duplicate
submission failures before their fixes. Chromium and WebKit run the expanded
authentication suite. Firefox now covers authentication, recovery and modern
surfaces in CI. Each run retains browser results and review screenshots.

Run the strict repository gate and public-export check on the chosen revision:

```sh
python scripts/release_check.py --strict-quality
python scripts/check_public_export.py
cd frontend
npm run smoke:web
npm run test:unit
npm run smoke:pwa
npm run smoke:site:ui
npm run smoke:ios
npm run smoke:firefox
```

The strict release command passes all 48 top-level checks, including the proof
verifier's two artifact self-checks. Python reports 894 passed and 16 optional
Telegram skips; typing covers 453 files. The source, privacy, export, migration,
dependency and production-build gates pass without weakening their requirements.

| Local evidence | Result |
| --- | --- |
| Chromium app workflows | 149 passed; no skips or retries. |
| Compatible local WebKit | 18 authentication/session cases passed; WebKit 18.4 on this older Mac. Current-engine coverage belongs to GitHub CI. |
| Direct web session tests | 11 passed, including concurrent renewals, late responses, logout/account changes, and transient/rejected failures. |
| Shared Swift package | 87 passed on iOS 17.2; five session-boundary cases passed again after normalizing the renewal URL. |
| Built web app with real local backend | Login, renewal, all five tabs at 390/834/1440px, JSON export, signup, tenant isolation and deletion passed. No page exceptions or server errors; deleted account rows and foreign-key violations both zero. |
| Published-asset isolation | Product-preview capture passed and left the four reviewed website/store images unchanged. |
| Public hosted pages | Home, app, privacy, terms, support, AI disclosure and deletion pages returned 200 in Chrome. They still served older cache keys; this is URL availability evidence, not deployment verification. |

The combined code revision `5c1bdbd` passes all nine jobs in
[GitHub run 34655594573](https://github.com/seramasamy/thoughtpins/actions/runs/34655594573):
Python, PostgreSQL, container, Android, web, native-change detection, both native
device reviews, and the iOS archive. The browser matrix passes 289 cases:
149 Chromium app, one PWA, 38 website, 63 WebKit and 38 Firefox; all 11 direct
web session tests also pass.

The iPhone 17 Pro and iPad Pro 13-inch (M5) each pass seven model and five UI
tests on iOS 26.5, with no failures or skips. Their current captures include
sign-in, registration, retry, large text, capture recovery and navigation;
iPad navigation is reviewed in portrait and landscape. All 87 shared Swift
tests pass in the archive job as well as on the older local simulator.

The unsigned arm64 production archive succeeds and its built bundle passes
validation: version 1.0.0, build 277, iPhone/iPad device families, minimum iOS
17.0, Xcode 26.6 (`17F113`) and iOS 26.5 SDK. Browser reports, native results,
screenshots, archive and dSYMs were downloaded for the private recovery packet.
Signing, signed export and App Store Connect upload were skipped because their
credentials are not configured. The following submission-note commit changes
documentation only; these native artifacts belong to `5c1bdbd`.

| Live commit | Platform and purpose |
| --- | --- |
| [ac70447](https://github.com/seramasamy/thoughtpins/commit/ac70447780305e56df3ef2028413bbbbf0adf9ee) | README inspiration and sourced alternatives. |
| [c1547d3](https://github.com/seramasamy/thoughtpins/commit/c1547d329799aae992b25003384b5a78098d2d57) | Web authentication, session recovery, accessible visual finish and browser coverage. |
| [fdf1b14](https://github.com/seramasamy/thoughtpins/commit/fdf1b142fb5a5a8551b9d367c6fe48b432c255f8) | Native account boundaries, sign-out behavior and nine Swift regressions. |
| [48d9ad4](https://github.com/seramasamy/thoughtpins/commit/48d9ad4e12211c6d3550cee87e9ea30dcefc164d) | Browser tests preserve reviewed product images. |
| [5c1bdbd](https://github.com/seramasamy/thoughtpins/commit/5c1bdbd970764262d55ce3b2e61e9e7f18b18951) | Release gate checks the extracted iOS module and the same required endpoints. |

Distribution remains separate: the local Apple Distribution identity, six
GitHub signing/App Store Connect secrets, hosting credentials and live review
password are absent. Signing, deployment, a live review-account pass, current
store captures and physical-device validation still need completion.

All local review artifacts remain ignored under `reports/appstore-prep/` and
`.tmp/appstore-prep/`. Fixtures are fictional; this work makes no paid
model-provider calls.
