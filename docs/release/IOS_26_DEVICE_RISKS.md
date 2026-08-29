# What has never run on the target device

Everything verified so far ran on iOS 17.2 simulators no wider than an iPhone
15 Pro Max. The app will first run for real on an **iPhone 17 Pro Max on
iOS 26**. This is the audit of anything whose appearance or layout comes from
an OS default that Apple can restyle between versions, rather than from a value
we set. Items are listed whether or not they were changed.

## The one that matters most

**Every screen background comes from SwiftUI's `Form`/`List` defaults, not from
`ThoughtPinsTheme`.** `canvas` and `surface` are defined and are used for the
chat bubble and the route capsule — nothing else. The app's actual background
is `systemGroupedBackground`, which on iOS 17.2 measures `#F2F2F7` light and
`#000000` dark.

That is coupled to a decision already shipped: `LaunchBackground` was set to
exactly those two values so the cold launch stops stepping from warm near-black
to pure black. **Those are hard-coded numbers matched to iOS 17.2's system
colour.** If iOS 26 changes `systemGroupedBackground`, the launch screen stops
matching and the cold-launch jump returns — in the opposite direction.

Two ways out, and they are the same work either way:

1. Paint the Forms with `ThoughtPinsTheme.canvas` and set `LaunchBackground` to
   the same value. Then nothing depends on Apple. This is the "warm paper" pass
   deferred earlier; it needs re-verification in both themes, both device
   classes, and the accessibility sizes.
2. Leave it and re-measure on the first real device. Sample the settled
   background on an iOS 26 device and compare against the two values in
   `LaunchBackground.colorset`. If they differ, update them.

**Do (2) on the first device boot regardless** — it is a two-minute check and it
is the only thing here that produces a visible defect on launch.

## Checked and deliberately left inheriting the system

| Where | What | Why it is left alone |
|---|---|---|
| `ThoughtPinsScreens.swift` memory list | `Color(.systemGroupedBackground)` behind the readable column | Here the dependence *is* the point: it has to match the `Form` background beside it. Hard-coding it would guarantee a mismatch the moment Apple changes the system colour, which is the opposite of what we want |
| Status banner | `.thinMaterial` | Adapts to light and dark on its own, and it is transient — it now clears after four seconds. An explicit colour would be more predictable but would need its own light/dark pair |
| Recap, Account | `.pickerStyle(.segmented)` | Intended to look native. Inheriting Apple's restyling is correct for a standard control |
| Chat | `.buttonStyle(.bordered)`, `.textFieldStyle(.roundedBorder)` | Same reasoning |
| Titles | `.system(.title, design: .serif)` and friends | Dynamic Type aware, so they scale with the person's setting rather than a fixed point size |

## Checked and clean

- **No screen-geometry assumptions.** No `UIScreen.main`, no `.bounds`, no
  hard-coded aspect ratios anywhere in the app or the native target.
- **No safe-area assumptions.** Nothing calls `ignoresSafeArea`, so a taller
  screen or a different sensor housing changes nothing.
- **The single `GeometryReader`**, in `ThoughtPinsBrandMark`, is self-relative:
  every dimension is a ratio of `min(width, height)`, so the mark is resolution
  and size independent.
- **Hard-coded sizes are intentional and not OS-dependent.** 44×44 is Apple's
  minimum tap target and should stay fixed; 72×72 is the decorative brand mark;
  6×6 are the thinking dots.
- **Layout adapts by size class, not by device.** `thoughtPinsReadableColumn`
  keys off `horizontalSizeClass`, so a wider iPhone 17 Pro Max is still compact
  and still gets the full-width phone layout, exactly as an iPhone 15 Pro Max
  does. Nothing keys off a device name or a pixel width.

## Not appearance, but first-device-only

- **Sign in with Apple** cannot be exercised until the capability is on the App
  ID and `oauth_apple_enabled` is switched on.
- **Google sign-in** is suppressed by design until Apple sign-in exists; see
  `apple-submission/AFTER_DEVELOPER_ACCOUNT.md`.
- **Microphone permission** has only ever been granted by a simulator.
  `simctl privacy revoke microphone` does not take -- recording started anyway
  -- so the denied path has never actually run. It is device work, and it is
  written out in "Device tests that cannot be faked" below.
- **iOS 26 Dynamic Type** may add steps above AX5. The composer switches layout
  on `dynamicTypeSize.isAccessibilitySize`, which is a category test rather than
  a fixed list, so a new larger step takes the stacked layout automatically.

## Device tests that cannot be faked

Each of these needs a real device because the simulator either cannot produce
the state or produces it and then ignores it. Run them on the first build that
reaches hardware, before TestFlight goes wider.

### Microphone denied

`ThoughtPinsVoiceRecorder.start()` asks for permission and, when refused, sets
`"Microphone access was not granted. You can attach an audio file instead."`
and returns without opening the session. That branch has never executed.

1. Fresh install. Chat tab, tap the mic.
2. At the system prompt, tap **Don't Allow**.
3. Expect: no recording indicator, no timer, the message above on screen, and
   the file-attach route still working. Nothing is uploaded.
4. Tap record again. iOS does not prompt a second time; the same message must
   appear immediately rather than a stuck or silent control.
5. Settings > Thought Pins > Microphone > on. Return to the app, record, and
   confirm a real recording uploads and transcribes.

Note for step 4: once permission is permanently denied the message is the only
feedback, and the app offers no route to Settings. That is allowed, and the
message does name a working alternative. Whether to add an "Open Settings"
button is a product call, not a submission blocker -- flagged here rather than
changed.

### Microphone interrupted mid-recording

Start a recording, then place a call to the device (or start a FaceTime call).
`AVAudioSession.interruptionNotification` should stop the recording and leave
what was captured, not a zero-byte upload.

### Sign in with Apple

Cannot run until the capability is on the App ID and `oauth_apple_enabled` is
on. See `apple-submission/AFTER_DEVELOPER_ACCOUNT.md`.
