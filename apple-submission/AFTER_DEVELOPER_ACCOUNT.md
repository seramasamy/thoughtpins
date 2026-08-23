# After the Apple Developer account exists

Ordered. Each step says what "done" looks like, so you can stop and resume.

The Xcode mechanics are already written up in
[`docs/release/MAC_XCODE_V1_EXECUTION_CHECKLIST.md`](../docs/release/MAC_XCODE_V1_EXECUTION_CHECKLIST.md)
(10 sections) and
[`docs/release/MACOS_XCODE_APP_STORE_RUNBOOK.md`](../docs/release/MACOS_XCODE_APP_STORE_RUNBOOK.md)
(554 lines). This file is the ordering around them, including everything that
is not Xcode.

---

## Stage 0 — What you need before anything else

| Thing | Why | Status |
|---|---|---|
| Apple Developer Program membership, **Account Holder** role | Nothing below works without it | you said this is in progress |
| A Mac running current macOS with Xcode 26+ | The only host that can compile SwiftUI or sign an archive | **you do not have this yet** |
| `invite@thoughtpins.com` receiving mail | Reviewers email it if the gate stops them | verify |
| `support@thoughtpins.com` receiving mail | Apple requires a working support contact | verify |

**The Mac is the real blocker, not the account.** If you do not own one:
a Mac mini (M4, base) is the cheapest route and is reusable for every future
release. Cloud Mac rental (MacStadium, Scaleway Apple silicon) works for a
one-off submission but you will need it again for every update and every
rejection round-trip.

---

## Stage 1 — Enrollment and identifiers (no Mac needed)

1. **Confirm the membership is active.** developer.apple.com → Account. It
   should say "Apple Developer Program" with an expiry roughly a year out.
   *Done when:* Certificates, Identifiers & Profiles is reachable.

2. **Register the App ID.** Identifiers → **+** → App IDs → App.
   - Description: `Thought Pins`
   - Bundle ID: **Explicit** → `com.thoughtpins.app`
     (this must match `PRODUCT_BUNDLE_IDENTIFIER` in
     `mobile/ios/ThoughtPinsNative/project.yml`, and the gate asserts it)
   - Capabilities: tick **Sign in with Apple** only. Nothing else — the
     entitlements file requests only `com.apple.developer.applesignin`, and an
     App ID with capabilities the app does not use fails provisioning.
   *Done when:* the identifier appears in the list.

3. **Create the App Store Connect record.** appstoreconnect.apple.com → Apps →
   **+** → New App.
   - Platform: iOS
   - Name: `Thought Pins` (must be globally unique — if taken, pick now, it is
     hard to change later)
   - Primary language: English (U.S.)
   - Bundle ID: the one from step 2
   - SKU: `thoughtpins-ios-001`
   - User Access: Full Access
   *Done when:* the app record exists and shows "Prepare for Submission".

4. **Note your Team ID.** developer.apple.com → Account → Membership. Ten
   characters. You need it for `APPLE_TEAM_ID` later.

---

## Stage 2 — Production backend readiness (no Mac needed)

Do this *before* the archive, so the app the reviewer opens has data.

5. **Seed the review account against production.**
   ```bash
   # from the repo, with production DATABASE_PUBLIC_URL exported
   export THOUGHTPINS_REVIEW_EMAIL=review@thoughtpins.com
   # Generate 20+ characters, store it in your password manager, and export it
   # into THOUGHTPINS_REVIEW_PASSWORD. Never write it into a file in this repo.
   read -rs THOUGHTPINS_REVIEW_PASSWORD && export THOUGHTPINS_REVIEW_PASSWORD
   python scripts/seed_review_account.py --allow-production --json
   ```
   `--allow-production` is required on purpose; the seeder refuses production
   otherwise.

   *Done when:* the output shows
   `"invite_admitted": true` and non-zero `entries`, `entities`, `memories`.
   If `invite_admitted` is `false`, the invite gate is off in that environment —
   check `INVITE_ONLY`.

6. **Prove the demo account works end to end from outside.**
   Sign in at https://thoughtpins.com/app with the review credentials. You
   must land in the product, **not** on an invite screen. Open People, send one
   chat message, open Account.
   *Done when:* you saw a chat reply and a memory card, signed out, signed back
   in.

7. **Confirm maintenance mode is off** and will stay off for the review window
   (typically 24–72 hours, longer if rejected). A maintenance banner during
   review reads as a broken app.

8. **Check the legal pages load over HTTPS with no redirect chain:**
   https://thoughtpins.com/privacy, `/terms`, `/support`, `/ai-disclosure`,
   `/account/delete`. Apple fetches these.

