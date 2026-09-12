# Thought Pins Public Site

This directory is the static public site for `thoughtpins.com`. It contains the
product homepage, shared brand assets, and store-facing trust resources.

The app itself lives at `thoughtpins.com/app`. The public site owns legal,
support, security, account deletion, and AI disclosure URLs used for web launch,
TestFlight, App Store review, and Play Store review. The homepage detects a local
no-auth environment through `/v1/client-config` and labels its direct test-session
entry. Public production links always target the authenticated app.

Before public launch, have the policy and terms language reviewed, then keep
this directory aligned with the URLs configured in `.env.production.example`.
The backend public router also serves these same files from the API/app runtime image when `site/` is packaged. Keep file names stable because App Store, Play Store, client config, and smoke tests reference `/privacy`, `/terms`, `/support`, `/account/delete`, and `/ai-disclosure` directly.

The modern homepage and `/classic/` share `assets/product-showcase.css` and
the accessible device tabs in `assets/site.js`. Product images are captures of
the web app with fictional fixtures. Classic-only typography and surfaces live
in `assets/classic-site.css`; keep modern homepage refinements separate.

Run `cd frontend && npm run smoke:site:ui` for Chromium and WebKit coverage at
eight phone, tablet, and desktop widths, including device-tab keyboard use,
resizing, no-JavaScript fallback, dark appearance, contrast, and overflow. The
command starts a loopback static server that supports the production policy
URLs. No account or model-provider credentials are needed.

The modern homepage follows **How it works → The app → Your control**. The
existing `#week` anchor now opens a directly scrollable set of examples; it is
kept for existing links. `/classic/` remains available with its **Modern Site**
return link. The modern header and footer do not advertise the classic route.

`assets/modern-home.css` owns this composition. `assets/labs.js` owns the
progressive reveals and example controls; `assets/motion-preference.js` shares
the session choice with the classic site;
`assets/constellation.js` owns the decorative canvas. Its floating field and
scroll-to-logo sequence were
recovered from pre-redesign backup `a67bbdf`: 135 motes on every screen, the
original individual floating speeds, 14px wobble, 12px vertical drift, dynamic
nearby links and long fine strands. Keep the original display-synchronized
cadence and pixel ratio cap of 2. Do not thin the phone field or slow its clock.
Positions scale on resize without reshuffling. As the visitor scrolls, the
introduction fades and all 135 motes gather along the actual mark's eight paths;
scrolling back up reverses the assembly. Preserve the backup's cubic easing,
260svh desktop runway and 190svh phone runway. Small viewport
units keep the stage stable when mobile browser chrome changes. The synchronous
sampler in `assets/constellation-shape.js` avoids waiting for an image fetch.
Keyboard focus keeps the introduction visible; fully faded links are inert.
Short windows, oversized text, unavailable SVG geometry and system Reduce Motion
use ordinary document flow, without the pinned sequence.
Pause when offscreen, hidden or leaving the page, and resume on restoration.
The motion toggle pauses automatic floating/twinkle and the marquee; deliberate
scrolling still controls assembly. Live system Reduce Motion disables both
automatic animation and assembly. All content and native scrolling remain usable
without JavaScript.
Changing to a static layout restores the introduction's accessibility even if
the canvas is offscreen and its drawing loop is suspended.
Product captures reserve their dimensions before lazy loading to avoid layout
shifts. `frontend/site-e2e/motion.spec.ts` covers these behavior boundaries;
`frontend/site-e2e/constellation.spec.ts` checks the original density, displacement
and changing connections against a controlled display clock.
`frontend/site-e2e/constellation-scroll.spec.ts` compares every formed node with
the canonical SVG, and checks reversal, resizing, focus and fallback behavior.

Public diagrams in the repository use the self-contained static
[retrieval SVG](../docs/architecture/assets/retrieval-pipeline.svg), with a text
equivalent beside each use. Do not require GitHub's Mermaid runtime to read the
architecture. The SVG contains no scripts, external fonts or remote assets.
