# App Review notes — Thought Pins

This is a draft for the chosen release. Before pasting the marked block into
App Store Connect, complete [Submission status](SUBMISSION_STATUS.md): validate
the signed build, confirm the fictional review account and backend, and check
that the described features and provider settings match that build. Historical
production observations below are dated evidence, not current attestations.

Put the password in App Store Connect's **Sign-In Information**, never in this
file or the notes body. Recheck the notes length after edits:

```sh
python3 - <<'CHECK'
from pathlib import Path
text = Path('apple-submission/REVIEW_NOTES.md').read_text()
block = text.split('## ✂️ BEGIN — paste into App Store Connect\n', 1)[1].split('## ✂️ END', 1)[0]
print(len(block), 'characters')
assert len(block) <= 4000
CHECK
```

## ✂️ BEGIN — paste into App Store Connect

Thought Pins — Guideline 2.1 information

1. PHYSICAL-DEVICE RECORDING
Before sending these notes, add the verified recording URL, physical device,
latest OS version, app version and build here. The recording must begin with
launch and show registration, login, the main flow, reporting and deletion.
This draft does not claim that a recording is attached.

2. PURPOSE AND AUDIENCE
Thought Pins is a private journal and personal-memory app for people who want
to revisit their experiences, ideas and reading. Save notes, voice transcripts
and sources, then inspect people and places or ask questions about your record.
References let users check the underlying material; AI answers can be wrong.

3. REVIEW ACCESS AND FEATURES
review@thoughtpins.com — current password in the Sign-In Information fields.
Verify these credentials and the fictional demo content before submission.
The backend must remain available throughout review. No sample file or purchase
is required. Registration is open on the submission deployment; no invite code
is required. Native provider buttons appear only when configured for that app.

Try:
- Sign in, or register a separate email/password account. A new account shows
  the explicit AI-processing consent before saving or asking.
- Chat: ask “What do you remember about Maya?” and inspect the cited record.
- Open Recap, People, Places and Pins. Capture can save a note, source or file.
- Tap the microphone, allow recording and speak an invented note. Ordinary
  audio is discarded after transcription; the optional voice archive is disabled.
- Use Report a reply beneath an answer. Notes and replies are private. There is
  no public feed, social profile, following or user-to-user messaging, so
  blocking other users is not applicable.
- Open Account to change appearance and export account JSON or a vault ZIP.
- On a separate disposable account, choose Delete account and confirm. The app
  returns to sign-in after server-confirmed removal. Cleanup failures are shown
  for retry. Do not delete the standing demo account used by other reviewers.

4. EXTERNAL SERVICES AND PRIVACY
Railway hosts the API, workers, PostgreSQL and Redis. Qdrant provides semantic
search. Cloudflare provides domain
and web routing. DeepSeek provides configured AI organization and responses;
OpenAI provides embeddings and hosted voice transcription. Resend delivers
account email and sign-in links. Image OCR uses Tesseract and PDF extraction
uses pypdf on the server. Reconcile enabled identity providers with the
selected build before sending this list.

Users consent before AI processing. Journal content is not used for advertising
or model training. No advertising/analytics SDK, IDFA or tracking prompt is
included. Current provider details: https://thoughtpins.com/ai-disclosure

5. REGIONS AND DEVICES
The product has no intentional region-specific features or content. Its screens
and image OCR are English; online features need provider access. Confirm the
App Store territories and service availability for this submission.
The app supports iPhone and iPad. Sign-in needs a connection; supported offline
journal drafts are kept on-device and sent after reconnecting, with failures
reported. Test the chosen signed build on physical devices before submission.

6. REGULATED SERVICES AND MATERIAL
Thought Pins is a note-taking tool, not a regulated financial or medical
service. Review content is invented. Users deliberately supply documents;
article capture respects access restrictions and does not bypass paywalls.
No protected third-party publication is bundled as the review dataset.

The release is free: no purchases, subscriptions, ads or external purchase links.
Support: support@thoughtpins.com — https://thoughtpins.com/support
Privacy: https://thoughtpins.com/privacy
Terms: https://thoughtpins.com/terms

## ✂️ END — paste into App Store Connect

---

## Notes for you, not for Apple

### Verified against production on 2026-08-25

Everything below was checked by talking to `api.thoughtpins.com` and by signing
in on a clean simulator, not by reading configuration.

**The demo account was reseeded on 2026-09-03.** `review@thoughtpins.com`
exists with `email_verification_required: false`, so there is no mail step in
the way, and it was reseeded with a fresh password so the credentials in App
Store Connect are known to work rather than assumed to.

Reseeding is not free of surprises. `scripts/seed_review_account.py
--allow-production` set the password and then failed part-way: its demo-content
insert was rejected with `new row violates row-level security policy for table
"raw_entries"`. That is RLS doing its job — see TD-009 — and it left the account
signed-in-able but empty, which is worse than either outcome alone because the
notes above promise a pre-loaded account. The content was written afterwards
through the public API, which scopes tenants correctly. **If you reseed again,
check the account has content before you trust it.**

