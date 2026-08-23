# Apple Submission Package

Everything needed to submit Thought Pins to the App Store, and an honest account
of what is not ready.

| File | What it is |
|---|---|
| [`REVIEW_NOTES.md`](REVIEW_NOTES.md) | The text to paste into App Store Connect → App Review Information |
| [`AFTER_DEVELOPER_ACCOUNT.md`](AFTER_DEVELOPER_ACCOUNT.md) | Ordered runbook from enrollment to submission |
| [`PROGRESS.md`](PROGRESS.md) | Working log, decisions with reasons, findings |

Existing material this builds on rather than duplicates:

- `docs/release/MAC_XCODE_V1_EXECUTION_CHECKLIST.md` — 10-section Xcode checklist
- `docs/release/MACOS_XCODE_APP_STORE_RUNBOOK.md` — 554-line signing/archive runbook
- `docs/release/APPLE_REVIEW_ANSWERS.md` — App Privacy questionnaire answers
- `docs/release/APP_REVIEW_RISK_REGISTER.md` — per-guideline risk register
- `deploy/store/` — submission packet, data-safety inventory, commerce policy

---

## Blocking, in order

### ~~1. DNS~~ — resolved 2026-08-23

`api.thoughtpins.com` is live: HTTP 200 on `/v1/client-config`, valid
certificate, resolving unproxied to Railway. `check_live_endpoints.py` reports
**8 of 8 reachable**. Both mobile builds now have a backend to dial.

### 1. Sign in with Apple is off in production

Production reports `oauth_google_enabled: true` and `oauth_apple_enabled: false`.
Guideline 4.8 requires Sign in with Apple wherever a third-party sign-in is
offered, so this is a rejection as it stands. It is not fixable yet —
`APPLE_OAUTH_CLIENT_IDS` needs an Apple Developer account. Set it in Railway
before submitting.

### 2. No Mac — **blocks everything in Stage 3**

No SwiftUI in this repository has ever been compiled. Roughly 400 lines,
including everything changed in the last two passes. Expect first-build errors
and treat them as normal.

### 3. Screenshots — blocked on 2

iPhone 6.9" (1290 × 2796) and iPad 13" (2064 × 2752), at least three each. iPad
is required because the target is universal.

---

## Not blocking, and already correct

**No in-app purchases.** `deploy/store/commerce-policy.json` declares the app
free with no IAP, no subscriptions, no external purchase links and no ads, and
`scripts/check_free_launch.py` fails the build if StoreKit, Stripe, RevenueCat,
Paddle or Play Billing plumbing appears in any shipping surface. This removes
Guideline 3.1.1 from the review entirely. Reasoning in
[`PROGRESS.md`](PROGRESS.md).

**No paywall circumvention.** Saving a gated article stores public metadata only
— the fetched text is discarded, `rights_basis` is set to `metadata_only`, and
publishers that limit automated access are refused. `ARTICLE_ALLOW_RESTRICTED_DOMAINS`
is forced false outside local development by startup validation.

**No tracking.** No IDFA, no `AppTrackingTransparency`, no analytics or
advertising SDK, no `UIWebView`, no private API use, no swizzling. Verified by
sweep across the iOS and Android sources.

**Permissions.** Microphone only, requested on tap, with the reason string
explaining that audio is transcribed and discarded.

**Account deletion.** Real and reachable in-app at Account → Delete account, and
on the web at `/account/delete`. Guideline 5.1.1(v) satisfied.

**The demo account clears the invite gate.** Fixed in this pass — it did not
before, and that alone would have ended the review.

---

## Known-unverified Swift

These changed recently and have never been compiled. If the first Xcode build
fails, start here:

| File | What changed |
|---|---|
| `ThoughtPinsNativeApp.swift` | Base-URL validation replacing a force-unwrap |
| `ThoughtPinsAppModel.swift` | `clearLocalAccountState`, reworked `register`, guarded draft sync |
| `ThoughtPinsReviewShell.swift` | Auth form restructure, `registrationBlocker`, colour-scheme Apple button, `record()` guard |
| `ThoughtPinsScreens.swift` | `scenePhase` recording teardown, importance row restructure, `contentShape` |
| `DraftStore.swift` | `purge()` |
| `DraftStoreTests.swift` | New file, 3 tests |

What *is* executed: the Python suite (838 tests), the Android core tests
(6 tests, run locally against the SDK), the Android APK build, and the
Playwright iOS device matrix (45 checks across nine iPhone and iPad sizes on
WebKit, the engine iOS Safari uses).

The Android app has been **run on an emulator** — it launches, renders, and the
auth screen behaves. That is the closest executed proxy for the iOS shell, since
both drive the same API contract and the same product decisions.
