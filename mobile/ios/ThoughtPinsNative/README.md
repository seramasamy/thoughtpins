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
