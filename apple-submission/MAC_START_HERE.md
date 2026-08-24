# Mac: start here

You have the Mac. This is the whole sequence, in order, with what to expect at
each step. Nothing here needs the Apple Developer account except Stage 3 — do
Stages 1 and 2 today regardless of whether enrolment has cleared.

**Do not use a ZIP.** Clone the repository. You will be fixing compile errors on
this machine and pushing them back, and a ZIP throws away git history, branch
state, and any way to get the fixes home.

---

## Stage 1 — Get the tree onto the Mac (15 minutes)

```bash
# Xcode from the App Store first, then launch it once to accept the licence.
xcode-select --install          # command line tools, if not already there
xcodebuild -version             # expect Xcode 26 or newer

git clone https://github.com/seramasamy/thoughtpins.git
cd thoughtpins
```

The repo is private, so git will ask for GitHub credentials. Use a personal
access token, not your password.

```bash
./scripts/bootstrap_macos.sh
```

That one script creates the Python virtual environment, installs the locked
frontend dependencies, runs the source gates, generates the Xcode project with
XcodeGen, and attempts an unsigned generic Simulator build. Add
`--install-missing` if it complains about Homebrew packages.

---

## Stage 2 — The first compile (expect it to fail)

**This is the first time any Swift in this project has been through a
compiler.** Roughly 500 lines have only ever been read, never built. Failures
here are the expected outcome, not a sign anything is wrong.

```bash
swift test --package-path mobile/ios/ThoughtPinsCore
```

That runs `APIClientTests` and `DraftStoreTests` — the shared client and the
draft store, including the three tests proving a deleted account's offline
drafts cannot reach the next person on the device.

Then the app target:

```bash
cd mobile/ios/ThoughtPinsNative
xcodegen generate
xcodebuild -project ThoughtPins.xcodeproj -scheme ThoughtPins \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  CODE_SIGNING_ALLOWED=NO build
```

### Where errors will be, in likelihood order

| File | What is unverified in it |
|---|---|
| `ThoughtPinsReviewShell.swift` | The invite gate view, auth form restructure, `registrationBlocker`, colour-scheme Apple button |
| `ThoughtPinsAppModel.swift` | `refreshInviteStatus`, `redeemInvite`, `isBlockedByInviteGate`, reworked `register` |
| `ThoughtPinsScreens.swift` | `scenePhase` recording teardown, importance row restructure, `contentShape` |
| `APIClient.swift` / `Models.swift` | `InviteStatusResponse`, `inviteStatus()`, `redeemInvite()` |
| `ThoughtPinsNativeApp.swift` | Base-URL validation replacing a force-unwrap |
| `DraftStore.swift` | `purge()` |

Most likely categories: a missing `import`, an `@MainActor` isolation
complaint (the target builds with `SWIFT_STRICT_CONCURRENCY: complete`), or a
SwiftUI `ViewBuilder` type-inference error asking you to break up a large body.

Fix, commit, push. The gates on Windows will keep verifying everything else.

---

## Stage 3 — Simulator, and iPad properly

Once it builds, run it. A former App Store reviewer's account is that they test
iPad **almost always**, even when the iPad box is unchecked — and this target
claims universal (`TARGETED_DEVICE_FAMILY: "1,2"`), so iPad is certain to be
opened.

Minimum device set:

- iPhone SE (3rd gen) — the narrowest supported
- iPhone 17 Pro
- iPhone 17 Pro Max
- iPad mini (A17 Pro)
- iPad Pro 13"

For each: launch, sign in with the demo account, send a chat message, record a
voice note, open Account, export, rotate to landscape.

Then the four things only a simulator shows:

- **Dynamic Type at AX5** — Settings → Accessibility → Display & Text Size
- **VoiceOver order** on Chat and Account
- **Dark mode cold launch** — confirm no white flash (fixed, never verified)
- **iPad Slide Over at 320pt** — drag the app into a Slide Over window

On iPad specifically, look at the chat column measure and the memory-card grid.
An iPhone layout stretched across 13 inches is exactly what "feels broken" means
to a reviewer.

---

## Stage 4 — Signing and archive

Follow [`../docs/release/MAC_XCODE_V1_EXECUTION_CHECKLIST.md`](../docs/release/MAC_XCODE_V1_EXECUTION_CHECKLIST.md)
from section 5. It covers signing, the private release values, the archive and
validation. [`AFTER_DEVELOPER_ACCOUNT.md`](AFTER_DEVELOPER_ACCOUNT.md) has the
App Store Connect metadata and the order to do it in.

Screenshots come from Stage 3: iPhone 6.9" at 1290 × 2796 and iPad 13" at
2064 × 2752, at least three each.

---

## What you do not need

- **A ZIP handoff.** Clone.
- **Android.** Nothing in the Apple path touches it.
- **20 testers.** That is a Play requirement. TestFlight has no minimum — you can
  install on your own device and submit.
