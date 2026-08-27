# Web and iOS parity

Nobody had looked at this. The privacy policy, terms and support pages describe
one product; the App Store listing describes one product; there are two clients.
This is what each one actually does, which divergences were chosen, and which
were not.

Read alongside `apple-submission/REVIEW_NOTES.md`. **The listing is the iOS
listing**, so anything true on the web and not on iOS is the direction that gets
a submission rejected — those are called out first.

Verified 2026-08-26 by reading both clients end to end.

---

## Capabilities

| Capability | Web | iOS | Verdict |
|---|---|---|---|
| Write a note | yes | yes | parity |
| Voice note | yes | yes | parity |
| File import | yes | yes | parity |
| Obsidian vault import | yes | yes | parity (iOS lacks the conflict-policy picker) |
| Chat | yes | yes | **divergent** — web keeps a transcript, iOS shows only the latest reply |
| Response styles | yes | yes | parity |
| Importance prompts | yes | yes | parity |
| Private-memories toggle | yes | yes | parity |
| Recap day/week/month | yes | yes | parity |
| People cards | yes | yes | parity |
| Places cards | yes | yes | parity |
| Pins / library list | yes | yes | parity |
| Library source detail | yes | yes | parity |
| Memory card detail | yes | yes | parity |
| Account export | yes | yes | **fixed this pass** — see below |
| AI-processing consent | yes | yes | **fixed this pass** — version comparison |
| Account deletion | yes | yes | parity in effect, divergent in friction |
| Invite redemption | yes | yes | parity |
| Report a reply | standalone form | per-reply only | divergent, scoped |
| Voice archive | yes | yes | parity |
| Sign in: email/password | yes | yes | parity |
| Sign in: Apple | yes | yes | parity (both gated off by server config) |
| Sign in: Google | yes | hidden | intentional — 4.8 |
| Sign in: magic link | yes | **absent** | intentional |
| Manage sign-in methods | yes | **absent** | accidental, deferred |
| Devices / sessions | yes | **absent** | accidental, **scoped to web** |
| Delete a single entry | yes | yes | **shipped this pass** |
| Search | yes | **absent** | accidental, **scoped to web** |

---

## Fixed in this pass

**You could not delete a single entry.** `deleteEntry` had existed in the core
client with no caller, so the right the privacy policy grants — "delete specific
content ... from the app" — could not be exercised from the app at all. That is
a stated user right rather than a feature description, and the page is reachable
from inside the app, so it was shipped rather than scoped: a swipe action on the
Recap list with a confirmation. Both chained promises verified — the memories
extracted from an entry go with it (proven end to end against production: the
assistant could recall the content before the delete and could not after), and
its retained recording goes too (proven by test, because retention is opt-in and
off in production so no live account can have one).

**Account export gave you nothing.** `exportAccount()` fetched the payload and
discarded it, then said "Your export is ready." The privacy policy promises
export "from the app" and the review notes send a reviewer to that button. It
now writes a JSON file and offers the system share sheet; verified on the
shipping binary against production (135 KB, Save to Files).

**Consent never re-prompted on a version bump.** Web compares the stored
acceptance version against the served `LEGAL_DOCUMENT_VERSION`; iOS only checked
that *an* acceptance existed. The day that version moves, every web user would
be re-prompted and no iOS user ever would. iOS compares versions now.

**Rate-limited refresh logged web users out.** Any refresh failure cleared the
session, so a 429 — five auth requests a minute per IP, which is one office
behind one NAT — signed people out with valid credentials. Only 401 and 403 end
a session now, which is the rule iOS already followed deliberately.

**Three iOS strings that were untrue.** A 429 on chat said "Chat failed"; a
rate-limited save called itself an offline draft with full signal; the in-app
safety report sent a 2000-character summary into a field the server caps at 1000
and therefore always failed.

---

## Divergences that are intentional and defensible

**Google sign-in is hidden on iOS.** The app refuses a third-party login unless
Sign in with Apple is offered beside it (Guideline 4.8), and Apple sign-in is
not configured yet. Web has no such rule. The GoogleSignIn SDK was removed from
the iOS build entirely this session, because it could never be reached.

**No magic-link sign-in on iOS.** Passwordless email sign-in on a phone means
leaving the app for a mail client and returning through a URL callback. It is a
real feature, not an oversight, and it is not v1.

**Deletion friction differs.** Web makes you type `DELETE`; iOS uses a
confirmation dialog. Both end at the same server call with the same required
confirmation string. Typing a word on a phone keyboard is friction of a
different kind, and platform conventions differ. Both satisfy 5.1.1(v).

**Chat has no transcript on iOS.** Web keeps a scrollable thread; iOS shows the
latest reply. This is a real product difference and the review notes describe
the iOS behaviour accurately. Adding a transcript needs a message-list model the
app does not have — deliberately deferred, not accidental.