---

## Stage 3 — On the Mac

9. **Clone and bootstrap**, then run the full gate to confirm the tree is sound
   on a second platform:
   ```bash
   python scripts/release_check.py --strict-quality
   ```
   Expect 49/49. ~12 minutes.

10. **Run the two things Windows never could.** This is the first execution of
    any Swift in this project — treat failures here as expected, not alarming.
    ```bash
    swift test --package-path mobile/ios/ThoughtPinsCore
    ```
    That runs `APIClientTests` and the new `DraftStoreTests` (3 tests proving a
    deleted account's offline drafts cannot reach the next person on the
    device).

    Then generate and build:
    ```bash
    brew install xcodegen
    cd mobile/ios/ThoughtPinsNative && xcodegen generate
    xcodebuild -project ThoughtPins.xcodeproj -scheme ThoughtPins \
      -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
      CODE_SIGNING_ALLOWED=NO build
    ```
    *Expect compile errors on the first attempt.* Roughly 400 lines of SwiftUI
    in this repo have never been through a compiler. See
    "Known-unverified Swift" in [`README.md`](README.md).

11. **Simulator pass across the device matrix.** Run on, at minimum:
    iPhone SE (3rd gen), iPhone 17 Pro, iPhone 17 Pro Max, iPad mini (A17 Pro),
    iPad Pro 13". For each: launch, sign in, chat, record a voice note, export,
    and rotate to landscape.

    Then the things only a simulator shows:
    - **Dynamic Type at AX5** (Settings → Accessibility → Display & Text Size)
    - **VoiceOver order** on Chat and Account
    - **Dark mode cold launch** — confirm no white flash (fixed, unverified)
    - **iPad Slide Over at 320pt** — drag the app into a Slide Over window

12. **Follow the existing checklist** from section 5 onward:
    `docs/release/MAC_XCODE_V1_EXECUTION_CHECKLIST.md`. It covers signing,
    private release values, archive, and validation.

---

## Stage 4 — App Store Connect metadata

13. **Screenshots.** Required, and you cannot make them until step 11.
    - iPhone 6.9" — 1290 × 2796 — **at least 3**
    - iPad 13" — 2064 × 2752 — **at least 3** (required because
      `TARGETED_DEVICE_FAMILY` is `1,2`; dropping iPad support is the only way
      to avoid this, and it is not worth it)
    Suggested: Chat with a reply, a People memory card, Recap.
    No device frames, no added marketing text over the UI.

14. **App Privacy.** Answers are pre-derived in
    [`docs/release/APPLE_REVIEW_ANSWERS.md`](../docs/release/APPLE_REVIEW_ANSWERS.md)
    and must match `PrivacyInfo.xcprivacy` exactly — Apple compares them.
    Declared: Email, Phone, User ID, Other User Content, Audio, Device ID — all
    "Linked to you", all "App Functionality", **none** used for tracking.

15. **Age rating.** The app shows user-generated and AI-generated text.
    Answer honestly; expect **12+**. Do not claim 4+.

16. **Export compliance.** `ITSAppUsesNonExemptEncryption` is already `false` in
    the Info.plist (HTTPS only, which is exempt), so App Store Connect should
    not ask again.

17. **Review notes.** Paste from
    [`REVIEW_NOTES.md`](REVIEW_NOTES.md). Put the demo password in the
    **Sign-In Information** fields, not the notes body.

---

## Stage 5 — Submit

18. **TestFlight first.** Upload the build, install it on a real iPhone from
    TestFlight, and repeat the step-11 flow on hardware. The simulator does not
    exercise the Keychain, real microphone hardware, or a real cold launch.

19. **Submit for review.** Expect 24–48 hours.

20. **If rejected** — most first submissions are. Read the exact guideline
    number, fix only that, reply in Resolution Center. Do not resubmit silently
    with unrelated changes.

    Most likely for this app, in order:
    - **2.1** — reviewer could not get past the invite gate. Mitigated by the
      demo account and the notes; if it still happens, reply with fresh
      credentials the same day.
    - **5.1.1(v)** — account deletion. It is implemented and reachable at
      Account → Delete account; point them there.
    - **4.0 / 2.3.x** — screenshots not matching the app.

---

## Do this the week before

- [ ] Test-send to `support@` and `invite@` from an outside address; confirm
      arrival and that you will notice them.
- [ ] Generate and store the review password in a password manager.
- [ ] Decide the App Store name now and check availability.
- [ ] Read [`docs/release/APP_REVIEW_RISK_REGISTER.md`](../docs/release/APP_REVIEW_RISK_REGISTER.md).
