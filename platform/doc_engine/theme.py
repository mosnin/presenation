"""Extract document theme tokens from a Presenton slide template."""

from __future__ import annotations

import colorsys
import json
import re
from collections import Counter
from dataclasses import dataclass, field, replace
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
    # Page/stage colors. template.json themes render on white; design-spec
    # themes may define a dark stage (e.g. navy background, yellow type).
    bg: str = "#ffffff"
    fg: str | None = None  # defaults to ink when unset
    # Google Fonts families to load in HTML outputs (design-spec themes ship
    # no font files, unlike slide templates which bundle TTFs).
    webfonts: list[str] = field(default_factory=list)
    heading_style: str = "normal"  # e.g. "italic" for serif-italic displays
    heading_transform: str = "uppercase"

    @property
    def text_color(self) -> str:
        return self.fg or self.ink

    def for_print(self) -> "Theme":
        """A print-safe variant of this theme for paged documents.

        Paged output always uses white paper: CSS cannot paint the @page
        margin area, so a colored body leaves a white frame around every
        page, and dark pages are wrong for print anyway. Themes designed for
        a dark stage (gold-on-navy, say) would then put light type on white,
        so the text color is forced back to a legible near-black. Fonts,
        accent, and component fills — which carry most of the aesthetic —
        are untouched.
        """
        accent = self.accent
        # An accent tuned for a dark stage can be too light to read on white
        # (pale gold, for one), and it is also used as a fill behind white
        # table-header text. Darken until it carries on paper.
        while _lightness(accent) > 0.55:
            accent = _darken(accent, 0.8)

        if _lightness(self.bg) > 0.65 and _lightness(self.text_color) < 0.5:
            return replace(
                self, bg="#ffffff", accent=accent, accent_dark=_darken(accent)
            )
        return replace(
            self,
            bg="#ffffff",
            fg="#16181d",
            ink="#16181d",
            muted="#6b7280",
            accent=accent,
            accent_dark=_darken(accent),
        )


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


def google_fonts_links(theme: Theme) -> str:
    """<link> tags loading the theme's webfonts, or "" when it bundles TTFs."""
    from urllib.parse import quote

    if not theme.webfonts:
        return ""
    families = "&".join(f"family={quote(f, safe=':;@,')}" for f in theme.webfonts)
    return (
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?{families}'
        '&display=swap">'
    )


def load_theme_spec(path: str | Path) -> Theme:
    """Load a theme from a design-spec markdown file.

    The format (YAML front matter: name, description, colors, color-aliases,
    typography roles, webfonts) follows the design-system spec style of the
    MIT-licensed frontend-slides project (github.com/zarazhangrui/frontend-slides),
    which demonstrated that a lightweight declarative spec is enough for an
    LLM-driven renderer — no coordinate layouts required.
    """
    import yaml

    path = Path(path)
    text = path.read_text()
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if not match:
        raise ValueError(f"{path}: expected YAML front matter between --- lines")
    spec = yaml.safe_load(match.group(1)) or {}

    colors: dict[str, str] = {
        k: str(v) for k, v in (spec.get("colors") or {}).items()
    }
    aliases: dict[str, str] = spec.get("color-aliases") or {}

    def color_of(alias: str, default: str) -> str:
        value = aliases.get(alias, "")
        value = colors.get(value, value)  # alias may point at a named color
        return value if HEX_RE.match(value) else default

    typography: dict = spec.get("typography") or {}

    def family_of(*roles: str, default: str) -> str:
        for role in roles:
            entry = typography.get(role)
            if isinstance(entry, dict) and entry.get("fontFamily"):
                return str(entry["fontFamily"]).split(",")[0].strip().strip('"')
        return default

    display = typography.get("display") or typography.get("h1") or {}
    bg = color_of("c-bg", "#ffffff")
    fg = color_of("c-fg", "#16181d")
    accent = color_of("c-accent", "#2342b8")

    return Theme(
        template=str(spec.get("name", path.stem)),
        heading_font=family_of("display", "h1", "h2", default="Georgia"),
        body_font=family_of("body", "paragraph", "p", default="system-ui"),
        accent=accent,
        accent_dark=_darken(accent) if _lightness(bg) > 0.5 else accent,
        ink=fg,
        muted=color_of("c-muted", fg + "99" if len(fg) == 7 else "#6b7280"),
        bg=bg,
        fg=fg,
        webfonts=[str(f) for f in (spec.get("webfonts") or [])],
        heading_style=str(display.get("fontStyle", "normal")),
        heading_transform=str(display.get("textTransform", "uppercase")),
    )


def resolve_theme(
    name: str,
    templates_dir: str | Path = "templates",
    specs_dir: str | Path | None = None,
) -> Theme:
    """Find a theme by name: a design-spec markdown in specs_dir wins,
    otherwise fall back to extraction from a slide template's template.json."""
    if specs_dir:
        spec_path = Path(specs_dir) / f"{name}.md"
        if spec_path.exists():
            return load_theme_spec(spec_path)
    template_path = Path(templates_dir) / name / "template.json"
    if template_path.exists():
        return load_theme(templates_dir, name)
    raise FileNotFoundError(
        f"No theme named {name!r}: looked for"
        f" {Path(specs_dir) / (name + '.md') if specs_dir else '<no specs dir>'}"
        f" and {template_path}"
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
