# Thought Pins Design System

`DESIGN.md` is the canonical visual contract and `docs/product/PRODUCT.md` is the canonical
product context. This document records implementation guidance shared across
the website, responsive web app, iOS shell, and Android shell.

## Identity

Thought Pins should feel like a private, authored place for memory rather than
a dashboard or an ornamental digital notebook. A neutral canvas keeps long
reading sessions clear; terracotta supplies recognition and warmth; charcoal
anchors navigation and privacy-focused sections.

The active Brain Pin mark combines memory and location in one silhouette. The
canonical web assets are:

- `site/assets/thought-pins-mark.svg`
- `frontend/public/assets/thought-pins-mark.svg`
- `mobile/ios/ThoughtPinsNative/Resources/Assets.xcassets/LaunchMark.imageset/LaunchMark.svg`

The compatibility aliases named `thought-pins-brain-pin.svg` must remain byte
identical to the canonical mark. Retired logo studies are not public assets.
The mark uses an intentional inset and centered transform so the white shape
has equal breathing room inside the orange tile. Store raster icons flatten
that tile to a full-bleed square; the operating system supplies the final
platform mask.

## Type

- Newsreader Variable: display headings, recap titles, memory names, and the
  wordmark.
- Source Sans 3 Variable: interface controls, body copy, metadata, forms, and
  long responses.
- Native shells retain platform typography and scalable text metrics; iOS
  applies the system serif (New York) via `.fontDesign(.serif)` for display
  text, Android uses its serif display family.
- Fonts are bundled locally. Letter spacing is zero.

## Surfaces

- The legal/support pages implement the canonical chrome documented in
  `site/assets/styles/00-foundations.css`: topbar with theme toggle,
  `.page-toc` for long policies, and the full `.site-footer` with brand
  block. All seven pages load `/assets/site.js` (theme, reveals, app links).
- The homepage product preview is a self-playing chat vignette
  (`23-demo-live.css`, driven from `site.js`); the static screenshots remain
  the no-JS / reduced-motion / print representation.
- `site/labs/` holds experimental concepts (currently the "night journal"
  kinetic homepage) with their own stylesheets; they are noindexed, share
  only fonts and product assets, and are not product surfaces.
- iOS theming lives in `ThoughtPinsTheme.swift` (dynamic light/dark token
  colors, `ThoughtPinsThinkingDots`, `ThoughtPinsEmptyState`); chat replies
  are bordered bubbles, lists use branded empty states.
- The static fallback (`frontend/static/`) is rethemed to the warm-paper
  tokens so a failed Vite build never ships the retired green design.

## Core Tokens

```css
--tp-canvas: #f8f8f6;
--tp-surface: #ffffff;
--tp-surface-warm: #fcfbf9;
--tp-ink: #221d16;
--tp-ink-soft: #6b6459;
--tp-line: #e6e2dd;
--tp-line-strong: #d5cfc7;
--tp-brand: #e8612b;
--tp-brand-deep: #bd451b;
--tp-action: #b33e16;
--tp-brand-soft: #fbe9dd;
--tp-sage: #587465;
--tp-sage-soft: #e6ede7;
--tp-blue: #44708a;
--tp-blue-soft: #e4edf2;
--tp-danger: #a83232;
--tp-charcoal: #26211b;
--radius-card: 8px;
--radius-button: 7px;
--radius-chip: 6px;
--motion-quick: 140ms;
--motion-standard: 220ms;
--motion-entrance: 380ms;
--ease-quiet: cubic-bezier(0.22, 1, 0.36, 1);
--ease-settle: cubic-bezier(0.16, 1, 0.3, 1);
```

## Interaction Language

- Use familiar Lucide symbols for icon actions and pair unfamiliar symbols
  with tooltips or visible labels.
- Chat has one composer. Enter sends and Shift+Enter creates a deliberate line
  break.
- Thinking dots communicate model or indexing work; they are a state motif,
  not part of the logo.
- Selected memory cards receive a quiet tinted surface and a small brand dot.
- Source links always open the canonical publisher page in a new context.
- User-facing reading views describe availability, not provider internals.
- The site and web app share one theme controller: a light / dark / auto
  choice persisted as `tp-theme`, applied via `data-theme` on the root
  element. Auto removes the attribute so the system decides. A one-line
  inline script in each page head applies the stored choice before first
  paint. The header icon cycles auto → light → dark; the app also exposes a
  segmented Appearance control in Account.

## Motion Language

- Rise (380ms entrance), settle (scale 1.04 → 1), stagger (50ms sibling
  steps via `.stagger`, wired into Recap/Memory/Pins/Entries grids), breathe
  (hero mark idle), thinking-dots (all busy states), constellation (hero
  particle field, pointer- and idle-reactive).
- View changes in the app carry per-kind entrances on `.view-stage`:
  `--list` (rise), `--focus` (opacity fade), `--detail` (rise + 8px x-drift).
- Skeletons crossfade into real content through `useContentSwap`.
- Native shells mirror the same language: tab transitions, list item
  entrances, mic-recording pulse, and a ThinkingDots port, all gated by
  Reduce Motion / animator-duration settings.

## Responsive Contract

- Desktop: persistent 224px navigation rail, stable content width, sticky detail
  panes only while they fit.
- Tablet: icon rail and single-column detail fallbacks.
- Mobile: five-item bottom navigation, elevated center Chat action, safe-area
  insets, and a global composer that never overlaps the tab bar.
- Critical features are adapted, never removed, on small screens.
- The public product preview is an actual responsive sample: its accessible
  Desktop/Mobile tabs switch between a wide workspace and a phone layout, and
  the default follows the viewport width. It is illustrative copy, never user
  data.

## Design Review Practice

The system borrows the useful discipline of interface-design and TypeUI:
review the rendered interface, keep spacing on the 4px/8px rhythm, and make
the visual language explicit before adding a surface. The repository already
uses token-driven CSS and `lucide-react`; a second utility-CSS framework would
duplicate ownership and add maintenance cost, so it is intentionally not
installed.

Review artifacts live in `reports/design-review/`. They are references for
hierarchy, spacing, and responsive composition, not production images or
source content. Generated mockups must never become user-facing product data.

## Verification

Before shipping frontend changes:

1. Run `npm run build` in `frontend`.
2. Run `npm run smoke:web` for browser workflows and accessibility.
3. Run `npm run smoke:site` for homepage/legal pages at four widths.
4. Run the installed Impeccable detector against `frontend/src` and `site`.
5. Inspect desktop and mobile screenshots for hierarchy, clipping, awkward
   empty states, safe areas, and stale internal language.

Intentional legal section numbering may be ignored by the detector; decorative
numbered marketing scaffolds may not.