**The password is not in this repository and must not be.** Put it in App Store
Connect → App Review Information → **Sign-In Information**. If you have lost it,
change it rather than guessing.

**The account has content, verified on 2026-09-03 by reading it back.** Five
journal entries, all `processed`, and memory cards for Maya and User. Asking
"What do you remember about Maya?" returns a grounded answer naming Atlas Cafe,
the copper lantern, and the half marathon — which is the sample question the
pasteable notes invite the reviewer to try, so it was checked rather than
assumed. All of it is fictional; no real person appears.

Exact counts are deliberately not stated here. They drift every time the
account is used for testing — checked against production on 2026-08-26 it held
10 entries and 17 memories, not the four this line used to claim. Reseed with
`scripts/seed_review_account.py` before submitting and read the counts off its
`--json` output if you need them. Chat answers
from it — "What do you remember about Maya?" returns a grounded answer citing
Atlas Cafe and the copper lantern. The screenshots in `screenshots/` are that
account, on production.

**The invite gate is off, confirmed at the endpoint the app actually calls.**
`/v1/client-config` reports `invite_required: false`, and for the demo account
`/v1/invites/status` reports:

```json
{"invite_required": false, "invite_redeemed": false, "admitted": true,
 "contact_email": "invite@thoughtpins.com", "attempts_remaining": 10}
```

`admitted` is what matters: `ThoughtPinsAppModel.isBlockedByInviteGate` is
`inviteRequired && !admitted`, and `invites.admitted()` returns `True`
unconditionally while `INVITE_ONLY` is false. So `ThoughtPinsInviteView` cannot
appear. This was confirmed at runtime, not just read: the screenshot run signs
in on a wiped simulator and asserts the "You're on the list" screen never
appears. That assertion lives in the Mac screenshot harness, not in CI, so it
is only as current as the last time someone ran it.

**The order a reviewer walks.** Cold install → sign-in screen → AI-processing
consent → the app. No invite wall anywhere in it. Consent is server state, so
once accepted it never returns: the demo account has accepted it, and a reviewer
signing in goes straight to the tab shell. A reviewer who registers their own
account sees the consent screen. Both paths were exercised.

**No third-party sign-in button appears.** Production reports
`oauth_google_enabled: true` and `oauth_apple_enabled: false`. Guideline 4.8
requires a privacy-preserving equivalent alongside any third-party login, and
email-and-password does not qualify because it cannot mask the address. The app
now suppresses Google unless Apple sign-in is also available, so the sign-in
screen offers email and password only. To offer Google, configure Apple sign-in
and set `oauth_apple_enabled` — they then appear together.

### Turning the invite gate back on

Neither `create_invite_code` nor `redeem` consults the flag, so codes stay
mintable and redeemable; they are simply not required. One variable and a
redeploy:

```bash
railway variables --service api --set "INVITE_ONLY=true"
railway redeploy --service api --yes
```

If you do that before submitting, the demo account needs a redeemed invite
(`seed_review_account` mints and redeems one when the gate is on) **and** the
notes need a paragraph explaining the wall. A reviewer who registers, hits a
wall, and finds no explanation files a 2.1 rejection.

### Before you submit

- [ ] Put the demo password in **Sign-In Information**, not the notes body.
- [ ] Confirm **invite@thoughtpins.com** and **support@thoughtpins.com** both
      receive mail during the review window. Apple emails; a bounce is a
      rejection.
- [ ] Confirm the backend is not in maintenance mode for the whole window.
- [ ] Re-run `StoreScreenshotTests` if the UI changes, so the screenshots match
      the build being reviewed.
- [x] **`WEB_APP_URL` is correct on Railway.** It briefly held
      `C:/Program Files/Git/app` — Git Bash rewrote a leading-slash value
      before it reached the service. It is now `https://thoughtpins.com/app`,
      confirmed on 2026-08-26 at the endpoint the apps actually read:
      `/v1/client-config` returns
      `"store_urls": {"web": "https://thoughtpins.com/app"}`. Two guards stay
      regardless — the API sends `null` rather than a Windows path
      (`config_urls.public_client_url`), and `scripts/validate_production.py`
      blocks a deploy on a mangled value. Set such variables with
      `MSYS_NO_PATHCONV=1`, or give a full `https://` URL.

### Things deliberately not claimed

The notes do not name the AI provider. `site/ai-disclosure.html` and
`site/privacy.html` are the binding disclosures and must stay accurate about
what actually processes user content. If you change providers, change those
pages in the same deploy — App Review compares the app's claims to the linked
policy, and a mismatch is worse than either statement alone.

The notes do not promise that private-memory recall works. Production runs with
`PRIVATE_ALLOW_LLM` off, which is deliberate: entries marked private are never
sent to a third-party model.

The switch itself makes no network call, so flipping it shows nothing. The
refusal arrives on the **first message sent** while it is on — this section
used to say the toggle itself returned 403, which is not what happens. The app
then turns the switch back off and explains why in plain words rather than
passing through the server's "disabled by server policy" phrasing. Enable the
flag only if you want a reviewer to be able to use it, and understand that
doing so weakens the privacy claim above.
