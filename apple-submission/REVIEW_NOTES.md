# App Review Notes — Thought Pins

**Paste the section between the markers into App Store Connect → App Review
Information → Notes.** Everything outside the markers is for you, not Apple.

Keep it under ~4,000 characters. The version below is about 2,600.

---

## ✂️ BEGIN — paste into App Store Connect

Thought Pins is a private journaling and personal-memory app. You write or
speak notes; it organises them into people, places, events and sources you can
ask about later.

**DEMO ACCOUNT**
Email: review@thoughtpins.com
Password: (entered in the Sign-In Information fields above)

Pre-loaded with fictional demo data — no real personal information — so every
screen has something to show immediately. Please do not delete this account.

**NO INVITE CODE IS NEEDED**

Sign-up is open; no invite code is required, and you can register your own
account. The app contains a private-testing screen for a closed beta, but that
gate is off and you will not see it. If you ever do, email me and I will clear
it the same day.

Sign-in is email and password only. Google and Apple sign-in are built but not
enabled: we will not offer a third-party login without Sign in with Apple
alongside it, and Apple sign-in is not configured yet.

**WHAT TO TRY**

1. Sign in with the demo account.
2. **Chat** — ask "what do you remember about Maya?" It answers from stored
   memories, with the source visible.
3. **Recap** — saved entries by day. **People / Places** — memory cards built
   from those entries. **Pins** — saved readings; "+" adds a link or file.
4. **Voice note** — the microphone in Chat. It asks permission first and
   explains that audio is transcribed then discarded.
5. **Account → Export account** — full data export, including an
   Obsidian-compatible Markdown vault.
6. **Account → Delete account** — real, immediate, irreversible deletion, two
   taps away. Because it genuinely deletes, please test it on a throwaway
   account you register: deleting the demo account stops the credentials above
   working for the rest of the review.

**NOTHING IS SHARED — THERE IS NO SOCIAL SURFACE**

Everything a person writes is visible only to their own account. No feed, no
profiles, no following, no comments, no sharing, no public links, no
user-to-user communication of any kind. There is no audience to expose anyone
to, so the usual user-generated-content risks have no path here.

The app still offers in-app reporting of unsafe AI output (Account → Support).
Retrieved journal text, imported articles and OCR output enter the model prompt
as evidence, never as instructions, so saved content cannot redirect the
assistant.

**AI AND PRIVACY**

Content you save or ask about is sent to a third-party AI provider over HTTPS
for classification, extraction and replies. This is disclosed before any content
is sent: an account must accept an AI-processing consent screen before it can
save or ask anything, and the same disclosure is at
https://thoughtpins.com/ai-disclosure.

The demo account has already accepted it, so signing in with the credentials
above goes straight to the app. To see the consent screen itself, register a new
account — it appears immediately after sign-up and blocks the app until
accepted.

No advertising or analytics SDKs, no tracking, no IDFA and no App Tracking
Transparency prompt. Journal content is never sold or used for advertising.

**ARTICLE SAVING AND PUBLISHER RIGHTS**

Saving a link stores the article's public text. If a page is paywalled or
access-gated, the app detects it and stores only public metadata — title,
publisher, date, canonical URL — discarding fetched text and telling the user
the page was gated. There is no paywall circumvention of any kind.

**PURCHASES, PERMISSIONS, IPAD**

No purchases, subscriptions, external purchase links or advertising. The app is
free throughout.

Microphone only, and only when record is tapped for a voice note. No location,
contacts, photos, camera or notifications prompt.

Universal build — everything above works on iPad exactly as on iPhone, same
account, same data.

**SUPPORT**

support@thoughtpins.com — https://thoughtpins.com/support
Privacy: https://thoughtpins.com/privacy — Terms: https://thoughtpins.com/terms

If anything blocks you, email me and I will respond the same day.

## ✂️ END — paste into App Store Connect

---

## Notes for you, not for Apple

### Verified against production on 2026-08-25

Everything below was checked by talking to `api.thoughtpins.com` and by signing
in on a clean simulator, not by reading configuration.

**The demo account did not exist.** `review@thoughtpins.com` was not registered
on production. `POST /v1/auth/register` returned 200 and created it, which means
it was absent — a reviewer given those credentials would have been unable to
sign in, and that is a Guideline 2.1 rejection on the first screen. It now
exists, with `email_verification_required: false`, so there is no mail step in
the way.

**The password is not in this repository and must not be.** Put it in App Store
Connect → App Review Information → **Sign-In Information**. If you have lost it,
change it rather than guessing.

**The account has content.** It was populated through the public API, so the
data is real rather than injected: two journal entries, one saved reading, four
entries in total, two people cards (Maya, User), one place card. Chat answers
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
- [ ] **Fix `WEB_APP_URL` on Railway.** It holds
      `C:/Program Files/Git/app` — Git Bash rewrote a leading-slash value before
      it reached the service. The API no longer serves it (a Windows path is
      now sent as `null`, so no client shows it), and
      `scripts/validate_production.py` blocks a deploy while it is wrong, but
      the variable itself is still wrong:

      ```bash
      MSYS_NO_PATHCONV=1 railway variables --service api --set "WEB_APP_URL=/app"
      # or set it to the full URL and avoid the problem entirely:
      railway variables --service api --set "WEB_APP_URL=https://thoughtpins.com/app"
      ```

### Things deliberately not claimed

The notes do not name the AI provider. `site/ai-disclosure.html` and
`site/privacy.html` are the binding disclosures and must stay accurate about
what actually processes user content. If you change providers, change those
pages in the same deploy — App Review compares the app's claims to the linked
policy, and a mismatch is worse than either statement alone.

The notes do not promise that private-memory recall works. Production runs with
`PRIVATE_ALLOW_LLM` off, so turning on "Use private memories" in Chat returns
403. The app now turns the switch back off and shows the server's explanation
rather than "Chat failed", but if you want a reviewer to be able to use it,
enable the flag.
