# Thought Pins iOS Target

This directory is the production-shaped iPhone and iPad target. XcodeGen keeps the project definition reviewable in `project.yml`; generated `.xcodeproj` files are build artifacts and should not become the source of truth.

## Generate And Build

On macOS with current Xcode and XcodeGen:

```text
xcodegen generate
xcodebuild -project ThoughtPins.xcodeproj -scheme ThoughtPins \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  CODE_SIGNING_ALLOWED=NO build
```

For a signed archive, follow
[`docs/release/MACOS_XCODE_APP_STORE_RUNBOOK.md`](../../../../docs/release/MACOS_XCODE_APP_STORE_RUNBOOK.md).
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

Nothing off a Mac can compile SwiftUI. The layout claims in this target —
Dynamic Type at accessibility sizes, VoiceOver order, iPad Slide Over at 320pt,
Stage Manager, the launch-screen transition — are reasoned from the source and
remain unverified until someone runs the simulator. The device matrix that *is*
executed lives in `frontend/e2e/ios-device-matrix.spec.ts`: nine shipping iPhone
and iPad sizes driven through WebKit, which is the same engine iOS Safari uses.
That covers the web app on those devices. It is not a substitute for building
this target.
