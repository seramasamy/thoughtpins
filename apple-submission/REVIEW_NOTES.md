# App Review Notes — Thought Pins

**Paste the section between the markers into App Store Connect → App Review
Information → Notes.** Everything outside the markers is for you, not Apple.

Keep it under ~4,000 characters. The version below is about 2,600.

---

## ✂️ BEGIN — paste into App Store Connect

Thought Pins is a private journaling and personal-memory app. You write or
speak notes; it organises them into people, places and sources you can ask
about later.

**DEMO ACCOUNT**
review@thoughtpins.com — password in the Sign-In Information fields above.
Pre-loaded with fictional demo data, no real personal information. Please do
not delete it; see DELETION.

**WHY AN ACCOUNT IS REQUIRED (5.1.1(i))**

The account is the product, not a gate on it. Everything here is recall over
what you saved: entries are stored, indexed, and answered against later from
any device you sign in on. Without an account there is nothing to remember. We
ask for an email or phone and a password — no profile, contacts or social
graph.

**NO INVITE CODE IS NEEDED**

Sign-up is open; registering your own account is not gated, and we tested that
on a clean install. The app has a private-testing screen from a closed beta,
switched off — if you see it, email me and I will clear it same day.

Sign-in is email and password only. Google and Apple sign-in are built but not
enabled: we will not offer a third-party login without Sign in with Apple
alongside it (4.8), and Apple sign-in is not configured yet.

**WHAT TO TRY**

1. Sign in, or register your own account.
2. **Chat** — ask "what do you remember about Maya?" It answers from stored
   entries, saying "your journal shows" rather than asserting facts.
3. **Recap** (entries by day), **People / Places** (cards built from them),
   **Pins** (saved readings; "+" adds a link or file).
4. **Voice note** — the mic in Chat. It asks permission and says audio is
   transcribed then discarded.
5. **Report a reply** — under any chat answer; reaches support@thoughtpins.com.
6. **Account → Export account** — full export, including a Markdown vault.

**DELETION (5.1.1(v))**

Account → Data → **Delete account**, two taps from any screen via the person
icon at top right. Immediate and irreversible: the account and all entries go
and the app returns to sign-in. Please test it on a throwaway account you
register — deleting the demo account stops the credentials above working.

**AI AND PRIVACY**

Content you save or ask about is sent to a third-party AI provider over HTTPS
for classification, extraction and replies. An account must accept an
AI-processing consent screen before it can save or ask anything; the same
disclosure is at https://thoughtpins.com/ai-disclosure. The demo account has
accepted already — register a new account to see that screen.

The assistant answers only from your own saved material, is instructed never to
claim external truth, and treats retrieved text as evidence rather than
instructions. Nothing is used for advertising or model training by us. No
advertising or analytics SDKs, no tracking, no IDFA, no ATT prompt.

**NOTHING IS SHARED — NO SOCIAL SURFACE**

Everything is visible only to its own account. No feed, profiles, following,
comments, sharing, public links or user-to-user communication. There is no
audience to expose anyone to, which is why the user-generated-content
questions are answered No.

**ARTICLE SAVING**

Saving a link stores the article's public text. If a page is paywalled the app
keeps only public metadata, discards the fetched text and says so. No paywall
circumvention.

**PURCHASES, PERMISSIONS, IPAD**

No purchases, subscriptions, external purchase links or advertising, and no
link in the app leads to a page selling anything.

Microphone only, and only when record is tapped. No location, contacts,
photos, camera or notifications prompt.

Universal build; iPhone is portrait only by design, iPad supports all four
orientations.

**OFFLINE**

Signing in needs a connection. After that the app opens without one, says so,
and saves what you write on the device to send when you reconnect.

**SUPPORT**

support@thoughtpins.com — https://thoughtpins.com/support
Privacy and Terms are linked from that page.

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
