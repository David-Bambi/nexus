import re
from pathlib import Path

import pytest

# The stylesheet whose color tokens are checked.
STYLESHEET = Path(__file__).parents[2] / "src" / "web" / "static" / "app.css"

# Text colors and the backgrounds they are drawn on, as token names without "--color-".
PAIRS = [
    ("text", "bg"), ("text", "surface"),
    ("text-muted", "bg"), ("text-muted", "surface"), ("text-muted", "surface-muted"),
    ("accent", "bg"), ("accent", "surface"), ("accent-contrast", "accent"),
    ("danger", "bg"), ("danger", "surface"),
    ("warning", "bg"), ("warning", "surface"),
    ("success", "bg"), ("success", "surface"),
]

# Badge colors, drawn on a 12% tint of themselves mixed with the surface color (whatever lies behind).
BADGES = ["text-muted", "accent", "warning", "success", "danger"]

# WCAG AA minimum contrast for normal text.
MINIMUM = 4.5


def _themes() -> dict:
    """Color tokens of the light theme and of the dark theme (light values overridden)."""
    css = STYLESHEET.read_text()
    dark_start = css.index("@media (prefers-color-scheme: dark)")
    pattern = r"--color-([\w-]+):\s*(#[0-9a-fA-F]{6})"
    light = dict(re.findall(pattern, css[:dark_start]))
    dark = {**light, **dict(re.findall(pattern, css[dark_start:css.index("/* Reset", dark_start)]))}
    return {"light": light, "dark": dark}


def _luminance(color : str) -> float:
    """Relative luminance of a #rrggbb color."""
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first : str, second : str) -> float:
    """WCAG contrast ratio between two #rrggbb colors."""
    high, low = sorted([_luminance(first), _luminance(second)], reverse=True)
    return (high + 0.05) / (low + 0.05)


def _tint(color : str, background : str, alpha : float) -> str:
    """The color seen when `color` is drawn at `alpha` opacity over `background`."""
    mixed = [round(alpha * int(color[i:i + 2], 16) + (1 - alpha) * int(background[i:i + 2], 16)) for i in (1, 3, 5)]
    return "#" + "".join(f"{c:02x}" for c in mixed)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_text_colors_meet_wcag_aa_on_their_backgrounds(theme):
    """
    Given the color tokens of a theme
    When measuring each text color against the backgrounds it is used on
    Then every pair reaches a 4.5:1 contrast ratio
    """
    tokens = _themes()[theme]
    low = [(f, b, round(_contrast(tokens[f], tokens[b]), 2)) for f, b in PAIRS
           if _contrast(tokens[f], tokens[b]) < MINIMUM]
    assert low == []


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_badges_meet_wcag_aa_on_their_tint(theme):
    """
    Given the color tokens of a theme
    When measuring each badge color against its own 12% tint mixed with the surface color
    Then every badge reaches a 4.5:1 contrast ratio
    """
    tokens = _themes()[theme]
    low = []
    for name in BADGES:
        ratio = _contrast(tokens[name], _tint(tokens[name], tokens["surface"], 0.12))
        if ratio < MINIMUM:
            low.append((name, round(ratio, 2)))
    assert low == []


def test_badge_tint_is_mixed_with_the_surface_not_transparency():
    """
    Given the badge rule of the stylesheet
    When reading its background
    Then the tint is mixed with the surface color, as the contrast test above assumes
    """
    css = STYLESHEET.read_text()
    badge = css[css.index(".badge {"):css.index("}", css.index(".badge {"))]
    assert "background: color-mix(in srgb, var(--badge-color) 12%, var(--color-surface));" in badge
