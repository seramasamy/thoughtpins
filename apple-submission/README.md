# Apple Submission Package

Everything needed to submit Thought Pins to the App Store, and an honest account
of what is not ready.

| File | What it is |
|---|---|
| [`MAC_START_HERE.md`](MAC_START_HERE.md) | **Have the Mac? Start here.** Clone, bootstrap, first compile, simulator, archive |
| [`REVIEW_NOTES.md`](REVIEW_NOTES.md) | The text to paste into App Store Connect → App Review Information |
| [`AFTER_DEVELOPER_ACCOUNT.md`](AFTER_DEVELOPER_ACCOUNT.md) | Ordered runbook from enrollment to submission |
| [`PROGRESS.md`](PROGRESS.md) | Working log, decisions with reasons, findings |

**Considering Play first?** See [`../play-submission/STEPS.md`](../play-submission/STEPS.md).
Short answer: start it in parallel, not instead — Android is buildable today and
Play's waiting period runs on its own while you sort out a Mac.

---

## What the process actually is

From a former App Store reviewer's public account, and it changes what matters:

- **Automated checks first.** They approve nothing — they only prepare the build
  for a human.
- **A human installs it and uses it like a normal person.** They are checking
  trust and compliance, not hunting bugs. Three questions: does it do what you
  say, does it follow the guidelines, and does anything feel confusing,
  misleading, unsafe or risky.
- **Reviewers do read the notes field.** Different person each round.
- **Ambiguity is resolved against you.** If they cannot understand something, it
  is safer for them to reject than to guess. This is the single highest-leverage
  fact: clarity in the notes is worth more than polish in the app.
- **First-pass approval is "not common at all"** — but the same reviewer said
  the first review is only the hardest *because* people submit without proper
  documentation, and that well-documented apps do pass first time.
- **They test on iPad "almost all of the time"**, even when the iPad box is
  unchecked. Unchecking only means you are not *claiming* native support; the
  app still has to launch and not feel broken. **We claim universal
  (`TARGETED_DEVICE_FAMILY: "1,2"`), so iPad will definitely be tested.**
- **Anything with user-generated content is flagged risky and needs heavy
  moderation tooling.** Ours has no sharing surface at all — verified, no feed,
  no profiles, no user-to-user anything — and the review notes now say so
  explicitly and first. That is the difference between "private notebook" and
  "social app we must scrutinise".
- **A "sent for extra review" outcome is the slow, bad path.** It happens when
  something is unclear or sensitive. Everything above is aimed at not landing
  there.

## The commonly-cited blockers, and where this project actually stands

| What people warn about | Us |
|---|---|
| $99/yr, approval takes days, needs business registration + tax ID | Only **organisation** accounts need a D-U-N-S number. An **individual** account needs government ID and is faster — but lists your personal legal name as the seller. Decide before enrolling; changing it later is painful. |
| Need a website with a privacy policy and terms | **Done.** `thoughtpins.com` with `/privacy`, `/terms`, `/support`, `/ai-disclosure`, `/account/delete` — all verified HTTP 200. |
| Screenshots must match exact device dimensions | **Done, and upgradeable.** A 6.5" iPhone set (1284×2778) and a 12.9" iPad set (2048×2732), six each, both accepted sizes. 1290×2796 is *not* a listed iPhone size and was replaced. The 6.9" slot is 1320×2868 and will be captured on the iPhone 17 Pro Max via TestFlight — see [`DEVICE_TEST_SCRIPT.md`](../docs/release/DEVICE_TEST_SCRIPT.md). |
| Custom icons | **Done.** 1024×1024, RGB, no alpha, solid corners — validated by the gate. |
| Pricing setup for subscriptions | **N/A.** Free, no IAP. Removes Guideline 3.1.1 entirely. |
| Regional availability configured before submitting | App Store Connect UI. Default is all regions; leave it unless you have a reason. |
| Most apps rejected first try | Likely. The mitigations are in this folder: the demo account clears the gate, the invite screen explains itself, deletion is reachable everywhere, and the review notes pre-empt the questions. |

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

### 2. First Swift compile — **unblocked**; the archive is not

A Mac is available, on macOS 13 Ventura. That compiles: Ventura runs Xcode 15.2,
which ships Swift 5.9 and the iOS 17.2 SDK, and this target asks for Swift 5.9
and iOS 17.0. No SwiftUI here has ever been through a compiler — roughly 500
lines — so expect first-build errors and treat them as the expected outcome.
[`MAC_START_HERE.md`](MAC_START_HERE.md) lists the files in likelihood order.

**Uploading is a separate problem.** App Store uploads have required Xcode 26+
since 28 April 2026 and Xcode 26 needs macOS Sequoia 15.6+, so the archive has
to come from somewhere else: the `ios` job on `macos-latest` in CI, Xcode Cloud,
an hourly cloud Mac, or newer hardware.

### 3. Screenshots — done, with a planned upgrade

Six iPhone shots at 1284 × 2778 (6.5") and six iPad shots at 2048 × 2732
(12.9"), both accepted sizes. iPad is required because the target is universal.

The 6.9" slot is **1320 × 2868**, not 1290 × 2796 as this section used to say —
1290 × 2796 is the iPhone 15 Pro Max's native resolution and is not a listed
App Store Connect size at all. 1320 × 2868 is exactly what an iPhone 17 Pro Max
produces, so the final iPhone set will be captured on hardware through
TestFlight.

The iPad set stays on the 12.9" simulator. The iPad A16 available for testing is
1640 × 2360, which is **not** a listed iPad size (the slots are 2064 × 2752,
2048 × 2732 and 1488 × 2266), so it is a device-testing machine, not a capture
device.

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
