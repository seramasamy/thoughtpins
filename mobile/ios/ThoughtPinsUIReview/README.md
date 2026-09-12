# Native UI review

This disposable app builds the production SwiftUI package against fictional
fixtures on localhost. It has its own bundle identifier and cannot reach the
production API. The test covers all five destinations, search and keyboard
dismissal, a chat prompt and reply, account access, sign-out, and email sign-in. Screenshots
are XCTest attachments. Run on iPhone SE, a current iPhone, and iPad in both
appearances. Separate tests cover landscape and the largest Dynamic Type size.

`AuthAndCaptureTests` adds password visibility and editing after concealment,
whitespace validation, 401/429 sign-in recovery, consent-gated account creation,
phone keyboard dismissal, signup/legal controls at the largest text size,
failed-link draft preservation, and Capture back navigation. It exercises every
tab in portrait and, on iPad, landscape. `NavigationSupport` resolves both
traditional tabs and the floating tab cells used by current iPadOS.
`ModelTests/SubmissionTests` verifies the acceptance contract directly, including
disk-write failure, durable offline storage, duplicate-request guards, and
invalid input. Tests run serially against the shared fixture server.
CI retains both XCTest bundles and portable screenshot attachments so review
does not require the runner's Xcode version.

`ModelTests/PasswordFieldTests` checks exact Unicode and whitespace preservation,
selection across visibility changes, typing/deletion after concealment, and
publishing the latest input before Return submits. Password entry keeps one
native text field rather than replacing it when Show/Hide changes.

The app currently advertises ordinary password AutoFill. Automatic strong-password
generation needs a configured `webcredentials` association and a separate signed
device check; requesting it without that association blocked manual entry on the
iOS 17.2 review host. The tests wait for usable keyboard keys and check the entire
entered value. They do not prove a real iCloud/password-manager round trip.

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

GitHub runs iPhone and iPad reviews on separate macOS runners through
`.github/workflows/ios-native-review.yml`. Each waits for simulator boot
readiness and runs its cases serially against its own fixture server. This
avoids carrying CoreSimulator state between device families. Both matrix
reviews must pass before the production archive/signing job is eligible.
Artifact names include the device family so both XCTest results and portable
screenshots remain available without collisions.

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

The shared `ThoughtPinsOrbit` is a static vector network used by authentication,
Chat and empty states. Inspect it in light/dark appearance on compact iPhone and
iPad; it has no timer, hit targets or VoiceOver elements.
`ThoughtPinsThinkingDots` uses a bounded TimelineView only for work feedback,
pausing when its view disappears, its scene is inactive, or Reduce Motion is
enabled. Button press feedback also honors Reduce Motion. Keep those lifecycle
checks separate from appearance review; a screenshot cannot prove them.
