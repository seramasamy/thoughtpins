# Homepage, diagrams and native graphics · 12 September 2026

This change keeps the mineral/violet/ember visual system and makes the public
site easier to read and navigate. It changes presentation and animation
lifecycle behavior, including native password focus; retrieval, authentication
protocols and storage contracts are unchanged.

| Surface | Change | Reason |
| --- | --- | --- |
| GitHub README and retrieval walkthrough | One static, self-contained SVG replaces both Mermaid blocks. Five stages show query scope, all eight collectors, ranking/selection, context and response. A text equivalent accompanies the image. | Readers can inspect the architecture without GitHub's Mermaid renderer. The optional entity filter, sequential collection and failure limits remain explicit. |
| Modern homepage | How it works → The app → Your control; clearer capture/recall copy and a shorter hero. | Explain the workflow before asking someone to try it, with less empty scrolling. Existing `#week` links remain valid. |
| Navigation | Remove classic links from the modern header/footer; retain `/classic/` and its Modern Site return link. Restore visible mobile Log in. | Keep the main site focused while preserving the older entry point. |
| Examples | Native horizontal scrolling at every size, Previous/Next, arrow keys, Home/End, position and progress. | Remove scroll-driven horizontal transforms; make the full sequence reachable with a thumb, keyboard or pointer. Partial final steps work when multiple cards fit. |
| Site motion | A stable violet/ember network with capped drawing and a shared Pause motion control. Marquee copies include their trailing gap. | Avoid reshuffling on resize, loop seams, background canvas work and inaccessible autoplay. Both homepages and their button hover effects share the session choice and live Reduce Motion setting. Canvas work also follows page visibility and viewport intersection. |
| Both product previews | Reserve screenshot aspect ratios before lazy loading. | Avoid the collapsed phone frame and layout jump on slow connections. |
| Native iOS | A static vector network replaces blurred decorative orbits; sign-in uses one compact brand header; thinking dots use a bounded timeline. Press feedback respects Reduce Motion. | Crisp graphics and less form scrolling on compact phones, with loading animation tied to view visibility, active scene and accessibility preference. |
| Native password submission | Apply enabled/focus changes after SwiftUI finishes rendering; cancel stale queued updates when the field changes or is removed. | Pressing the keyboard's Go action could freeze sign-in when disabling the active UIKit field re-entered SwiftUI's focus graph. The Return-key workflow and direct coordinator test cover this path. |

## Reproduce the checks

```sh
python scripts/release_check.py --strict-quality
python scripts/check_public_export.py
cd frontend
npm run smoke:site:ui
```

The browser suite covers both sites at eight widths, product tabs, keyboard use,
contrast/overflow, missing JavaScript, blocked storage, unavailable canvas,
slow image loading, motion preference changes and lifecycle restoration. The
motion tests observe canvas draws rather than relying on static screenshots.
Simulated page lifecycle events exercise the handlers; they are not proof of
every browser's back/forward cache policy.

The manually dispatched `.github/workflows/strict-release.yml` runs the same
unmodified strict gate on a clean Linux runner and retains its log with the
commit SHA. It needs no production credentials and does not deploy anything.
This provides a reproducible alternative when a development machine is
resource-constrained; it does not relax checks or test deadlines.

Run the [native review harness](../../mobile/ios/ThoughtPinsUIReview/README.md)
against fictional fixtures for navigation, authentication, error recovery,
Dynamic Type and iPad rotation. Use the CI results for the exact commit when
reviewing a current iOS SDK. Local macOS 13 cannot run the current Playwright
WebKit build or produce an App Store upload with a supported Xcode version.

Native review also checks the visible bounds above the software keyboard and
its accessory toolbar. A control reported as hittable by XCTest can still be
covered on a newer simulator. The test waits for keyboard readiness before
checking the password field after Next, and submits through Go as well as the
button. These checks retain the actual focus and successful sign-in assertions.

The site cache key and digest move together so returning visitors receive the
new assets. The domain and public-route checks follow the registration link,
control section and current export wording instead of retired marketing titles;
the legal, privacy and deployment requirements remain enforced.
No schema migration or model-provider test calls are required.
Automated checks and simulator screenshots do not replace a signed physical
device check or establish that every animation will be flawless on all devices.
