# Device test script — Thought Pins v1

Written before the build exists, so the day it lands this is thirty minutes and
not a day. Every item here is something a simulator either cannot produce or
produces and then ignores; the reasoning that stands in for them today is in
[`IOS_26_DEVICE_RISKS.md`](IOS_26_DEVICE_RISKS.md), and this is where that
reasoning finally gets measured.

**Hardware available:** iPhone 17 Pro Max (1320 × 2868), iPhone 17 Pro, iPad A16
(1640 × 2360). All on iOS/iPadOS 26.

**How to read this.** Each test says what to do, what you should see, and what
counts as a failure. "Failure" means stop and write it down — not "looks a bit
off". Record the result next to each heading as PASS / FAIL / N/A with a date.

**Screenshots are a separate job.** See "What this is not" at the end.

**This run is also the iOS-26 SDK re-verification.** Every "ARTIFACT" claim in
`apple-submission/SUBMISSION_STATUS.md` was verified on an Xcode 15.2 / iOS 17.2
build. App Store Connect requires the Xcode 26 / iOS 26 SDK, and that rebuild
can restyle system backgrounds, Form presentation, and the launch transition
(`LaunchBackground` was matched to iOS 17.2's grouped-background values by
hand). Running this script on the TestFlight build **is** the re-verification of
those visual ARTIFACT claims: the settled launch colour and no launch flash,
the orange tint (not system blue) on the sign-in screen, Form/grouped-list
backgrounds, and the tab bar. Note any drift against `SUBMISSION_STATUS.md`.

---

## Before you start

1. Install the TestFlight build. Note the build number — it is the commit count
   now, so it maps to a commit: `git rev-list --count <sha>`.
2. Sign in with the review account, then **sign out and delete the app**. Every
   test below that says "fresh install" means a genuinely fresh one; the
   Keychain survives app deletion, so also do Settings → General → iPhone
   Storage → Thought Pins → Delete App, and verify the next launch shows the
   sign-in screen rather than the tab bar. If it does not, the session outlived
   the app and that is itself a finding.
3. Have a second device or a laptop on hand for the interruption tests.

---

## 1. Launch background colour — the one recorded iOS 26 risk

`LaunchBackground.colorset` hard-codes `#F2F2F7` light and `#000000` dark,
matched to what `systemGroupedBackground` measured on iOS 17.2. Nothing
guarantees iOS 26 kept those values. If they moved, the cold-launch jump this
was fixed to remove comes back, in the opposite direction.

**Do — light mode:**
1. Settings → Display & Brightness → Light.
2. Force-quit Thought Pins. Wait ten seconds.
3. Start a screen recording, then launch the app.
4. Stop the recording once the first screen has settled.
5. Scrub to the launch screen and to the settled screen. Screenshot both.
6. Sample the background of each with the Photos markup eyedropper, or airdrop
   to a Mac and use Digital Colour Meter.

**You should see:** the two samples identical, or indistinguishable. No visible
step, flash or change of shade at the moment the app's own UI appears.

**Failure:** any visible step, or sampled values that differ. Record both hex
values. The fix is either updating the two numbers in
`LaunchBackground.colorset` to what iOS 26 actually uses, or option (1) in
`IOS_26_DEVICE_RISKS.md` — painting the Forms with `ThoughtPinsTheme.canvas` so
nothing depends on Apple's value at all.

**Do — dark mode:** repeat all of the above with Settings → Display &
Brightness → Dark. The dark value is the one most likely to have moved.

---

## 2. Microphone denied — the path the simulator refuses to produce

`simctl privacy revoke microphone` does not take: recording starts anyway. This
branch has therefore never executed. The code sets *"Microphone access was not
granted. You can attach an audio file instead."* and returns without opening
the session.

**Do:**
1. Fresh install. Sign in. Chat tab.
2. Tap the record control.
3. At the system prompt, tap **Don't Allow**.

**You should see:** no recording indicator, no timer, no orange status pill in
the status bar. The message above on screen. The file-attach route still works.
Nothing is uploaded.

**Failure:** a recording indicator appears; a timer starts; an empty or silent
file is uploaded; a generic error instead of that sentence; or the app hangs.

**Then, second tap:**
4. Tap record again.

**You should see:** the same message immediately. iOS does not prompt twice.