**iOS caps uploads at 25 MB client-side; web does not.** iOS is the stricter and
more honest of the two: it refuses before reading the file. The gap is that
**web** has no guard and will base64-encode a 30 MB file in the browser before
the server rejects it. Web is the one that should change.

---

## Divergences that nobody chose

These are accidental. None is fixed here; each is recorded with its cost.

**No devices or sessions screen on iOS.** The support page says to use the app's
Account screen to "manage devices". `registerDevice`, `revokeDevice`, `sessions`
and `revokeSession` all exist in the core client, uncalled. *Cost: the support
page should be scoped to the web app now — editorial. The screen itself is a
day.*

**No search on iOS.** Terms lists search as a feature. The memory-cards endpoint
takes a query parameter that iOS always sends empty. *Cost: a search field
bound to the existing parameter is small; scoping the terms wording is smaller.*

**Six of nine preference fields are unreachable on iOS** — preferred name,
timezone, reminder hour, notification settings. The request struct, the API
method and the response decode all exist and are exercised. *Cost: rows in an
existing Form. The cheapest item here.*

**No way to set or change a password on iOS**, or to see which sign-in providers
are attached. *Cost: moderate; needs its own screen.*

**Text length caps.** The server caps entries and chat at 50,000 characters and
web mirrors it in three composers. iOS has no cap on the live send path, so a
long entry gets a 422 and then falls into the draft queue, which refuses it too.
*Cost: one `maxLength` equivalent and a counter — small, but it needs the
draft-queue path checked with it.*

**Error wording diverges throughout.** Web renders the server's envelope message
verbatim; iOS maps status codes to its own sentences. Each is internally
consistent and iOS is the more human of the two. The one that matters: iOS
collapses 401 and 403 on login into "credentials did not match", but the server
returns 403 for *email verification required*, which is a different problem with
a different fix. *Cost: one case in `ThoughtPinsAuthFailure` — small, and worth
doing before email verification is ever switched on.*

**Consent copy differs by three edits.** Same meaning, same checkbox stem,
different body sentence and two bullets web has that iOS folds into a paragraph.
*Cost: pick one wording and use it in both. Editorial, but it is consent text,
so it should be one text.*

---

## An open disclosure question, not a defect

**What you ask the assistant is retained as an entry and appears in Recap
alongside notes you deliberately wrote.** `/v1/chat` calls
`remember_user_chat_message`, which writes a `RawEntry` with a distinct `source`
and `processed_status` — deliberately, so conversation turns stay recallable
without polluting the memory graph. Neither client filters the timeline by that
source, so both show questions next to notes. It is not an iOS divergence.

**Is it disclosed? Partly, and the gap is one sentence.**

- `site/privacy.html` **does** disclose the storage: "User Content: journal
  entries, **chat messages**, voice-note transcripts, reminders, uploads..." So
  nobody is told their questions are discarded.
- What no page says is that a chat message is retained **as an entry, in the
  journal timeline**. A reader would reasonably take "chat messages" to mean
  chat history — and there *is* a separate `chat_messages` table that also gets
  a row — not something that appears in Recap next to a note they wrote.
- `site/ai-disclosure.html` comes closest: "When a message is ambiguous, the
  product may disclose whether it is replying as chat or saving a journal
  memory." That describes routing an *ambiguous* message, which is a different
  claim from every question also being retained.

**Recommendation: one sentence, no product change.** In `privacy.html`, after
the User Content list, something like: *"Messages you send to the assistant are
saved with your entries so it can recall the conversation, and appear in your
timeline alongside notes you write. They can be deleted individually like any
other entry."* That last clause is now true, which it was not before this
session.

Not applied — this is wording on a published legal page and it is yours to
approve.

## Promises that are now scoped rather than universal

The published pages describe the product, not the iOS app. These sentences are
true of the web client and not of iOS, and the honest fix for most is editorial:

- support page: "manage devices" — **scoped to the web app**
- terms: "search" — **scoped to the web app**, naming Chat as the iOS route
- AI disclosure: routing "undo" — **scoped to the web app**

The fourth, privacy's "delete specific content ... from the app", was **not**
scoped. It grants a right rather than describing a feature, so the app was
changed to honour it instead.

`REVIEW_NOTES.md` was corrected this pass where it overstated: the safety report
does not email support, and the iOS export is account JSON rather than a
Markdown vault.

Done 2026-08-26. The three feature descriptions name the web app in plain
words; none of them reads as a disclaimer. The right was shipped. A reviewer who
opens the support page from inside the app — which they can, it is linked in
Account — no longer lands on a sentence the app does not honour.
