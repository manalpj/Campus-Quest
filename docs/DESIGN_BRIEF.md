# Design brief: calm, specific, not vibecoded

## Mood
A campus event tool. Clear, friendly, outdoors-readable. Think signage, not a startup landing page.

## Colour (CSS custom properties)
- Background: warm off-white #F6F4EF (never pure white as the page background)
- Surface (cards): #FFFFFF with a 1px border #D9D4C8
- Text: #1F2328, secondary text #4A5058 (check contrast)
- Primary action: blue #1A73E8
- Success: green #188038. Error: red #D93025. Attention: amber #B06000 on a light amber fill.
- Use the four Google colours only as small accents, never as large gradients.

## Type
- System font stack only (system-ui, -apple-system, Segoe UI, Roboto, sans-serif). No external fonts.
- Base 16px, line height 1.5. Headings 20 to 28px, semibold. Big numbers (timer, rank) use tabular numerals.

## Shape and depth
- One corner radius for the whole app: 6px.
- Depth comes from 1px borders, not shadows. At most one very subtle shadow on a modal.
- Spacing scale: 4, 8, 12, 16, 24, 32. Nothing else.

## Components
- Buttons: solid for the one main action, outlined for the rest. Minimum height 44px. Clear pressed and disabled states. No hover animations.
- Status chips (GPS good or weak, power-up counts): text plus an icon shape, never colour alone.
- Icons: simple inline SVG line icons, consistent stroke. No emoji as icons.
- Cards hold one idea each. Do not fill every gap with a card (no bento grid).

## Never use (the "looks vibecoded" list)
Pure white backgrounds, purple and black schemes, glow orbs in the background, dot-grid backgrounds, spark or star icons, harsh gradients, heavy drop shadows, decorative checkmark lists, three-tier pricing blocks, hover animations, fake testimonials or numbers.

## Copy
Short and concrete. Say what to do: "Walk to the spot and wait 8 seconds", not "Unlock the magic".

## Accessibility
Text contrast at least 4.5:1. Visible keyboard focus. Labels on every field. aria-live for errors. Colour is never the only signal. Text scales to 200%.