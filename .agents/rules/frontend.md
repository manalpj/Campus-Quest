---
trigger: always_on
---

# Frontend rules
- Mobile-first. Test at 360px wide first. Touch targets at least 44px.
- Vanilla JavaScript only. No frameworks, no build step, no external fonts.
- All game state lives on the server. Do not keep game state in localStorage or sessionStorage.
- Every fetch has error handling and a visible message for the player.
- Real <button>, <label>, <nav> elements. Every control reachable by keyboard with a visible focus ring.
- All colours and sizes come from CSS custom properties in style.css.
- Follow docs/DESIGN_BRIEF.md. Never add glow orbs, dot grids, spark icons, heavy shadows or purple and black schemes.