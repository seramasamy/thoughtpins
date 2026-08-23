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

**PLEASE READ: THE APP IS IN INVITE-ONLY BETA**

New public sign-ups currently require an invite code. This is a capacity control
for a solo-developer launch, not a paid feature or a locked-away upgrade. There
is nothing to buy anywhere in this app.

**The demo account above is already admitted and needs no code.** Please sign in
with it rather than registering a new account. If you do register a fresh
account, you will correctly see an "invite code required" screen — that is the
beta gate working, not a defect. Email invite@thoughtpins.com and I will admit
any account you create, usually within a few hours.

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

**SUPPORT**

support@thoughtpins.com — https://thoughtpins.com/support
Privacy: https://thoughtpins.com/privacy
Terms: https://thoughtpins.com/terms

Thank you for reviewing. If anything blocks you, email me and I will respond the
same day.

## ✂️ END — paste into App Store Connect

---

## Notes for you, not for Apple

### Why the invite-gate paragraph is there

The previous template in `deploy/store/review-notes-template.md` never mentioned
the gate. Production runs `INVITE_ONLY=true`, and until this pass the seeded
review account was **not** admitted — the reviewer would have signed in and hit
a wall. That is a Guideline 2.1 rejection where the app is never actually
reviewed.

Two things fix it, and both must hold:

1. `seed_review_account` now mints and redeems a real single-use invite for the
   demo account, so it is admitted through the normal path.
   `tests/test_review_seed.py::test_review_seed_admits_the_reviewer_through_the_closed_beta_gate`
   proves it against a gated endpoint, and a sibling test proves an ordinary
   account still meets the gate.
2. The notes above tell the reviewer what they will see if they register anyway.

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
