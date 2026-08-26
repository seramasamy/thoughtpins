# App Store screenshots

Captured 2026-08-25 from the real app, signed in to **production**
(`api.thoughtpins.com`) as the App Review demo account, with content the
account actually holds — the Maya / Atlas Cafe / Northstar Memory fictional
set. Nothing here is a mockup, a device frame, or an empty state.

Regenerate with `StoreScreenshotTests` (see `MAC_START_HERE.md`); it signs in,
asks Chat a question, waits for the real answer, and walks the tabs.

**Assert that each screen actually opened.** An earlier set shipped an
`07-account.png` that was really the Pins screen: the status banner was
covering the Account button, the tap was swallowed, and the test screenshotted
whatever was still on screen. The banner no longer takes hit tests, but a
capture run with no assertion will happily record the wrong screen again.

## What is here

| Folder | Device | Pixels | Slot |
|---|---|---|---|
| `iphone-1284x2778/` | iPhone 13 Pro Max, iOS 17.2 | 1284 × 2778 | iPhone 6.5-inch |
| `ipad-2048x2732/` | iPad Pro 12.9-inch (6th generation), iOS 17.2 | 2048 × 2732 | iPad 12.9-inch |
| `evidence/` | Not for upload — the sign-in screen and the AI-processing consent screen, kept as proof of the review path | — | — |

Six shots per device, in upload order:

1. `02-chat` — the product working: a question answered from the person's own
   journal, in the person's own words, with the route badge showing where the
   answer came from. **Lead with this one.**

   The subject of this shot is the *answer*, not the "Use private memories"
   switch that happens to sit above it. That switch is deliberately not the
   selling point: production runs with `PRIVATE_ALLOW_LLM` off, so entries
   marked private are never sent to a third-party model, and a reviewer who
   turns it on and sends a message gets a refusal. That is the correct
   behaviour and the stronger privacy claim -- but leading a listing with a
   control whose first use is refused invites a 2.3.1 conversation we do not
   need to have. If the framing ever changes so the switch becomes the
   subject, enable the flag first or crop it out.
2. `03-people` — memory cards built from entries
3. `04-recap` — entries by day
4. `05-places` — the place cards
5. `06-pins` — saved readings
6. `07-account` — export and delete, in plain sight

## Sizes: which slot these fill, and why

Apple requires **one iPhone set**, and — because this target is universal
(`TARGETED_DEVICE_FAMILY: "1,2"`) — **one iPad set**. Smaller display classes
are optional; App Store Connect scales the supplied set down for the rest.

**The iPhone set is 6.5-inch by choice, not because 6.9-inch was unavailable.**
6.5-inch (1284 × 2778) is an accepted alternative when no 6.9-inch set is
supplied, and it is produced natively by the iPhone 13 Pro Max simulator, which
this Xcode has. An earlier set was captured at 1290 × 2796; that is the iPhone
15 Pro Max's native resolution but is **not a listed iPhone size in App Store
Connect**, so it would have been rejected at upload. It has been replaced.

The iPad set is 2048 × 2732, the iPad Pro 12.9-inch native resolution, which is
still an accepted iPad size.

**The 6.9-inch set will come from hardware, not a simulator.** An iPhone 17 Pro
Max produces 1320 × 2868 natively — exactly the 6.9-inch slot — so once the
build is on TestFlight, capture the same six screens there and replace the
6.5-inch set. That is an upgrade, not a fix: the 6.5-inch set is valid to
submit as it stands.

The iPad set stays on the 12.9-inch simulator. The iPad A16 available for device
testing is 1640 × 2360, which is **not** a listed App Store Connect iPad size —
the slots are 2064 × 2752, 2048 × 2732 and 1488 × 2266 — so do not plan iPad
screenshots from it.

The 13-inch slot (2064 × 2752) would need an iPad Pro 13-inch simulator and a
newer Xcode than macOS 13 can install. Nothing about the layout would change,
only the canvas.

## Rules these already satisfy

- No status-bar edits, no fake battery or carrier — straight simulator capture.
- No device frames, no marketing text overlaid. If you add overlays later, keep
  a copy of these originals; Apple rejects screenshots that misrepresent the UI.
- No placeholder or lorem content, and no empty states.
- All content is fictional and belongs to a demo account. No real person's
  journal appears in any of them.
