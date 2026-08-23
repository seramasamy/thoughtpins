# Thought Pins App Review Risk Register

Last reviewed: 2026-07-13.

This register is an engineering checklist, not legal advice. It records the reasons Apple or Google could reject Thought Pins and the local evidence that should be checked before any store submission.

## Highest-Risk Rejection Paths

| Risk | Why Review Could Reject | Current Mitigation | Proof Command |
| --- | --- | --- | --- |
| Backend unavailable during review | Store reviewers need a live, fully functional backend and demo access. | `deploy/store/submission-packet.json`, review account seed, health/deep-health smoke, launch packet. | `python scripts/collect_closed_beta_evidence.py --web-smoke --strict-complete` |
| Account deletion incomplete or hard to find | Apps with account creation must provide in-app deletion; Google also requires a web deletion resource. | `DELETE /v1/me`, Account screen deletion, `/account/delete`, privacy retention copy. | `python scripts/app_store_compliance_check.py` |
| Privacy/Data Safety mismatch | Journal, document, AI, embeddings, diagnostics, and auth data must match store-console disclosures. | `deploy/store/data-safety-inventory.json`, `site/privacy.html`, `site/ai-disclosure.html`. | `python scripts/check_store_submission_packet.py` |
| Voice consent or retention mismatch | Microphone capture requires clear recording indication and purpose disclosure; collecting audio for an unshipped future feature would create a minimization/review risk. | Public store builds set `VOICE_ARCHIVE_ENABLED=false` and discard audio after transcription. Private/self-hosted archive code remains separately gated, version-consented, encrypted, tenant-scoped, and deletable. | `python -m pytest tests/test_voice_archive.py && python scripts/check_ios_submission_source.py` |
| Third-party AI disclosure/consent gap | Apple requires disclosure and explicit permission before sharing personal data with third-party AI; Google expects safe generative AI behavior. | Registration and existing-user native onboarding require AI-processing consent; the privacy policy, AI disclosure, safety report path, and data-safety inventory document processing. | `python scripts/check_ios_submission_source.py && python scripts/check_store_submission_packet.py` |
| AI safety/reporting gap | A chatbot-like app can be rejected if unsafe output has no report path or if prohibited content is enabled. | `POST /v1/safety/reports`, in-app Legal report form, `/ai-disclosure`, `/support`, prohibited generation categories in inventory. | `python scripts/check_store_submission_packet.py` |
| Copyright/access-control circumvention | Article ingestion could be mistaken for unlicensed content import. | Terms and privacy require authorized sources; the fetch policy stores metadata when public text is unavailable. | `python scripts/check_store_submission_packet.py` |
| Sign in with Apple parity | If Google or another third-party login is offered on iOS, Apple requires an equivalent privacy-preserving login option. | OAuth verifier supports Apple and Google; packet marks client IDs as production configuration. | `python scripts/app_store_compliance_check.py` |
| Thin web wrapper / low-quality app | Apple can reject a bare website wrapper or low-effort app. | Native handoff, mobile core, web review harness, app-grade account/export/delete/capture flows. | `python scripts/check_native_review_handoff.py` |
| Hidden local-tool leakage | Public builds must not expose owner-only local adapters, review-bypass controls, or private data. | Private adapter split, public export hygiene, forbidden scan, public UI copy check, client-config omission of local adapter flags. | `python scripts/check_public_export.py` |
| Secrets in public repo/package | Hardcoded credentials or local `.env` leakage would be severe. | `.gitignore`, `.dockerignore`, forbidden scan, public export scan, no review password in store packet. | `python scripts/forbidden_scan.py && python scripts/check_public_export.py` |
| Native permission disclosure | Unnecessary entitlements or vague purpose strings can trigger privacy questions. | Microphone is requested only after a clear voice-note disclosure and user action; recording state is visible; iOS purpose text and Android runtime permission match the product. Broad photos, location, contacts, and notifications remain absent. | `python scripts/check_ios_submission_source.py && python scripts/check_store_submission_packet.py` |
| Inaccurate health/maintenance behavior | Reviewers may reject if the app breaks during a backend restart without clear UI. | Maintenance mode, client config, web banner, runtime smoke. | `python scripts/smoke_startup_shutdown.py` |

## Official References Checked

- Apple App Review Guidelines: https://developer.apple.com/app-store/review/guidelines/
- Apple App Privacy Details: https://developer.apple.com/app-store/app-privacy-details/
- Apple account deletion guidance: https://developer.apple.com/support/offering-account-deletion-in-your-app/
- Google Play User Data policy: https://support.google.com/googleplay/android-developer/answer/10144311
- Google Play account deletion requirements: https://support.google.com/googleplay/android-developer/answer/13327111
- Google Play AI-Generated Content policy: https://support.google.com/googleplay/android-developer/answer/14094294

## Remaining External Proof Before Submission

- Publish `thoughtpins.com` and `thoughtpins.com` over HTTPS with the same legal pages.
- Run Docker/PostgreSQL RLS verification on a Docker-capable host.
- Preserve the passing Playwright, axe, responsive, maintenance, and offline evidence from the final release commit.
- Seed a private review account and enter its credentials only in App Store Connect / Play Console.
- Generate and compile the iOS project on current macOS/Xcode, then configure final Apple signing/provisioning and App Store Connect records.
- Rotate local/test credentials before public beta or any public GitHub export.
