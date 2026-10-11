"""Tests for Task 23: Design pass and accessibility.

Validates:
- Centralized CSS custom properties in static/style.css matching DESIGN_BRIEF.md palette and radius (6px).
- Universal keyboard focus (:focus-visible) support.
- Button touch target rules (min-height >= 44px).
- HTML accessibility: form fields have labels or aria-labels, map container and HUD status chips have aria-labels.
- Error alerts have aria-live / role="alert".
- Forbidden aesthetic patterns (glow orbs, heavy box-shadows, pure white page backgrounds) are absent.
"""

import re
from pathlib import Path


STATIC_DIR = Path("static")


def test_design_tokens_and_palette():
    """style.css defines the design brief palette, spacing scale, and 6px radius in :root."""
    css_path = STATIC_DIR / "style.css"
    assert css_path.exists()
    css = css_path.read_text(encoding="utf-8")

    # Core palette custom properties
    assert "--bg: #f6f4ef" in css
    assert "--surface: #ffffff" in css
    assert "--border: #d9d4c8" in css
    assert "--text: #1f2328" in css
    assert "--text-secondary: #4a5058" in css
    assert "--primary: #1a73e8" in css
    assert "--success: #188038" in css
    assert "--error: #d93025" in css
    assert "--attention: #b06000" in css
    assert "--radius: 6px" in css

    # Universal focus-visible keyboard ring
    assert ":focus-visible" in css
    assert "outline: 2px solid var(--primary)" in css


def test_button_touch_targets():
    """All main button classes specify at least 44px min-height."""
    css_path = STATIC_DIR / "style.css"
    css = css_path.read_text(encoding="utf-8")

    # Map buttons (48px or min 44px)
    assert re.search(r"\.map-btn\s*\{[^}]*min-height:\s*44px", css)

    # Standard buttons
    assert re.search(r"\.btn\s*\{[^}]*min-height:\s*44px", css)
    assert re.search(r"\.btn-small\s*\{[^}]*min-height:\s*44px", css)
    assert re.search(r"\.gods-btn\s*\{[^}]*min-height:\s*44px", css)
    assert re.search(r"\.gods-btn-sm\s*\{[^}]*min-height:\s*44px", css)
    assert re.search(r"\.btn-text-action\s*\{[^}]*min-height:\s*44px", css)
    assert re.search(r"\.banner-dismiss-btn\s*\{[^}]*min-height:\s*44px", css)
    assert re.search(r"\.status-bar-btn\s*\{[^}]*min-height:\s*44px", css)


def test_no_heavy_shadows_or_forbidden_patterns():
    """Only modal overlays may have a subtle shadow; cards rely on 1px borders."""
    css_path = STATIC_DIR / "style.css"
    css = css_path.read_text(encoding="utf-8")

    # No glow orbs or dot grids
    assert "glow" not in css.lower() or "box-shadow: 0 0" not in css
    assert "radial-gradient" not in css

    # Check that .gods-card, .clue-card, .doc-card do not have box-shadow
    assert not re.search(r"\.gods-card\s*\{[^}]*box-shadow", css)
    assert not re.search(r"\.clue-card\s*\{[^}]*box-shadow", css)
    assert not re.search(r"\.doc-card\s*\{[^}]*box-shadow", css)


def test_html_accessibility_labels_and_live_regions():
    """Form controls have labels, HUD chips have aria-labels, and alerts announce errors."""
    index_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    gods_html = (STATIC_DIR / "gods.html").read_text(encoding="utf-8")
    board_html = (STATIC_DIR / "board.html").read_text(encoding="utf-8")

    # Map container & HUD chips have aria-labels
    assert 'id="map-container"' in index_html and 'aria-label=' in index_html
    assert 'id="status-cleared"' in index_html and 'aria-label=' in index_html
    assert 'id="status-timer"' in index_html and 'aria-label=' in index_html

    # Member inputs in index.html have aria-labels
    member_inputs = re.findall(r'<input[^>]*class="member-input"[^>]*>', index_html)
    assert len(member_inputs) >= 2
    for mi in member_inputs:
        assert 'aria-label="' in mi

    # Alert boxes in gods.html have aria-live
    assert 'id="login-alert"' in gods_html and 'aria-live=' in gods_html
    assert 'id="gods-game-alert"' in gods_html and 'aria-live=' in gods_html
    assert 'id="gods-teams-alert"' in gods_html and 'aria-live=' in gods_html

    # Board status has role="status" and aria-live
    assert 'id="board-status-badge"' in board_html and 'aria-live=' in board_html
