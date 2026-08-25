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
| Apple Developer Program membership, **Individual** | Nothing below works without it | decided: individual, not organisation |
| A Mac | Compiles SwiftUI; the archive needs Xcode 26+ | **have one, on macOS 13 Ventura** — see below |
| `invite@thoughtpins.com` receiving mail | Reviewers email it if the gate stops them | verify |
| `support@thoughtpins.com` receiving mail | Apple requires a working support contact | verify |

**The Ventura MacBook compiles but cannot upload.** App Store uploads have
required Xcode 26 or later since 28 April 2026; Xcode 26 needs macOS Sequoia
15.6+, and macOS 13 tops out at Xcode 15.2. That is still Swift 5.9 with the
iOS 17.2 SDK, which is exactly what this target asks for, so the machine does
every job up to the archive: first compile, error fixing, simulator passes,
Dynamic Type, VoiceOver, iPad.

For the archive itself, the `ios` job in `.github/workflows/ci.yml` already runs
on `macos-latest` with a current Xcode and is the natural place to grow it —
`gh workflow run ci.yml --ref main -f run_native=true`. Xcode Cloud (25 compute
hours a month with the developer programme), an hourly cloud Mac, or a used
Apple silicon machine are the alternatives. Full detail in
[`MAC_START_HERE.md`](MAC_START_HERE.md).

---

## Stage 1 — Enrollment and identifiers (no Mac needed)

0. **Enrol as an Individual.** developer.apple.com/programs → Enroll.
   - Sign in with an Apple ID that has **two-factor authentication on**.
     Enrolment refuses without it, and turning it on later is a detour.
   - Entity type: **Individual / Sole Proprietor**. No D-U-N-S number, no
     business documents. Apple verifies you with a government photo ID through
     their app or website.
   - $99/year. Approval is usually 24-48 hours, occasionally longer if the ID
     check needs a second pass.
   - **Your legal name becomes the seller name shown on the App Store listing.**
     That is the trade for skipping the D-U-N-S wait. It cannot be changed to a
     company name later without transferring the app to a new organisation
     account.
   *Done when:* the email says your membership is active.

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

     Tick it **even though v1 does not show an Apple button.** The entitlement
     is in the binary, and an entitlement absent from the provisioning profile
     fails signing with "Provisioning profile doesn't include the
     com.apple.developer.applesignin entitlement". See *What v1 ships for
     sign-in* below.
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

## What v1 ships for sign-in

**Email and password only.** No Apple button, no Google button, no third-party
section on the sign-in screen at all.

That is a decision, not an omission. Production reports
`oauth_google_enabled: true` and `oauth_apple_enabled: false`, and the app now
refuses to offer Google unless Apple is available alongside it.

Guideline 4.8 requires that an app using a third-party login service also offer
an option that limits collection to name and email **and lets the person keep
their email address private**. Email-and-password fails the second half: it
needs a real, working address. So Google on its own is a rejection.

Shipping first-party sign-in only lands in 4.8's own exemption — *"Your app
exclusively uses your company's own account setup and sign-in systems"* — so
there is nothing to satisfy and nothing to explain.

### If you want the Google button back

There is one practical route: **turn on Sign in with Apple.** It is the option
that meets the private-address requirement, and the app already implements it
in full — the button, the nonce, the state check, the authorization code. What
is missing is configuration, not code:

1. The App ID capability (Stage 1 above) — needed for signing regardless.
2. A Services ID, a key, and the team id, so the backend can verify the
   identity token. `APPLE_OAUTH_TEAM_ID`, `APPLE_OAUTH_KEY_ID` and
   `APPLE_OAUTH_PRIVATE_KEY` already exist in config for this.
3. `oauth_apple_enabled` true in client-config.

Do those and the Apple button appears, with no app change.

### Restoring the Google plist wiring

Google needs three things put back that v1 removed, because with no client ID
they resolved to empty strings and an empty `CFBundleURLSchemes` entry is
malformed:

- `mobile/ios/ThoughtPinsNative/project.yml`, under the target's `settings.base`:

  ```yaml
  GOOGLE_IOS_CLIENT_ID: ""
  GOOGLE_IOS_SERVER_CLIENT_ID: ""
  GOOGLE_IOS_REVERSED_CLIENT_ID: ""
  ```

