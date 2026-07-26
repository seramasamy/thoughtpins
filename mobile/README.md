# Thought Pins Mobile

Thought Pins has one backend contract and two native clients:

- `ios/ThoughtPinsCore` and `android/thoughtpins-core` contain UI-independent API, session, version-policy, and offline-draft code.
- `ios/ThoughtPinsApp` and `android/thoughtpins-app` contain the SwiftUI and Jetpack Compose product surfaces.
- `ios/ThoughtPinsNative` is the XcodeGen app target. `android/` is a complete Gradle workspace.

The native apps keep chat primary while exposing journal capture, user-initiated voice notes, source ingestion, memory cards, recaps, export, Obsidian portability, account deletion, maintenance handling, and offline drafts. Email or phone registration creates an authenticated session before content can be sent. AI processing requires an explicit disclosure acceptance, and microphone capture adds a just-in-time disclosure. The public store configuration discards recordings after transcription. A private/self-hosted deployment can separately expose encrypted voice retention only when its server feature gate is enabled and the user completes unbundled consent.

## Store Review Posture

- The iOS app includes Sign in with Apple and only shows optional OAuth providers advertised by `/v1/config`.
- Privacy, terms, AI disclosure, support, and account-deletion links are reachable before and after authentication.
- Account deletion is available in-app with destructive confirmation.
- The iOS privacy manifest declares linked account, device, and user-content data for app functionality and declares no tracking.
- The submitted store configuration sets `VOICE_ARCHIVE_ENABLED=false`; voice
  audio is temporary, while its transcript follows normal journal retention and
  deletion controls.
- Android disables cleartext traffic and backup, and iOS uses an HTTPS production API endpoint.
- Source readers show publisher metadata, summaries, and the canonical URL supplied by the user. Internal retrieval text and storage paths are not exposed.
- App icons and launch assets use the canonical integrated brain/map-pin mark.

Legal and store metadata still require human/legal review before submission. Native store readiness also requires signed release archives, a live review backend and demo account, App Store Connect and Play Console records, final native screenshots, and simulator/device smoke evidence.

## Android Compose Shell

The Android surface (`android/thoughtpins-app`) follows the shared warm-paper design contract in `DESIGN.md`:

- Both light and dark Material 3 color schemes are defined from the canonical palette: the `#f8f8f6` canvas, terracotta brand `#e8612b` reserved for fills and brand moments, the AA-safe action tone `#b33e16` for text and buttons on light surfaces, sage `#587465` and blue as semantic support colors, and a `#1a1714` dark canvas. The shell follows `isSystemInDarkTheme()`.
- Display titles and the brand wordmark use a serif family; body and reading text use the platform sans. All type keeps scalable `sp` units so Android font-size settings apply.
- The integrated brain/map-pin mark is drawn as a Compose `Canvas` from the canonical 128-unit geometry and appears on the auth hero and list empty states. It is not a raster copy; the adaptive launcher icon remains the canonical vector.
- A three-dot pulse sits beside "Thinking with your memory" and collapses to static dots when the system animator duration scale is zero, so reduced-motion is respected. Asynchronous status text carries polite live-region semantics.
- A persistent maintenance banner is visually distinct from the transient snackbar used for one-off confirmations. List screens have oriented empty states, and capture stays reachable from the top app bar.

These are source-level design notes validated by `scripts/check_native_review_handoff.py`; they are not a substitute for an emulator screenshot or a Gradle build, which require the Android toolchain.

## Build And Validation

Android (Windows, macOS, or Linux):

```text
cd mobile/android
./gradlew :thoughtpins-app:assembleDebug :thoughtpins-app:lintDebug
./gradlew :thoughtpins-app:bundleRelease
```

iOS requires macOS with current Xcode and XcodeGen:

```text
cd mobile/ios/ThoughtPinsNative
xcodegen generate
xcodebuild -project ThoughtPins.xcodeproj -scheme ThoughtPins \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  CODE_SIGNING_ALLOWED=NO build
```

From the repository root, run:

```text
python scripts/check_mobile_core.py
python scripts/check_ios_submission_source.py
python scripts/check_native_review_handoff.py
```

These source gates do not replace an Xcode archive, signing validation, or device testing.

## Deliberate Omissions

Push notifications, photo access, and share extensions are not enabled in the review target. Optional microphone capture is user-initiated from the voice-note control, has an explicit purpose string and privacy disclosure, and sends recordings through the journal transcription workflow. Other capabilities should only be added with a complete user workflow, accurate purpose strings, privacy disclosures, platform entitlements, and tests.
