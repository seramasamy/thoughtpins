# Thought Pins iOS Target

This directory is the production iPhone and iPad target. XcodeGen keeps the project definition reviewable in `project.yml`; regenerate the Xcode project from that specification for release builds.

## Generate And Build

On macOS with current Xcode and XcodeGen:

```text
xcodegen generate
xcodebuild -project ThoughtPins.xcodeproj -scheme ThoughtPins \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  CODE_SIGNING_ALLOWED=NO build
```

For a signed archive, follow
[`docs/release/MACOS_XCODE_APP_STORE_RUNBOOK.md`](../../../docs/release/MACOS_XCODE_APP_STORE_RUNBOOK.md).
The repository scripts deliberately keep the Apple team, certificates,
provisioning profiles, review credentials, and App Store Connect credentials out
of source control:

```text
./scripts/ios_release.sh preflight
APPLE_TEAM_ID=ABCDE12345 IOS_BUILD_NUMBER=1 ./scripts/ios_release.sh archive
```

The generated `.xcodeproj` is build output. `project.yml` remains the source of
truth and should be regenerated on each clean release host.

Before upload, verify the privacy manifest and App Store Connect privacy answers describe the same data flow; test Sign in with Apple, registration, explicit AI-processing consent, account deletion, maintenance mode, offline drafts, legal links, and the reviewer demo account on a clean device.

## The privacy manifest tracks the code, not a checklist

`PrivacyInfo.xcprivacy` shipped with an empty `NSPrivacyAccessedAPITypes` while
the chat screen kept its voice disclosure in `@AppStorage`. That is a
required-reason API, and the upload fails with **ITMS-91053** rather than
warning. `check_ios_submission_source.py` now reads the Swift sources and
requires a declaration for every required-reason category it finds a call to —
so the next `UserDefaults`, file-timestamp, disk-space or boot-time call fails
on Linux CI instead of in App Store Connect. It also fails the reverse: a
category declared that nothing uses.

## What a Windows or Linux host can prove, and what it cannot

`check_ios_submission_source.py` validates project settings, the Info.plist,
entitlements, the privacy manifest against actual API use, icon format, launch
appearances, and the local-data teardown wiring. `swift test --package-path
mobile/ios/ThoughtPinsCore` covers the client and the draft store, and runs on
the macOS CI job.

The [native review harness](../ThoughtPinsUIReview/README.md) compiles the actual
SwiftUI package against fictional loopback fixtures. Simulator review covers
iPhone SE through Pro Max, iPad mini and iPad Pro, dark/light appearance,
landscape on iPad, and large Dynamic Type. The model tests exercise failed
storage, offline persistence, overlapping requests, and retry acceptance.
XCTest screenshots are retained as result-bundle attachments.

Read the [release review log](../../../docs/release/RELEASE_POLISH_CHANGELOG.md)
and [earlier device review](../../../docs/release/UI_ROBUSTNESS_CHANGELOG.md)
for the evidence and its scope. GitHub's iOS job validates the shared package,
native authentication/capture tests, simulator build, and unsigned device
archive. It compares the entire pushed range so an earlier Swift change in a
batch cannot skip native verification.

A validation dispatch uses `run_native=true` and `upload_testflight=false`.
Uploading requires an explicit `upload_testflight=true` selection and signing
credentials. A local Xcode 15.2 simulator pass does not establish submission
eligibility: uploads require the current Apple-supported SDK. Physical-device
VoiceOver, real provider sign-in, signing/provisioning, and App Store Connect
processing still need their own release evidence.
