# Thought Pins Visual System

This file is the canonical design contract for automated review. Product
strategy lives in `docs/product/PRODUCT.md`; implementation notes live in
`DESIGN_SYSTEM.md`.

## Physical Scene

A person checks a private memory companion at a desk in daylight or on a phone
between real-world moments. The interface must remain calm and readable, but
it should feel authored rather than sterile.

## Color Strategy

Product UI uses a restrained neutral canvas with terracotta below 10 percent
of the visible surface. The public brand page may commit more strongly to the
terracotta and charcoal pair. Sage and blue are semantic support colors, not
alternate themes.

### Palette

| Role | Value |
|---|---|
| Canvas | `#f8f8f6` |
| Surface | `#ffffff` |
| Secondary surface | `#fcfbf9` |
| Ink | `#221d16` |
| Soft ink | `#6b6459` |
| Faint ink | `#948c7f` |
| Line | `#e6e2dd` |
| Strong line | `#d5cfc7` |
| Brand orange | `#e8612b` |
| Deep brand | `#bd451b` |
| Accessible action | `#b33e16` |
| Action hover | `#8f2e0e` |
| Brand tint | `#fbe9dd` |
| Success sage | `#587465` |
| Success tint | `#e6ede7` |
| Source blue | `#44708a` |
| Source tint | `#e4edf2` |
| Danger | `#a83232` |
| Charcoal | `#26211b` |

## Typography

- Display and reflective text: **Newsreader Variable**, weights 480-620.
- Product and reading text: **Source Sans 3 Variable**, weights 400-700.
- Monospace: SFMono-Regular, Consolas, or Liberation Mono.
- Both brand fonts are self-hosted. No runtime font CDN requests.
- App headings use fixed rem sizes. Marketing display type may use bounded
  responsive sizing, never viewport-width font scaling.
- Body copy is normally 16px with 1.55-1.7 line height and a 75ch ceiling.
- Headings use balanced wrapping; prose uses pretty wrapping where supported.
- Letter spacing is zero. Do not use negative tracking.

## Shape And Depth

- Cards, panels, inputs: 8px radius.
- Buttons: 7px radius.
- Status labels: 6px radius.
- Avatars and icon-only circular actions may be fully round.
- Borders and whitespace are the default separators.
- Static cards do not carry broad shadows. Floating composers and dialogs may
  use one purposeful elevation layer.
- Do not nest cards.

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

- Site and web app offer a manual light / dark / auto choice, persisted as
  `tp-theme`. Auto removes `data-theme` so the system decides; an explicit
  choice sets `data-theme="light"|"dark"` and wins over the system.
- Dark mode is designed, not inverted: dark tokens are hand-tuned pairs of
  the light palette (canvas `#1c1916`, ink `#f5f1ea`, brand text `#f0906a`,
  action `#cd4d20` on the site; the app dark scheme mirrors them).
- Every screenshot review runs in both themes at every device width.

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

- Gradients used as decoration or text fill.
- Colored side stripes on cards and callouts.
- Identical marketing card grids.
- Repeated tiny uppercase section kickers.
- Decorative numbered markers unless sequence is meaningful.
- Glassmorphism, ornamental blobs, paper grain, and oversized rounded cards.
- Provider-specific or founder-specific language in public product surfaces.