**Failure:** a stuck control, a spinner that never resolves, or silence — the
person taps and nothing at all happens. Note that the app offers no route to
Settings here; that is allowed and is flagged in `IOS_26_DEVICE_RISKS.md` as a
product call, not a submission blocker. Record whether it *felt* like a dead
end.

**Then, granting it:**
5. Settings → Thought Pins → Microphone → on.
6. Return to the app, record a few seconds of speech, stop.

**You should see:** a real recording uploads, transcribes, and the transcript is
saved as a journal entry.

---

## 3. Microphone revoked in Settings while the app is open

Not the same test as 2. Here permission was granted, the app is running, and it
is taken away underneath it.

**Do:**
1. With permission granted and the app open on Chat, switch to Settings.
2. Settings → Thought Pins → Microphone → off.
3. Return to Thought Pins — do not force-quit — and tap record.

**You should see:** iOS terminates and relaunches the app on returning (it does
this for a permission change), so expect a cold start. After it, recording
should behave exactly as test 2: the denied message, no indicator.

**Failure:** the app returns without relaunching and then records anyway; or it
crashes rather than relaunching; or the denied message does not appear.

---

## 4. A phone call interrupting a recording

`AVAudioSession.interruptionNotification` is observed and should stop the
recording, keeping what was captured.

**Do:**
1. Start a voice note and speak for about ten seconds.
2. From the second device, call this one.
3. Decline the call.
4. Return to Thought Pins.

**You should see:** the recording stopped when the call arrived. What was
captured before the interruption is kept and transcribed, or the app says
plainly that the recording was interrupted. The compact call banner does not
leave the UI in a broken layout.

**Failure:** a zero-byte upload; a transcript of silence; the recorder still
showing as running with a frozen timer; a crash; or the layout still shifted
after the banner clears.

**Repeat with the call answered and then ended** — that is the longer
interruption and the one more likely to expose a stale session.

---

## 5. Real Split View and Slide Over on iPad

The simulator faked this. `thoughtPinsReadableColumn` only constrains **regular**
width; compact width is meant to be left exactly as a phone. The interesting
moment is the transition, when the size class changes under a live view.

**Do:**
1. Open Thought Pins on the iPad, then open Notes alongside it.
2. Drag the divider to the 50/50 split.
3. Drag it so Thought Pins is the narrow third.
4. Drag it back to full width.
5. Repeat with Thought Pins in Slide Over, then push it away and pull it back.
6. Do all of the above while a **person detail screen** is open, not just a tab.

**You should see:** at each width the content stays inside the window with no
clipped text and no horizontal scrolling. At the narrow width the layout reads
like the phone layout. At full width the content is held to a readable column
and centred, with a single uniform background — no band down the middle with a
hard edge either side.

**Failure:** clipped or truncated text; a horizontal scroll bar; the
readable-column band reappearing with visible edges; the navigation bar losing
its Account control; or a crash on rotation while split.

**Also:** rotate the iPad through all four orientations in each configuration.
iPad supports all four by design; iPhone is portrait only.

---

## 6. Dynamic Type at AX5 via Settings

Not the Xcode inspector — the real setting, which affects the whole system
including the navigation bar and tab bar.

**Do:**
1. Settings → Accessibility → Display & Text Size → Larger Text → Larger
   Accessibility Sizes on → drag to the maximum (AX5).
2. Walk every screen: Recap (day/week/month), People, a **person detail**, Chat
   with a reply on screen, Places, Pins, a **reading detail**, Capture, Account.

**You should see:** text wraps rather than truncating. Nothing overlaps.
Everything reachable by scrolling. Labelled controls still show their labels.
The composer switches to its stacked layout.

**Failure:** any truncated label with no way to see the rest; any two elements
overlapping; any control pushed off screen; any row whose text is clipped by a
fixed-height container.

**Pay particular attention to** the "About this reading" row on a reading detail
— it stacks label above value above AX1 and that stacking has only been seen in
a simulator.

---

## 7. VoiceOver driven by real gestures

The accessibility tree has been inspected programmatically. That is not the same
as listening to it.

**Do:**
1. Settings → Accessibility → VoiceOver → on. (Triple-click the side button to
   toggle it quickly.)
