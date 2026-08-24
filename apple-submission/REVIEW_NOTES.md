# App Review Notes — Thought Pins

**Paste the section between the markers into App Store Connect → App Review
Information → Notes.** Everything outside the markers is for you, not Apple.

Keep it under ~4,000 characters. The version below is about 2,600.

---

## ✂️ BEGIN — paste into App Store Connect

Thought Pins is a private journaling and personal-memory app. You write or speak
notes, and the app organises them into people, places, events and sources you
can ask questions about later.

**DEMO ACCOUNT**
Email: review@thoughtpins.com
Password: (entered in the Sign-In Information fields above)

The account is pre-loaded with fictional demo data — no real personal
information — so every screen has something to show immediately.

**OPEN SIGN-UP**

You can register your own account if you prefer — sign-up is open and requires
no code. The demo account above is pre-loaded with data, so it is the faster way
to see the product working.

**WHAT TO TRY**

1. Sign in with the demo account.
2. **Chat** — ask "what do you remember about Maya?" It answers from stored
   memories, with the source visible.
3. **Recap** — daily/weekly/monthly view of saved entries.
4. **People / Places** — memory cards built from journal entries.
5. **Pins** — saved articles and documents. Tap "+" to add a link or file.
6. **Voice note** — the microphone in Chat. It asks permission first and
   explains that audio is transcribed then discarded.
7. **Account → Export account** — full data export, including an
   Obsidian-compatible Markdown vault.
8. **Account → Delete account** — real, immediate, irreversible deletion.

**NOTHING IS SHARED — THERE IS NO SOCIAL SURFACE**

Everything a person writes here is visible only to their own account. There is
no feed, no profiles, no following, no comments, no sharing, no public links,
and no way for one account to see another's content. The app has no
user-to-user communication of any kind.

This matters for the usual user-generated-content concerns: there is no audience
to expose anyone to, so the risks that moderation tooling exists to address —
harassment, distribution of harmful material, contact between adults and minors
— have no path here. It is a private notebook.

For completeness, the app still has: in-app reporting of unsafe or unexpected AI
output (Account → Support), and a safety endpoint behind it. Retrieved journal
text, imported articles and OCR output enter the model prompt as *evidence*,
never as instructions, so saved content cannot redirect the assistant.

**AI AND PRIVACY**

Content you save or ask about is sent to a third-party AI provider over HTTPS
for classification, extraction and replies. This is disclosed before any content
is sent: a consent screen appears on first launch and must be accepted, and the
same disclosure is at https://thoughtpins.com/ai-disclosure.

No advertising SDKs. No analytics SDKs. No tracking. No IDFA and no App Tracking
Transparency prompt, because nothing is tracked. Journal content is never sold
or used for advertising.

**ARTICLE SAVING AND PUBLISHER RIGHTS**

Saving a link stores the article's public text. If the page is paywalled or
access-gated, the app **detects this and deliberately stores nothing but the
public metadata** — title, publisher, date, canonical URL — and tells the user
the page was gated. Fetched text from gated pages is discarded rather than
saved. The app contains no paywall circumvention of any kind, and publishers
that limit automated access are refused outright.

**PURCHASES**

None. The app is free with no in-app purchases, no subscriptions, no external
purchase links and no advertising. There is no account tier to upgrade.

**PERMISSIONS**

Microphone only, and only when the user taps record for a voice note. No
location, contacts, photos, camera, or notifications.

**IPAD**

Universal build. The same five screens, laid out for the larger canvas.
Everything above can be tested on iPad exactly as on iPhone — same account, same
data, no iPhone-only paths.

**SUPPORT**

support@thoughtpins.com — https://thoughtpins.com/support
Privacy: https://thoughtpins.com/privacy
Terms: https://thoughtpins.com/terms

Thank you for reviewing. If anything blocks you, email me and I will respond the
same day.

## ✂️ END — paste into App Store Connect

---

## Notes for you, not for Apple

### The invite gate is off for the submission window

`INVITE_ONLY=false` was set on the Railway `api` service on 2026-08-23, so
production sign-up is open and `invite_required` reports `false`. The notes say
so, and there is nothing for a reviewer to be blocked by.

**Invite codes still work.** Neither `create_invite_code` nor `redeem` consults
the flag, so codes remain mintable and redeemable — they are simply not
required. Turning the gate back on is one variable and a redeploy:

```bash
railway variables --service api --set "INVITE_ONLY=true"
railway redeploy --service api --yes
```

Everything built for the gated case stays in place and stays tested, so flipping
it back needs no code change:

- `seed_review_account` mints and redeems a real single-use invite for the demo
  account when the gate is on. Two tests cover it — one proves the reviewer
  reaches a gated endpoint, its sibling proves an ordinary account still does
  not.
- Both native apps have a gate screen, routed after the consent step, with
  account deletion reachable from it. Four checks in
  `check_ios_submission_source.py` fail if any of that is removed.

**If you turn it back on before submitting, restore the paragraph explaining it
to the reviewer.** A reviewer who registers, hits a wall, and finds no
explanation in the notes files a Guideline 2.1 rejection.

### Before you paste

- [ ] Confirm **invite@thoughtpins.com** and **support@thoughtpins.com** both
      receive mail, and that you will see them during the review window. Apple
      does email, and a bounce during review is a rejection.
- [ ] Put the demo password in App Store Connect's **Sign-In Information**
      fields, not in the notes body.
- [ ] Re-run the seed against production so the demo data and admission exist on
      the backend the app actually talks to. See `AFTER_DEVELOPER_ACCOUNT.md`.
- [ ] Confirm the backend is not in maintenance mode for the whole review
      window.

### Things deliberately not claimed

The notes do not name the AI provider. `site/ai-disclosure.html` and
`site/privacy.html` are the binding disclosures, and they must stay accurate
about what actually processes user content. If you change providers, change
those pages in the same deploy — App Review compares the app's claims to the
linked policy, and a mismatch is worse than either statement alone.
