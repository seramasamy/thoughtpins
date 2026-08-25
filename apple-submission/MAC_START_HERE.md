# Mac: start here

You have the Mac. This is the whole sequence, in order, with what to expect at
each step. Nothing here needs the Apple Developer account except Stage 3 — do
Stages 1 and 2 today regardless of whether enrolment has cleared.

**Do not use a ZIP.** Clone the repository. You will be fixing compile errors on
this machine and pushing them back, and a ZIP throws away git history, branch
state, and any way to get the fixes home.

---

## Stage 0 — Check what this Mac can actually do

```bash
sw_vers                         # ProductVersion: the number that decides everything
xcodebuild -version 2>/dev/null || echo "no Xcode yet"
```

**If `ProductVersion` starts with 13 (Ventura), this Mac can compile the app but
cannot submit it.** Three verified facts, and they do not bend:

| | |
|---|---|
| macOS 13 Ventura runs at most **Xcode 15.2** | 15.3+ requires macOS 14 |
| Xcode 15.2 ships **Swift 5.9** and the **iOS 17.2 SDK** | this target needs Swift 5.9 and iOS 17.0 — it fits |
| App Store uploads have required **Xcode 26+** since **28 April 2026** | Xcode 26 needs macOS Sequoia 15.6+ |

So Ventura is genuinely useful for Stages 1–3 and genuinely cannot do Stage 4.
Split the work accordingly — this is not a reason to stop.

**If `ProductVersion` is 13.0–13.4**, run Software Update first. Ventura's last
release is 13.7.x, it is free, and Xcode 15.2 refuses to install below 13.5.

**Where the archive comes from instead.** `.github/workflows/ci.yml` already has
an `ios` job on `macos-latest`, which carries a current Xcode. It runs
`swift test` and `prepare_ios_submission.sh` today, and is the natural place to
grow the signed archive. Trigger it by hand:

```bash
gh workflow run ci.yml --ref main -f run_native=true
```

Other routes if that does not suit: Xcode Cloud (Apple's own, 25 compute
hours/month with the developer programme), an hourly cloud Mac, or a used Apple
silicon machine. All of them are Stage 4 problems, not today's.

---

## Stage 1 — Get the tree onto the Mac (15 minutes)

```bash
# Xcode from the App Store first, then launch it once to accept the licence.
# On Ventura the App Store may offer nothing: download Xcode 15.2 from
# https://developer.apple.com/download/all/ instead — a free Apple ID is enough.
xcode-select --install          # command line tools, if not already there
xcodebuild -version             # 15.2 on Ventura; 26+ on Sequoia or newer

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

# List what this Xcode actually has before naming a destination. An unknown
# simulator name fails with an error that reads like a build failure but is not.
xcrun simctl list devicetypes | grep iPhone

xcodebuild -project ThoughtPins.xcodeproj -scheme ThoughtPins \
  -destination 'platform=iOS Simulator,name=iPhone 15 Pro' \
  CODE_SIGNING_ALLOWED=NO build
```

`iPhone 15 Pro` is the right destination on Xcode 15.2; the iPhone 17 simulators
do not exist there. On Xcode 26 substitute the current handset.

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

Minimum device set — take whichever of each pair your Xcode offers:

- **iPhone SE (3rd gen)** — the narrowest supported, present in both
- **iPhone 15 Pro** (Xcode 15.2) or iPhone 17 Pro (Xcode 26)
- **iPhone 15 Pro Max** or iPhone 17 Pro Max — the widest
- **iPad mini** (6th gen or A17 Pro)
- **iPad Pro** (12.9-inch 6th gen, or 13-inch)

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

Screenshots come from Stage 3 — but **read the exact required pixel sizes off
App Store Connect itself** when you get there rather than trusting a number
written down months earlier. Apple moves the required display class roughly
yearly, and the current one may want a simulator Xcode 15.2 does not have. If
so, capture them wherever the archive is built.

---

## What you do not need

- **A ZIP handoff.** Clone.
- **Android.** Nothing in the Apple path touches it.
- **20 testers.** That is a Play requirement. TestFlight has no minimum — you can
  install on your own device and submit.
