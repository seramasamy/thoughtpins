# Guideline 2.1 response preparation

Apple requested information and a physical-device demonstration for the new
submission. Supply evidence for the features the chosen signed build includes.

The six answers below are a draft. Before sending, attach a recording of the
chosen signed build running on a physical device with the latest operating
system, add its accessible URL to App Review Notes, and verify the demo
credentials in App Store Connect. A simulator recording, unsigned archive or
mock-provider test cannot replace that recording. Do not claim it is attached
until the attachment or link has been checked from another browser.

## Response draft

1. **Physical-device demonstration.** The recording must identify the device,
   OS version, app version and build, begin with launching Thought Pins, and show
   the flow below. Add the completed recording's private review URL and these
   device/build details here before sending this response. No such recording is
   supplied by this repository.
2. **Purpose and audience.** Thought Pins is a private journal and personal
   memory app for people who want to keep and revisit their own experiences,
   ideas and reading. Users save notes, voice transcripts and sources; the app
   organizes people and places and answers questions with references to the
   saved record. It helps users find context that would otherwise be scattered
   across notes. AI output can be inaccurate, so the underlying sources remain
   inspectable. It is not a financial, medical or other regulated advisory app.
3. **Access and main features.** Enter the verified demo username and password
   in App Store Connect's Sign-In Information fields. The account must contain
   fictional content and remain available throughout review. Alternatively,
   register a separate account with email and password, accept the AI-processing
   disclosure and save an invented note. Try Chat, Recap, People, Places, Pins,
   Capture, Account export and account deletion. No purchase or sample file is
   required. A separate account is recommended for deletion so other reviewers
   retain demo access. A short fictional sample appears below.
4. **External services.** The hosted deployment uses Railway for the API,
   background workers, PostgreSQL and Redis; Qdrant for semantic search;
   Cloudflare for domain and web
   routing; DeepSeek for configured AI organization and responses; OpenAI for
   embeddings and hosted voice transcription; and Resend for account email and
   sign-in links. Tesseract OCR and pypdf run on the server. The app's
   account/session system is operated by Thought Pins.
   Enabled identity providers must be listed for the submitted build: native
   Apple sign-in requires the separate verification in
   [APPLE_SIGN_IN.md](APPLE_SIGN_IN.md), and currently remains unverified. Google
   web sign-in is separate from the native build. Confirm this list against the
   deployment before sending; private experimental integrations are not part of
   the submitted app. Users consent before AI processing. Provider disclosures:
   https://thoughtpins.com/ai-disclosure.
5. **Regions.** The product has no intentional region-specific feature or
   content variants. Its screens are in English; image OCR currently reads
   English. Online functions need access to the configured services. Confirm
   the selected App Store territories and service availability before stating
   that the submitted build is consistently available in all selected regions.
6. **Regulated services and protected material.** Thought Pins is a private
   note-taking and recall tool. It does not offer brokerage, trading execution,
   investment recommendations, medical diagnosis or other regulated services.
   The review fixtures are invented. Users deliberately supply their own
   documents; link capture respects access restrictions and does not bypass
   paywalls. No protected third-party publication is bundled as the review
   dataset. No regulated-industry license or publisher authorization is claimed.

## Physical-device recording walkthrough

Use the exact signed build selected for submission. Turn on Do Not Disturb and
keep unrelated personal notifications out of the recording. Show real app
screens; do not substitute promotional artwork or a simulator for the device.

1. Start on the home screen and launch Thought Pins. State or show device, OS,
   app version and build in the recording or accompanying notes.
2. Register a disposable account, show password-entry behavior and the explicit
   AI-processing consent, then reach the app. Keep the review demo password out
   of the video; it belongs in the private sign-in fields.
3. Save: “I met Maya at Atlas Cafe today. We discussed the community garden.
   I left my violet compass in the blue desk drawer.” Wait for processing to
   finish; show useful feedback during the wait.
4. Ask “Where did I leave my compass?” Inspect the answer and its source. Edit
   the question and resend, showing that the old branch is replaced. Open
   People, Places, Pins and Recap using this account's actual saved material.
5. Capture an invented text document and a clear image of typed English text.
   If demonstrating voice, show the consent/permission request, record a short
   invented note, and verify its transcript. Demonstrate denial and recovery
   during QA even if the submitted recording uses the successful path.
6. Show Report a reply. Explain that notes and AI responses are private to the
   account: there is no public feed, social graph, user-to-user messaging or
   exposure to another user's content, so user blocking does not apply.
7. Open Account, change appearance, export data, sign out and sign back in.
   If Apple sign-in is enabled in this build, separately demonstrate a real
   Apple account with Hide My Email and subsequent sign-in.
8. Delete the disposable account from inside Account, show confirmation and
   return to sign-in, and verify that its old credentials cannot regain access.
   The release is free, with no paid content, subscriptions or purchase links.
9. Separately test the same release on a physical iPad and other supported
   devices, including rotation, larger text, VoiceOver, offline drafts,
   reconnect, upload cancellation and app backgrounding. Record the outcome
   and distinguish devices actually tested from simulated layouts.

Put the six completed answers in the App Store Connect response **and** the
App Review Information Notes field. Copy the verified demo credentials into
Sign-In Information. The notes block in [REVIEW_NOTES.md](REVIEW_NOTES.md)
provides the shorter navigation instructions; reconcile it with the chosen
build and the completed answers. Keep the backend and demo account live during
review.

References: [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/)
and [account deletion](https://developer.apple.com/support/offering-account-deletion-in-your-app/).
