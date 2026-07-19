# Threshold owner-console design contract

Source reference: `reference/Threshold-MVP.jsx`. This console keeps that reference's
blueprint language while replacing its synthetic browser state with the authenticated local
API.

## Tokens

- Canvas `#081827`; raised surface `#0F2438`; soft surface `#132D44`.
- Primary text `#EEF8FF`; blueprint line `#9FC4DC`; strong line `#C9E5F5`;
  secondary text `#99B8CA`.
- Restricted/windowed state uses distinct gold `#FFD166`; deny/TRIPPED state uses
  crimson `#FF5C70`; armed/active state uses `#6FE0B8`. Gold and crimson retain
  respective 12.44:1 and 6.00:1 contrast against the `#081827` blueprint canvas.
- Spacing follows a 4px base with 12/16/24/40px section rhythms. Corners stay nearly
  square (2px) to retain the plotted-instrument character.
- Narrow system display faces title blocks; system UI serves body text; monospace identifies
  policies, IDs, timestamps, and state.

## Interaction and accessibility

- The owner token and newly issued grant token exist only in React state and request headers.
  They are never placed in storage, URLs, DOM text, logs, screenshots, or build artifacts.
- Controls provide a minimum 44px target, visible amber focus ring, semantic labels, and
  status text in addition to color.
- No-go zones use both red and hatching; restricted zones use both amber and dashed lines.
- A verified TRIPPED snapshot uses a persistent high-contrast alert. Refresh and mutation
  immediately hide the stale snapshot behind a state-unknown loading surface until a fresh
  backend snapshot reports the authoritative state.
- The verification surface remains visible for at least 700ms so a fast loopback response
  cannot reduce owner feedback to an imperceptible flash.
- Blueprint zone names and state labels wrap to at most two deterministic lines and are
  clipped to the owning rectangle as a final containment boundary.
- Layouts must fit at 320px without horizontal page overflow; only the bounded ledger table
  may scroll within its own region.
- Motion is limited to progress rotation and is disabled by `prefers-reduced-motion`.

## Evidence boundary

Automated DOM/accessibility checks and deterministic builds are required. Human visual
review remains a separate gate; the owner accepted the corrected loading duration, semantic
color separation, and blueprint label containment on 2026-07-14. Future visual changes
require a new review.
