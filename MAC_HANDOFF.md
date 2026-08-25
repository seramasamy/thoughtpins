# Mac Handoff — read this first

You are Claude Code running on a MacBook. Work has been happening on a Windows
machine, which can run everything in this repository *except* a Swift compiler.
This file is the handoff. Read [`AGENTS.md`](AGENTS.md) too — it holds the
repository-wide rules and they still apply.

---

## The one-sentence situation

**About 4,200 lines of Swift in this repository have never been compiled**, and
this Mac is the first machine capable of compiling them.

Everything else is verified: 840 Python tests pass, a 50-step release gate
passes, the Android app builds and has been run on an emulator against
production, and the backend is live. The Swift is the gap.

---

## Hard constraints on this machine

| | |
|---|---|
| macOS | **13.7 Ventura** |
| Xcode | **15.2** — the newest Ventura can install (15.3+ needs macOS 14) |
| Swift | **5.9**, iOS 17.2 SDK |
| Target needs | Swift 5.9, iOS 17.0 — **it fits** |

**This Mac cannot produce an App Store archive.** Uploads have required Xcode 26
or later since 28 April 2026, and Xcode 26 needs macOS Sequoia 15.6+. That is
not a problem to solve here. The archive comes from the `ios` job in
`.github/workflows/ci.yml`, which runs on `macos-latest`, or from Xcode Cloud.

**So the job on this machine is: make the Swift compile, and prove it runs in a
simulator.** Nothing else.

Practical consequences:

- Simulator names must come from `xcrun simctl list devicetypes`. `iPhone 15
  Pro` exists here; `iPhone 17 Pro` does not, and naming it produces an error
  that reads like a build failure but is not one.
- If a Swift Package manifest anywhere declares `swift-tools-version` above 5.9,
  this toolchain cannot parse it at all. `ThoughtPinsCore/Package.swift` was
  already lowered to 5.9 for exactly this reason — the comment in that file
  explains why, do not raise it back.

---

## Start here, in this order

### 1. The cheapest signal — do this before any setup

```bash
swift test --package-path mobile/ios/ThoughtPinsCore
```

Needs **only Xcode**. No Homebrew, no npm, no project generation, no external
package resolution. It compiles roughly 2,000 lines — `APIClient.swift`,
`Models.swift`, `DraftStore.swift`, `SessionStore.swift`, `VersionPolicy.swift`
and their tests — and it is where the first real errors will surface.

Expect failures. They are the expected outcome of code that has never met a
compiler, not a sign anything is wrong.

### 2. Full environment

```bash
brew install gh xcodegen node@22 python@3.13
./scripts/bootstrap_macos.sh --install-missing
```

macOS 13.7 ships Python 3.9 and this repository needs 3.11 or newer, hence
`python@3.13`. The script builds the virtual environment, installs frontend
dependencies, runs four gates, generates the Xcode project with XcodeGen, and
attempts an unsigned Simulator build.

### 3. The app target

```bash
cd mobile/ios/ThoughtPinsNative
xcodegen generate
xcrun simctl list devicetypes | grep iPhone      # check before naming one
xcodebuild -project ThoughtPins.xcodeproj -scheme ThoughtPins \
  -destination 'platform=iOS Simulator,name=iPhone 15 Pro' \
  CODE_SIGNING_ALLOWED=NO build
```

---

## Where the errors will be

Ordered by how recently the code changed and how little of it has been read by a
compiler.

