# Legal Review Notes

Engineering updated the public Privacy Policy, Terms, and AI Disclosure on
2026-07-13 to match the implemented voice-note lifecycle. Product counsel or
the release owner should review these commitments before publication:

- voice audio is ephemeral by default and retained only after separate,
  versioned, affirmative consent;
- retained recordings are encrypted and limited to future personal voice
  features for the same account;
- no retained recording is used for advertising, a shared model, another
  user's model, or a general-purpose foundation model;
- disabling retention affects future recordings, while archive deletion
  removes retained audio and future derived voice data;
- account deletion includes recordings and derived voice data, while ordinary
  exports exclude audio bytes and internal storage references;
- production store disclosures must name the actual hosted transcription
  processor when external transcription is enabled.
- `VOICE_ARCHIVE_ENABLED` is false in the public App Store and Play
  configurations. Private/self-hosted deployments may enable the separately
  consented archive, but it must not be switched on in a store release until
  an account-scoped personal voice feature, updated legal review, and matching
  store-console disclosures ship together.

These notes record engineering intent and are not legal advice.