2. Swipe right repeatedly through: the sign-in screen, Recap, People, a person
   detail, Chat with a reply, Account.

**You should see:** every stop announces something meaningful. Reading order
matches what you see, top to bottom. Each memory row is announced as one thing —
its text and its date together — not as a bare date on its own. The back button
announces the screen it returns to ("People", "Pins"). Section headers are
announced before their contents. The Account control at top right is reachable
and named.

**Failure:** any stop that announces nothing, or announces an identifier like
`thoughtpins-problem-banner`; a bare date announced with no context; reading
order that jumps around; the back control unreachable or unnamed; a banner that
steals focus and cannot be dismissed.

**Then, with an error on screen:** sign in with a wrong password and swipe to
the error banner. It should be announced, and its Dismiss button reachable.

---

## 8. Airplane mode toggled mid-session

**Do:**
1. Sign in normally. Let the app load.
2. Turn on airplane mode from Control Centre without leaving the app.
3. Visit every tab.
4. Open a person detail and a reading detail.
5. Write a note and save it.
6. Ask a chat question.
7. Turn airplane mode off.
8. Wait, then check the note.

**You should see:** an offline notice that pushes content down rather than
covering the navigation bar. Read screens that are empty say they could not
load, and do not claim to be showing everything. A detail screen resolves within
about thirty seconds and says either that you are offline or that it took too
long — it must never sit on "Loading" indefinitely, and the reading detail
should still show its cached copy and say that is what it is. The note you wrote
is saved on the device and says so. The chat question fails with a sentence, not
a spinner. After reconnecting, the note sends and the app says how many were
sent — never that something synced when it did not.

**Failure:** a permanent spinner; a screen that claims to be up to date while
offline; a lost note; a success message for something that did not send; the
offline notice covering the Account control.

---

## 9. The new detail screens, on both devices

These were written after every other pass and are two taps from the People tab.

**Do, on iPhone and again on iPad:**
1. People → tap a card. Pins → tap a source.
2. Read every section. Scroll to the bottom.
3. Go back with the navigation control, and again with the edge-swipe gesture.
4. Open a card for someone with almost nothing recorded, if the account has one.

**You should see:** the detail opens; the row looked tappable before you tapped
it; the back control returns you to the tab you came from; a card with nothing
recorded explains that rather than showing a name over a blank screen; no
internal ranking value (`salience`, `salience_tier`) appears anywhere.

**Failure:** a row that opens nothing; a blank screen; a schema word on screen;
the edge-swipe leaving a half-dismissed view; content stretched across the full
iPad width instead of a centred column.

**Note a known content issue while you are here:** on the seeded review account
the "User" card's subtitle currently reads `Type: article. Status: processed.
Access: user_paste. Rights basis: user_provided.` That text is *stored server
side*, not generated by the app. Check whether it still appears on a freshly
seeded account, and record it if so.

---

## 10. Cold launch after force-quit, and after a reboot

**Do:**
1. Force-quit from the app switcher. Wait ten seconds. Launch.
2. Note whether you are still signed in.
3. Restart the device. Launch again before signing into anything else.

**You should see:** still signed in both times — the session lives in the
Keychain and survives both. The launch screen matches the first drawn screen
(test 1). No flash of sign-in before the tab bar appears.

**Failure:** signed out after either; a visible flash of the sign-in screen
before the shell; a launch that takes more than a couple of seconds to show
anything; or a crash on the first launch after reboot (this is the one that
catches cold-start ordering bugs).

---

## What this is not

**Screenshots.** Capture is a separate job with its own rules:

- The **iPhone 17 Pro Max at 1320 × 2868 is the final screenshot device** — that
  is Apple's preferred 6.9" slot, and it replaces the 6.5" fallback set
  currently in `apple-submission/screenshots/iphone-1284x2778/`.
- The **iPhone 17 Pro is not needed for capture.** Apple scales down from 6.9".
- The **iPad A16 is 1640 × 2360, which is not a listed App Store Connect iPad
  size.** The slots are 2064 × 2752, 2048 × 2732 and 1488 × 2266. Do not plan
  iPad screenshots from that device. iPad screenshots stay on the 12.9"
  simulator at 2048 × 2732.

**Signing and upload.** Not this document; see
`apple-submission/AFTER_DEVELOPER_ACCOUNT.md`.
