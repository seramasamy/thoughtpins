# Thought Pins Visual System

This file is the canonical design contract for automated review. Product
strategy lives in `docs/product/PRODUCT.md`; implementation notes live in
`DESIGN_SYSTEM.md`.

## Direction

The September 2026 redesign brings a modern, slightly futuristic visual system
to iOS, the responsive web app, and the public site. Cool mineral surfaces,
precise typography, an orbital memory motif, and the established ember mark
connect the surfaces. Content and primary actions retain the strongest hierarchy.
Android retains its existing native palette until a separate implementation pass.

## Color Strategy

| Role | Light | Dark |
|---|---|---|
| Canvas | `#f4f5f9` | `#0c1220` |
| Surface | `#ffffff` | `#151e30` |
| Ink | `#192132` | `#edf2ff` |
| Soft ink | `#616b7f` | `#a9b5cb` |
| Line | `#e0e4ee` | `#2a354b` |
| Brand mark | `#e8612b` | `#e8612b` |
| Filled action | `#b33e16` | `#b33e16` |
| Action text | `#b33e16` | `#ffb291` |
| Secondary accent | `#5454b8` | `#aca8ff` |
| Secondary tint | `#eeedfb` | `#282849` |

White text belongs on the accessible action fill; dark-mode links and active
navigation labels use the lighter action text. Pastel tints also have explicit
dark counterparts. The public homepage uses the dark palette in both system
appearances. Gradients are reserved for subtle atmosphere and hero surfaces.
Native system controls retain the established softened ember tint `#e8895f`
in dark mode; filled buttons use the shared `#b33e16` in both appearances.

## Typography

- iOS and the web app use native sans typography: SF Pro on Apple platforms,
  with Segoe UI and system sans fallbacks on other devices.
- Existing bundled fonts remain available for the static compatibility surface.
- Display headings may use restrained negative tracking, down to `-0.07em`.
  Prose and controls use normal tracking. The responsive gate enforces this.
- Body text remains readable with generous line height and a bounded measure.
- Native type uses scalable text styles; accessibility sizes reflow controls
  and collection grids. Never shrink text to force a layout to fit.

## Shape And Depth

- Web cards: 22px. Native cards: continuous 24pt corners.
- Web controls: 13px, with 16–24px composer and search surfaces.
- Navigation, identity marks, and orbital geometry may use circular forms.
- One subtle elevation layer for a floating composer, popover, or dialog.
- Borders, surface contrast, and whitespace establish hierarchy; every section
  does not need a card. Selectable memories and pins do.
- Native navigation remains platform navigation, preserving its behavior across
  iOS versions and device classes.

## Spacing

- Base grid: 4px.
- Common steps: 8, 12, 16, 20, 24, 32, 48, 72, and 96px.
- Related controls group tightly; sections receive visibly larger separation.
- Desktop product density is moderate. Mobile preserves every core workflow
  with at least 44px touch targets.

## Layout

- Desktop uses a 224px navigation rail and a fluid content region.
- At compact tablet widths the rail collapses to icons.
- At 700px and below, the same five primary destinations become a bottom bar.
- Chat remains the featured center destination.
- The global composer remains available outside Chat without covering content;
  safe-area and bottom padding must be tested at every mobile breakpoint.
- Source and memory collections use repeated cards only because each item is a
  selectable object. Page sections themselves remain unframed.

## Logo

The active mark is a minimal brain silhouette that resolves into a pin point.
It is white on the terracotta app tile. Canonical files are
`site/assets/thought-pins-mark.svg` and
`frontend/public/assets/thought-pins-mark.svg`.

## Motion

- Quick feedback: 140ms.
- Standard state transition: 220ms.
- View entrance: 380ms maximum.
- Primary easing: `cubic-bezier(0.22, 1, 0.36, 1)`.
- Settle easing: `cubic-bezier(0.16, 1, 0.3, 1)`.
- Animate transform and opacity for entrances; avoid layout-property motion.
- Thinking dots indicate genuine indeterminate work.
- No bounce or elastic easing.
- Every animation has a `prefers-reduced-motion` fallback.
- Ambient motion (hero constellation, logo breathe, marquee) runs at idle and
  never draws attention from the task; it pauses off-screen and when hidden.
- Scroll reveal fires once per element (no re-trigger jitter), staggered at
  55-110ms between siblings. In the app, card grids use the `.stagger` utility
  (50ms steps, capped at six items).
- Named motions shared across surfaces: rise, settle, stagger, breathe,
  thinking-dots, constellation. Experimental labs/ pages may exceed these
  rules; they are not product surfaces until adopted.

## Theme

- Web app and legal/support pages honor the existing persisted `tp-theme`
  preference. The app exposes appearance directly in the header.
- iOS follows system appearance with explicit light/dark token pairs.
- The public homepage is intentionally cinematic and dark.
- Screenshot review covers both app appearances, narrow phones, tablets, desktop,
  native Dynamic Type, and reduced motion. Marketing copy remains visible when
  reduced motion is enabled.

## Product States

Every workflow must account for loading, processing, success, validation,
empty, offline, maintenance, permission, rate-limit, and server-error states.
Empty states orient the user and explain the next natural action. Technical
diagnostics belong in authenticated status tools, not ordinary product copy.

## Voice Capture

Voice notes are an optional, user-initiated input path. The permission prompt
appears only after the user chooses the microphone action, the recording state
is visible while capture is active, and a failed or unavailable microphone
falls back to ordinary text and file attachment. Web, iOS, and Android use the
same journal upload contract so voice notes remain portable with the rest of
the user's vault.

## Source Presentation

- Show title, publication, author, publication date, topics, key ideas, status,
  and number of searchable memory sections when available.
- "Open original" always targets canonical URL, then source URL, then original
  submitted URL.
- Never render stored full article text in public pages or source-list cards.
- Never show reader-provider names, rights-basis fields, access methods,
  restricted-access flags, internal IDs, or retrieval scores in ordinary user UI.
- If full text is unavailable, say the link is saved and invite the user to add
  article text they can access. Do not imply wrongdoing.

## Accessibility Floor

- WCAG AA contrast.
- Visible focus indicators and complete keyboard operation.
- Minimum 44x44 CSS-pixel touch targets.
- Safe-area support on mobile.
- `aria-live` for asynchronous status.
- Dynamic Type on iOS and scalable `sp` text on Android.
- No essential information conveyed through color alone.

## Absolute Avoidances

- Rainbow surfaces, gradient text, or animated backdrops behind reading content.
- Colored side stripes on cards and callouts.
- Identical marketing card grids.
- Repeated tiny uppercase section kickers.
- Decorative numbered markers unless sequence is meaningful.
- Heavy blur behind body text, ornamental blobs, paper grain, and oversized rounded cards.
- Provider-specific or founder-specific language in public product surfaces.
