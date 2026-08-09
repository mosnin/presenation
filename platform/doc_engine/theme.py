"""Extract document theme tokens from a Presenton slide template."""

from __future__ import annotations

import colorsys
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass
class Theme:
    template: str
    heading_font: str
    body_font: str
    accent: str
    accent_dark: str
    ink: str
    muted: str
    fonts: dict[str, str] = field(default_factory=dict)  # family -> ttf path


def _walk(node, visit):
    if isinstance(node, dict):
        visit(node)
        for value in node.values():
            _walk(value, visit)
    elif isinstance(node, list):
        for item in node:
            _walk(item, visit)


def _saturation(hex_color: str) -> float:
    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    _, l, s = colorsys.rgb_to_hls(r, g, b)
    return s


def _lightness(hex_color: str) -> float:
    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    _, l, _ = colorsys.rgb_to_hls(r, g, b)
    return l


def _darken(hex_color: str, factor: float = 0.75) -> str:
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return "#{:02x}{:02x}{:02x}".format(
        int(r * factor), int(g * factor), int(b * factor)
    )


def load_theme(templates_dir: str | Path, template: str) -> Theme:
    path = Path(templates_dir) / template / "template.json"
    data = json.loads(path.read_text())

    font_sizes: dict[str, float] = {}
    font_usage: Counter[str] = Counter()
    color_usage: Counter[str] = Counter()

    def visit(node: dict) -> None:
        font = node.get("font")
        if isinstance(font, dict) and isinstance(font.get("family"), str):
            family = font["family"]
            size = float(font.get("size") or 0)
            font_sizes[family] = max(font_sizes.get(family, 0), size)
            font_usage[family] += 1
            color = font.get("color")
            if isinstance(color, str) and HEX_RE.match(color):
                color_usage[color] += 1
        for key in ("fill", "color", "background", "stroke"):
            value = node.get(key)
            if isinstance(value, str) and HEX_RE.match(value):
                color_usage[value] += 1
            elif isinstance(value, dict):
                inner = value.get("color")
                if isinstance(inner, str) and HEX_RE.match(inner):
                    color_usage[inner] += 1

    _walk(data.get("layouts", []), visit)

    # Heading font: the family used at the largest size. Body font: the most
    # frequently used family that isn't the heading font (falls back to the
    # heading font for single-family templates).
    heading_font = max(font_sizes, key=lambda f: font_sizes[f], default="Inter")
    body_candidates = [f for f, _ in font_usage.most_common() if f != heading_font]
    body_font = body_candidates[0] if body_candidates else heading_font

    # Accent: the most-used saturated color that isn't near-black/near-white.
    accents = [
        (color, count)
        for color, count in color_usage.most_common()
        if _saturation(color) > 0.35 and 0.15 < _lightness(color) < 0.85
    ]
    accent = accents[0][0] if accents else "#2342b8"

    # Ink: the most-used very dark color.
    darks = [
        (color, count)
        for color, count in color_usage.most_common()
        if _lightness(color) < 0.2
    ]
    ink = darks[0][0] if darks else "#16181d"

    fonts = {
        family: str(Path(templates_dir) / template / rel)
        for family, rel in (data.get("fonts") or {}).items()
    }

    return Theme(
        template=template,
        heading_font=heading_font,
        body_font=body_font,
        accent=accent,
        accent_dark=_darken(accent),
        ink=ink,
        muted="#6b7280",
        fonts=fonts,
    )
