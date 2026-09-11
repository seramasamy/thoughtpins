# Native UI review

This disposable app builds the production SwiftUI package against fictional
fixtures on localhost. It has its own bundle identifier and cannot reach the
production API. The test covers all five destinations, search and keyboard
dismissal, a chat prompt and reply, account access, sign-out, and email sign-in. Screenshots
are XCTest attachments. Run on iPhone SE, a current iPhone, and iPad in both
appearances. Separate tests cover landscape and the largest Dynamic Type size.

`AuthAndCaptureTests` adds password visibility, whitespace validation, 401/429
sign-in recovery, phone keyboard dismissal, signup/legal controls at the largest
text size, failed-link draft preservation, and Capture back navigation.
`ModelTests/SubmissionTests` verifies the acceptance contract directly, including
disk-write failure, durable offline storage, duplicate-request guards, and
invalid input. Tests run serially against the shared fixture server.

From the repository root, with frontend dependencies installed and Node 22.6+:

```sh
node --experimental-strip-types frontend/scripts/native-review-server.mjs
```

In another terminal, generate the ignored test project:

```sh
xcodegen generate --spec mobile/ios/ThoughtPinsUIReview/project.yml
xcodebuild -project mobile/ios/ThoughtPinsUIReview/DesignReview.xcodeproj \
  -scheme DesignReview -destination 'platform=iOS Simulator,name=iPhone SE (3rd generation)' \
  -parallel-testing-enabled NO -derivedDataPath .tmp/native-ui-derived \
  -resultBundlePath reports/native-ui-review.xcresult test
```

Choose a fresh result path for each run. The server changes only fixture dates
so the Recap remains populated. It uses the same mock API as browser tests;
no model-provider call, credentials, or user data is involved.

`RecoveryTests` also exercises 503/429 chat recovery, an explicit successful
retry, whitespace validation, keyboard dismissal, no-result search recovery,
the export share sheet, cancelling account deletion, and cancelling the voice
disclosure before recording. It resets the fictional API between cases using
the loopback-only `/__review` endpoint. Tests must run serially because that
fixture state is shared. The server never logs request bodies.

For dark mode, boot the selected simulator and set its appearance before testing:

```sh
xcrun simctl boot <device-uuid>
xcrun simctl ui <device-uuid> appearance dark
```

`testAccessibilityScreens` sets `.accessibility5` in the disposable host for
that launch, without changing the production app or system settings. Use
`-only-testing:DesignReviewTests/CaptureTests/testAccessibilityScreens` to run
it separately. `testLandscapeScreens` rotates an iPad simulator and restores
portrait. The harness mirrors the production orientation policy: iPhone uses
portrait, and iPad supports rotation. The landscape test skips iPhone.

Restore the simulator's appearance when finished. Inspect layout
and reachability at the largest sizes; screenshots alone do not prove VoiceOver
order or native behavior on an iOS SDK newer than the installed Xcode.
