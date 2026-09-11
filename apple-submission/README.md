# Apple submission package

Start with [Submission status](SUBMISSION_STATUS.md) for the tested revision and
remaining distribution work. The production app compiles, native iPhone/iPad
reviews run in CI, and an unsigned current-SDK archive has passed verification.
Signing, live review access and physical-device validation remain release steps.

| Task | Instructions |
| --- | --- |
| Work on a Mac | [Mac start here](MAC_START_HERE.md) |
| Verify source and browser workflows | [App Store preparation log](../docs/release/APP_STORE_PREPARATION.md) |
| Inspect native tests and fictional fixtures | [Native review harness](../mobile/ios/ThoughtPinsUIReview/README.md) |
| Configure signing and archive | [Signed archive runbook](../docs/release/MACOS_XCODE_APP_STORE_RUNBOOK.md) |
| Use Xcode Cloud, if selected | [Xcode Cloud runbook](../docs/release/XCODE_CLOUD_RUNBOOK.md) |
| Check physical-device behavior | [Device test script](../docs/release/DEVICE_TEST_SCRIPT.md) |
| Prepare review access and explanations | [Review notes](REVIEW_NOTES.md) |
| Review metadata and privacy answers | [App Store metadata](APP_STORE_METADATA.md) · [Privacy answers](../docs/release/APPLE_REVIEW_ANSWERS.md) |
| Track earlier decisions | [Progress history](PROGRESS.md) |

Run `python scripts/release_check.py --strict-quality` on the intended source.
On a Mac, `./scripts/ios_release.sh preflight` builds the production simulator
app. Neither command establishes signed distribution readiness.

For current-SDK CI validation without an upload:

```sh
gh workflow run ci.yml --ref main -f run_native=true -f upload_testflight=false
```

Both native device jobs must pass before archiving. Uploading requires a
separate, explicit selection and configured credentials. Keep signing material,
real review credentials and generated evidence out of source control.

Before submitting, confirm the backend and review account work, inspect the
actual signed build, and refresh store screenshots from that build. Use the
[current screenshot specifications](https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications/)
and [Apple's review guidance](https://developer.apple.com/app-store/review/).
The source repository, hosted deployment and App Store Connect submission each
need their own verification.