| File | What is unverified |
|---|---|
| `ThoughtPinsApp/Sources/ThoughtPinsApp/ThoughtPinsReviewShell.swift` | `ThoughtPinsInviteView`, auth form restructure, `registrationBlocker`, colour-scheme Apple button, the `record()` guard |
| `ThoughtPinsApp/Sources/ThoughtPinsApp/ThoughtPinsAppModel.swift` | `refreshInviteStatus`, `redeemInvite`, `isBlockedByInviteGate`, `clearLocalAccountState`, reworked `register` |
| `ThoughtPinsApp/Sources/ThoughtPinsApp/ThoughtPinsScreens.swift` | `scenePhase` recording teardown, importance-row restructure, `contentShape` |
| `ThoughtPinsCore/Sources/ThoughtPinsCore/APIClient.swift` | `inviteStatus()`, `redeemInvite()`, `InviteRedeemRequest` |
| `ThoughtPinsCore/Sources/ThoughtPinsCore/Models.swift` | `InviteStatusResponse` |
| `ThoughtPinsNative/Sources/ThoughtPinsNativeApp.swift` | base-URL validation replacing a force-unwrap |
| `ThoughtPinsCore/Sources/ThoughtPinsCore/DraftStore.swift` | `purge()` |
| `ThoughtPinsCore/Tests/ThoughtPinsCoreTests/DraftStoreTests.swift` | new file, 3 tests |

Most likely error classes, in order:

1. A missing `import`.
2. `@MainActor` isolation complaints — the target builds with
   `SWIFT_STRICT_CONCURRENCY: complete`, which is stricter than most code
   expects.
3. SwiftUI `ViewBuilder` type-inference failures asking for a large `body` to be
   broken into smaller views.
4. `Sendable` conformance, for the same strict-concurrency reason — values
   captured by a `Task` inside a `@MainActor` type, or crossing the boundary
   between `ThoughtPinsAppModel` (`@MainActor`) and `FileDraftStore` (an
   `actor`), are the places to look first.

String interpolation was checked at byte level across all 17 Swift files: every
`\(...)` is correctly single-escaped. If something there looks wrong, it is the
reader's terminal, not the source.

---

## Known risk that is not your problem to solve

The app target depends on **GoogleSignIn 9.1.0** through SPM. If that package's
own manifest requires a toolchain newer than 5.9, package resolution in step 2
or 3 will fail on Xcode 15.2.

If that happens: **do not remove the dependency.** `project.yml` pins
`exactVersion: 9.1.0` and `scripts/check_ios_submission_source.py` fails the
build without it. Google sign-in cannot be exercised here anyway — it needs
client IDs that only exist in a signed release build.

Instead, keep working through `swift test` on `ThoughtPinsCore`, which has no
external dependencies, and let the Xcode 26 machine resolve the package. Record
the exact error so it is not rediscovered later.

---

## Rules that still apply

From [`AGENTS.md`](AGENTS.md), and they matter here:

- **Do not weaken a gate to make something pass.** If a gate is wrong, change
  the implementation, the gate, and the reason together.
- **Do not log journal text, tokens, or credentials.** Not even while debugging.
- Fix, commit, and push. The Windows machine keeps running the full 50-step gate
  against everything else, so small pushes are better than one large one.
- Signing material stays in Keychain and the developer portal. Never in this
  repository. `*.jks`, `*.keystore`, and `keystore.properties` are gitignored
  for the Android equivalent; do not add Apple equivalents either.

---

## After it compiles

Run it in a simulator. The submission depends on more than "it builds":

- **iPad matters as much as iPhone.** A former App Store reviewer's public
  account is that they test iPad almost always, and this target claims universal
  (`TARGETED_DEVICE_FAMILY: "1,2"`), so it will be opened there. Check the chat
  column measure and the memory-card grid — an iPhone layout stretched across 13
  inches is what "feels broken" means to a reviewer.
- **Dynamic Type at AX5**, Settings → Accessibility → Display & Text Size.
- **VoiceOver order** on Chat and Account.
- **Dark mode cold launch** — confirm no white flash. This was fixed and never
  verified.
- **iPad Slide Over at 320pt**, which is narrower than any iPhone.

---

## Fuller detail

- [`apple-submission/MAC_START_HERE.md`](apple-submission/MAC_START_HERE.md) —
  the same sequence with more explanation
- [`apple-submission/README.md`](apple-submission/README.md) — what blocks
  submission and what is already done
- [`docs/release/MAC_XCODE_V1_EXECUTION_CHECKLIST.md`](docs/release/MAC_XCODE_V1_EXECUTION_CHECKLIST.md)
  — signing and archive, for whichever machine ends up doing it
- [`AGENTS.md`](AGENTS.md) — repository-wide rules
