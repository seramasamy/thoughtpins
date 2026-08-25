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

## Stage 2 — The first compile

**Status as of 2026-08-25:** this has been done on a Ventura / Xcode 15.2
machine. `ThoughtPinsCore` and `ThoughtPinsApp` both compile clean under
`SWIFT_STRICT_CONCURRENCY: complete`, and 15 of 15 core tests pass. Exactly one
file remains uncompiled anywhere — see **GoogleSignIn** below. Read the two
traps here before running anything; both cost a session real time.

```bash
cd mobile/ios/ThoughtPinsCore
xcodebuild test -scheme ThoughtPinsCore \
  -destination 'platform=iOS Simulator,name=iPhone 15 Pro'
```

That runs `APIClientTests`, `AuthFailureTests` and `DraftStoreTests` — the
shared client, the sign-in failure mapping, and the draft store, including the
three tests proving a deleted account's offline drafts cannot reach the next
person on the device.

### Trap 1: `swift test` fails silently on Ventura

**Do not use `swift test --package-path mobile/ios/ThoughtPinsCore` on macOS
13.** It compiles everything and then cannot run any of it. `swift test` builds
for the *host*, `Package.swift` declares `.macOS(.v14)`, and this machine is
13.7, so the bundle comes out stamped `minos 14.0`:

```
$ otool -l .build/x86_64-apple-macosx/debug/ThoughtPinsCorePackageTests.xctest/Contents/MacOS/ThoughtPinsCorePackageTests \
    | grep -A4 LC_BUILD_VERSION
      cmd LC_BUILD_VERSION
 platform 1
    minos 14.0
      sdk 14.2
```

The reason it wastes time is that it fails with **no diagnostic whatsoever**.
`swift test` prints `Build complete!` and exits 1, printing nothing. Running the
bundle by hand exits 83 — XCTest's "unable to load bundle" — also silently. It
reads as though the tests passed and something odd happened afterwards. They
never ran.

**Do not lower `.macOS(.v14)` to fix this.** The comment in `Package.swift`
explains what that floor is for. The simulator command above builds for iOS,
which is what the app ships for, and sidesteps the host entirely. On a Mac
running macOS 14+, plain `swift test` works fine.

### Trap 2: GoogleSignIn 9.1.0 cannot resolve on Xcode 15.2

Confirmed, not hypothetical. Verbatim:

```
$ xcodebuild -project ThoughtPins.xcodeproj -scheme ThoughtPins \
    -destination 'platform=iOS Simulator,name=iPhone 15 Pro' \
    CODE_SIGNING_ALLOWED=NO build

xcodebuild: error: Could not resolve package dependencies:
  Dependencies could not be resolved because 'googlesignin-ios' >= 9.1.0
  contains incompatible tools version (6.0.0) and root depends on
  'googlesignin-ios' 9.1.0.
```

GoogleSignIn 9.1.0 ships a `swift-tools-version:6.0` manifest, and a 5.9
toolchain cannot parse a manifest above its own version — it fails before
compiling a line. There is no flag for it and no workaround short of a newer
Xcode.

**Do not remove or downgrade the dependency.** `project.yml` pins
`exactVersion: 9.1.0` and `scripts/check_ios_submission_source.py` fails the
build without it. Google sign-in cannot be exercised on this machine anyway: it
needs client IDs that only exist in a signed release build, and with
`GOOGLE_IOS_CLIENT_ID` empty the provider's `supports(_:)` returns false.

The consequence: **`GoogleOAuthTokenProvider.swift` cannot be compiled here in
the normal way**, because it is the only importer of GoogleSignIn. Everything
else in the app compiles.

It has since been compiled against a stand-in. Each declaration the file uses
was checked against the real 9.1.0 public headers and reproduced with the same
nullability — `GIDSignIn.sharedInstance` (class property), `handleURL:`,
`signInWithPresentingViewController:completion:` (the async form the file
calls), `GIDSignInResult.user` (non-null), `GIDGoogleUser.idToken` and
`.profile` (both nullable), `GIDToken.tokenString` and `GIDProfileData.name`
(both non-null). Against that, the file compiles clean under
`SWIFT_STRICT_CONCURRENCY: complete` for the iOS 17 simulator, and its symbols
link into the app binary.

