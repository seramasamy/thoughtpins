# App Store screenshots

Captured 2026-08-25 from the real app, signed in to **production**
(`api.thoughtpins.com`) as the App Review demo account, with content the
account actually holds — the Maya / Atlas Cafe / Northstar Memory fictional
set. Nothing here is a mockup, a device frame, or an empty state.

Regenerate with `StoreScreenshotTests` (see `MAC_START_HERE.md`); it signs in,
asks Chat a question, waits for the real answer, and walks the tabs.

## What is here

| Folder | Device | Pixels |
|---|---|---|
| `iphone-1290x2796/` | iPhone 15 Pro Max, iOS 17.2 | 1290 × 2796 |
| `ipad-2048x2732/` | iPad Pro 12.9-inch (6th generation), iOS 17.2 | 2048 × 2732 |
| `evidence/` | Not for upload — sign-in and consent screens, kept as proof of the review path | 1290 × 2796 |

Six shots per device, in upload order:

1. `02-chat` — the product working: a question answered from the person's own
   journal, with the route badge and the private-memory control visible. **Lead
   with this one.**
2. `03-people` — memory cards built from entries
3. `04-recap` — entries by day
4. `05-places` — the place cards
5. `06-pins` — saved readings
6. `07-account` — export and delete, in plain sight

## Sizes: what Apple requires, and what these are

Apple requires **one iPhone set**, and — because this target is universal
(`TARGETED_DEVICE_FAMILY: "1,2"`) — **one iPad set**. Sets for smaller display
classes are optional; App Store Connect scales the largest set down for the
rest.

What is here is the largest of each that this toolchain can produce:

- **1290 × 2796** is the native resolution of the iPhone 15 Pro Max (6.7-inch),
  and has been the standard accepted upload for the top iPhone slot.
- **2048 × 2732** is the native resolution of the iPad Pro 12.9-inch, and is
  the long-standing required iPad size.

**Confirm the slot in App Store Connect before uploading, and do not take the
above as final.** Apple added a 6.9-inch iPhone class (1320 × 2868, iPhone 16
Pro Max) and a 13-inch iPad class (2064 × 2752), and if App Store Connect
insists on those exact pixel dimensions rather than accepting these, they
cannot be produced here: those simulators need a newer Xcode than macOS 13
can install. That is a parked item, not a fixed one — see the outstanding list
in `MAC_START_HERE.md`.

Nothing about the layout would change, only the canvas: the same six screens
at a larger frame.

## Rules these already satisfy

- No status-bar edits, no fake battery or carrier — straight simulator capture.
- No device frames, no marketing text overlaid. If you add overlays later, keep
  a copy of these originals; Apple rejects screenshots that misrepresent the UI.
- No placeholder or lorem content, and no empty states.
- All content is fictional and belongs to a demo account. No real person's
  journal appears in any of them.