- `mobile/ios/ThoughtPinsNative/Resources/Info.plist`:

  ```xml
  <key>GIDClientID</key>
  <string>$(GOOGLE_IOS_CLIENT_ID)</string>
  <key>GIDServerClientID</key>
  <string>$(GOOGLE_IOS_SERVER_CLIENT_ID)</string>
  <key>CFBundleURLTypes</key>
  <array>
      <dict>
          <key>CFBundleTypeRole</key>
          <string>Editor</string>
          <key>CFBundleURLSchemes</key>
          <array>
              <string>$(GOOGLE_IOS_REVERSED_CLIENT_ID)</string>
          </array>
      </dict>
  </array>
  ```

`scripts/ios_release.sh` refuses to build if you supply the `GOOGLE_IOS_*`
values while the plist has nowhere to put them, so this cannot be half done
silently. `scripts/check_ios_submission_source.py` then requires the keys to
resolve to something real rather than an empty string, in the source and — via
the `ios` CI job — in the built app.

Routes that do **not** work, so they are not worth trying:

- **Magic link.** Enabled server-side, unimplemented on iOS, and it still needs
  a real address — it does not satisfy the private-address requirement.
- **Email and password as the "equivalent option".** This is the one people
  assume works. It does not: there is no way to keep the address private.
- **Another social provider.** The requirement is about the *properties* of the
  alternative, and in practice Sign in with Apple is the only login service that
  has them.

Removing the entitlement to simplify provisioning is also not worth it: the gate
in `scripts/check_ios_submission_source.py` requires it, and keeping it costs
one tick on the App ID while leaving the door open.

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
      -destination 'platform=iOS Simulator,name=iPhone 15 Pro' \
      CODE_SIGNING_ALLOWED=NO build
    ```
    *Expect compile errors on the first attempt.* Roughly 400 lines of SwiftUI
    in this repo have never been through a compiler. See
    "Known-unverified Swift" in [`README.md`](README.md).

11. **Simulator pass across the device matrix.** Run on, at minimum:
    iPhone SE (3rd gen), the current Pro and Pro Max your Xcode offers
    (iPhone 15 Pro / Pro Max on Xcode 15.2), an iPad mini, and an iPad Pro.
    Run `xcrun simctl list devicetypes` first — naming a simulator this
    Xcode does not have fails in a way that reads like a build error. For each: launch, sign in, chat, record a voice note, export,
    and rotate to landscape.

    **Give iPad the same attention as iPhone, not less.** A former reviewer's
    account is that they test on iPad "almost all of the time" — even for apps
    that uncheck the iPad box, because unchecking only means you are not
    claiming native support, not that they will never launch it there. This
    target claims universal (`TARGETED_DEVICE_FAMILY: "1,2"`), so iPad is
    definitely tested. An iPhone layout stretched across 13 inches with a
    1,000pt-wide text column is the kind of thing that reads as "feels broken".
    Check the chat column measure, the memory-card grid, and Slide Over at
    320pt specifically.

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

13. **Screenshots.** Apple requires only the largest size in each family and
    scales the rest down automatically, so this is two sets, not six.

    | Family | Accepted sizes | How we get it | Cost |
    |---|---|---|---|
    | iPhone 6.9" | 1320 × 2868, 1290 × 2796, or 1260 × 2736 | **iPhone 17 Pro Max, on-device** — its native screenshot is 1320 × 2868 | £0 |
    | iPad 13" | 2064 × 2752 **or 2048 × 2732** | **iPad Pro 12.9" (6th gen) simulator** — 2048 × 2732, and it ships with Xcode 15.2 | £0 |

    The second row is the one worth noticing. The 13-inch class accepts
    2048 × 2732 as well as 2064 × 2752, and 2048 × 2732 is exactly what the
    12.9-inch simulator produces — which the Ventura MacBook already has. No
    newer Xcode, no rented Mac, no iPad hardware.

    Take the iPhone set from a TestFlight build on the real phone (side button
    plus volume up), then AirDrop to the Mac. Take the iPad set from the
    simulator with `Cmd-S`, or:

    ```bash
    xcrun simctl io booted screenshot ipad-chat.png
    ```

    At least 3 of each. Suggested: Chat with a reply, a People memory card,
    Recap. No device frames, no marketing text over the UI.

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
