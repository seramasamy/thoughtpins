# Age rating — Thought Pins

**Decision: rate for the mature tier (17+ on the legacy scale, 18+ on the
2025 scale). Do not rate this 4+.**

Getting this wrong does not merely delay approval — Apple removes apps whose
rating understates what they can produce, after they are live. This file records
the reasoning so the answer can be defended or revisited, rather than re-guessed.

---

## Why not 4+, which is what a journal app looks like

Everything except the assistant would justify 4+: no social surface, no ads, no
purchases, no gambling, no user-to-user contact, no web browser.

The assistant is the whole of the argument. `POST /v1/chat` sends the person's
text to a third-party model and returns generated prose. Three things follow:

1. **The output is not enumerable.** We cannot list what it may say, which is
   the question an age rating actually asks.
2. **There is no output moderation of our own.** A search of `src/thoughtpins/`
   finds no moderation, refusal or category-filter layer between the model and
   the reply. We rely entirely on the provider's own safety behaviour, which we
   do not control and which can change without us shipping anything.
3. **Its grounding is the person's own journal**, which may contain anything
   they chose to write — including material about health, grief, sex,
   substances, or self-harm. The system prompt binds the model to that content
   (`memory_answer.py`: "NEVER claim external truth. Say 'your journal shows'"),
   so the more faithful it is, the more directly it can restate mature material.

Point 3 cuts against a low rating harder than an open-domain chatbot would, not
less: an assistant that faithfully recounts a difficult journal entry is doing
its job.

## Why not something in between

9+ and 13+ exist for infrequent or mild instances of enumerated categories.
Neither describes "can generate arbitrary text with no ceiling we impose." The
tier is not chosen because the app is lurid — it is chosen because the honest
answer to "how intense can this get?" is "we do not bound it."

## What this costs, stated plainly

A mature rating narrows the audience and affects discoverability, and it is the
wrong call for a journalling app in every respect except the one that matters.
It is still the right call: the alternative failure mode is removal after
launch, with the rating cited.

**If we want a lower rating later, it has to be earned, not re-answered.** The
route is a moderation layer we control between the model and the reply, with
categories we can name and test. Then the questionnaire can be answered from
what the app permits rather than from what a third party might emit.

## Draft App Store Connect answers

App Store Connect's rating questionnaire changed in 2025 and the exact wording
of the AI questions differs from the legacy form. **Confirm each against the
live form** — these are the intended answers, not a transcription.

| Question | Answer | Why |
|---|---|---|
| Does the app include AI chatbot or generative AI features? | **Yes** | `/v1/chat` returns model-generated prose |
| Can that AI generate unrestricted or unfiltered content? | **Yes** | No moderation layer of our own; provider safety only |
| Cartoon or Fantasy Violence | None | Nothing in the app depicts any |
| Realistic Violence | None | " |
| Sexual Content or Nudity | **None as app content**; possible in generated text | The app ships none. This is why the AI answers above carry the rating |
| Profanity or Crude Humor | Same | The model may restate what the person wrote |
| Alcohol, Tobacco, or Drug Use | Same | " |
| Horror/Fear Themes | Same | " |
| Medical/Treatment Information | **None** | The app offers no medical feature and gives no advice; it can recount health notes the person wrote, which is journal content, not medical information as a feature |
| Gambling, Contests | None | Neither exists |
| Unrestricted Web Access | **No** | There is no in-app browser. "Open original" hands a URL the person saved to the system browser, and article import fetches a URL they typed. Neither is a browsing surface |
| User Generated Content | **No** | Nothing is shared. There is no feed, no profiles, no following, no comments, no links out, and no way for one account to see another's content |
| Made for Kids | **No** | Never enable this |

## The UGC answer is the one most likely to be challenged

Answer **No**, and be ready to explain why in the review notes: Apple's UGC
questions exist because content moves between people. Here nothing does. Every
entry, reply and card is visible only to the account that made it.

What we do have anyway, and should say so: an in-app report action on any chat
reply (Chat → "Report this reply"), which posts to `/v1/safety/reports` and is
answered at support@thoughtpins.com.

## Revisit this when

- A moderation layer of our own lands, which is the only thing that could
  justify a lower tier.
- Sharing, export-to-others, or any account-to-account surface is added, which
  would flip the UGC answer to Yes and bring 1.2's full set of obligations.
- Apple changes the questionnaire again.