So its syntax, its isolation, and its use of that API are no longer unknown.
What a stand-in cannot prove is that the real package resolves, links, and
behaves — that still needs the `ios` job in `.github/workflows/ci.yml` on
`macos-latest`, and it is the last thing standing between here and a verified
archive.

### Running the app on a Ventura machine anyway

The rest of the app can be built and run by excluding that single file. Do it in
a scratch copy outside the repository — never by editing `project.yml`, which
the submission gate checks. Two things that are not obvious:

- **Build ad-hoc signed, not `CODE_SIGNING_ALLOWED=NO`, if you intend to sign
  in.** An unsigned app has no `application-identifier` entitlement, so
  `KeychainSessionStore.save` fails and sign-in reports failure even though the
  network call succeeded. Use `CODE_SIGN_IDENTITY="-" CODE_SIGNING_REQUIRED=NO
  CODE_SIGNING_ALLOWED=YES`. (`ThoughtPinsAuthFailure.sessionNotStored` now
  names this case explicitly rather than blaming the password.)
- **Seed a local backend** rather than pointing at production:
  `scripts/seed_review_account.py` with `DATABASE_URL` on SQLite and
  `REQUIRE_API_AUTH=true` gives a populated account. Without `REQUIRE_API_AUTH`
  the dev server serves an empty default user to unauthenticated calls, and the
  app looks signed in with no data.

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

### What the first compile actually found

For the record, since the list of "where errors will be" guesses was mostly
wrong. The real ones, all fixed:

| Where | What |
|---|---|
| `ThoughtPinsAppModel.swift` | `ThoughtPinsApiClient` — the actor is `ThoughtPinsAPIClient` |
| `ThoughtPinsNativeProviders.swift` | Two `init`s used as default arguments needed `nonisolated`; Swift 5.9 type-checks a default argument as nonisolated whatever isolation encloses it (SE-0411 fixes this in Swift 6) |
| `Models.swift` | Four models declared snake_case `CodingKeys` while the decoder sets `convertFromSnakeCase`. The two cancel out, so `TokenResponse`, `ClientConfig`, `IngestResponse` and `DeviceRegistration` were all undecodable — login, OAuth, refresh, client config, ingest and device registration could not complete. Caught by a test, not the compiler. |

The concurrency guesses were right in kind — the isolation complaint was real.
The decoding bug was the one no amount of reading had found, and it is now
gated by `scripts/check_ios_submission_source.py`.

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

Then the four things only a simulator shows. **All four were run on
2026-08-25** (iPhone 15 Pro and iPad Pro 12.9-inch 6th gen, iOS 17.2); what they
found is recorded here so it is not re-derived:

- **Dynamic Type at AX5** — Settings → Accessibility → Display & Text Size.
  Found: the chat composer could not fit mic, field and Send on one row; the
  field collapsed to about two visible characters. Fixed — the composer picks
  an `HStack` or `VStack` from `dynamicTypeSize`.
- **VoiceOver order** on Chat and Account. Both read in visual order; no change
  needed. Note the chat field is exposed as a `TextView` carrying its
  placeholder, which is correct, not a missing label.
- **Dark mode cold launch** — no white flash. The launch background was
  `#1A1714` while the app settles on `systemGroupedBackground`, so dark launches
  stepped warm-black to pure black; `LaunchBackground` now matches where the app
  lands. Verify by frame-sampling, not by eye: the background is `#000000` on
  every frame in dark and `#F2F2F7` in light.
- **iPad Slide Over at 320pt** — drag the app into a Slide Over window. Holds:
  nothing clips, all five tabs stay labelled. `simctl` cannot drive Slide Over,
  so this was checked by reproducing what it changes — a 320pt frame plus a
  compact `horizontalSizeClass`.

On iPad specifically, look at the chat column measure and the memory-card grid.
An iPhone layout stretched across 13 inches is exactly what "feels broken" means
to a reviewer. **This was the worst of what the run found:** nothing in the app
constrained width anywhere — no `horizontalSizeClass`, no max width in any of
the six screens — so the "Use private memories" switch sat ~1200pt from its
label and the composer ran 1270pt. `thoughtPinsReadableColumn` in
`ThoughtPinsTheme.swift` now caps the chat column and the memory-card list at
680pt in regular width only, leaving every iPhone untouched. If you add a
screen, apply it.

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
