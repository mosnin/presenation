"""Synthesize a theme from a brand image.

Authoring a design spec takes a designer ten minutes and a non-designer an
afternoon. But most people already have the answer sitting on their laptop:
a logo, a website screenshot, a product shot. This extracts a usable theme
from that image — a background, a text color that reads on it, and an accent
that is actually the brand's — so a deck can be generated on-brand with no
theme authoring at all.

The method is deliberately boring and deterministic: quantize the image,
group near-identical colors, then assign roles by contrast and saturation
rather than by frequency alone (the most common color in a logo is usually
the background it sits on, not the brand color).

Requires Pillow.
"""

from __future__ import annotations

import colorsys
from pathlib import Path

from .theme import Theme, _darken, _lightness, _saturation

# Colors closer than this in RGB space are treated as the same brand color;
# anti-aliasing and JPEG artifacts produce clouds of near-identical pixels.
MERGE_DISTANCE = 40

# Ignore colors covering less than this share of the image: stray pixels are
# not brand colors.
MIN_SHARE = 0.005

QUANTIZE_COLORS = 32

# WCAG-ish contrast floor for body text against its background. Not full
# WCAG (that needs the relative-luminance formula per channel), but enough to
# refuse an unreadable pairing.
MIN_TEXT_CONTRAST = 4.0


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    channels = []
    for value in rgb:
        c = value / 255
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = _relative_luminance(a), _relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def extract_palette(
    image_path: str | Path, max_colors: int = 8
) -> list[tuple[tuple[int, int, int], float]]:
    """Return [(rgb, share_of_image)] sorted by share, near-duplicates merged."""
    from PIL import Image

    with Image.open(image_path) as img:
        img = img.convert("RGB")
        # Downscale first: full-resolution counting is slow and adds nothing.
        img.thumbnail((400, 400))
        quantized = img.quantize(colors=QUANTIZE_COLORS, method=Image.MEDIANCUT)
        palette = quantized.getpalette() or []
        counts = quantized.getcolors() or []

    total = sum(count for count, _ in counts) or 1
    raw: list[tuple[tuple[int, int, int], float]] = []
    for count, index in sorted(counts, reverse=True):
        rgb = tuple(palette[index * 3 : index * 3 + 3])  # type: ignore[assignment]
        if len(rgb) == 3:
            raw.append((rgb, count / total))  # type: ignore[arg-type]

    merged: list[list] = []
    for rgb, share in raw:
        for group in merged:
            if _distance(rgb, group[0]) < MERGE_DISTANCE:
                group[1] += share
                break
        else:
            merged.append([rgb, share])

    return [
        (rgb, share)
        for rgb, share in ((g[0], g[1]) for g in merged)
        if share >= MIN_SHARE
    ][:max_colors]


def _pick_background(
    palette: list[tuple[tuple[int, int, int], float]],
) -> tuple[int, int, int]:
    """The background is the dominant color, but pushed to an extreme: a deck
    on a mid-grey is muddy, and brand images are usually on white or near it."""
    dominant, _ = palette[0]
    light = _lightness(_hex(dominant))
    if light > 0.55:
        return (255, 255, 255) if light > 0.85 else dominant
    if light < 0.2:
        return dominant
    # A mid-tone dominant color makes a poor stage; default to paper and let
    # the color become the accent instead.
    return (255, 255, 255)


def _pick_accent(
    palette: list[tuple[tuple[int, int, int], float]],
    background: tuple[int, int, int],
) -> tuple[int, int, int]:
    """The brand color: the most saturated color that stands off the
    background, weighted by how much of the image it covers."""
    best: tuple[float, tuple[int, int, int]] | None = None
    for rgb, share in palette:
        hex_value = _hex(rgb)
        saturation = _saturation(hex_value)
        if saturation < 0.15:
            continue  # greys are not brand colors
        separation = contrast_ratio(rgb, background)
        if separation < 1.6:
            continue  # invisible against the stage
        score = saturation * 2 + min(share, 0.4) + min(separation, 6) / 6
        if best is None or score > best[0]:
            best = (score, rgb)
    if best:
        return best[1]
    # Monochrome source: derive an accent from the darkest available color.
    darkest = min(palette, key=lambda entry: _lightness(_hex(entry[0])))[0]
    return darkest


def _pick_text(
    background: tuple[int, int, int],
    palette: list[tuple[tuple[int, int, int], float]],
) -> tuple[int, int, int]:
    """Prefer a brand-ish text color, but only if it is genuinely readable;
    otherwise fall back to near-black or near-white."""
    candidates = sorted(
        palette,
        key=lambda entry: contrast_ratio(entry[0], background),
        reverse=True,
    )
    for rgb, _ in candidates:
        if (
            contrast_ratio(rgb, background) >= MIN_TEXT_CONTRAST
            and _saturation(_hex(rgb)) < 0.5
        ):
            return rgb
    return (22, 24, 29) if _lightness(_hex(background)) > 0.5 else (245, 245, 245)


def _mix(
    a: tuple[int, int, int], b: tuple[int, int, int], amount: float
) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * amount) for x, y in zip(a, b))  # type: ignore[return-value]


def theme_from_image(
    image_path: str | Path,
    name: str | None = None,
    heading_font: str = "Archivo",
    body_font: str = "Inter",
) -> Theme:
    """Build a Theme from a logo or screenshot.

    Fonts are not inferred — identifying a typeface from an image is a
    different problem, and guessing wrong is worse than a clean default. Pass
    heading_font/body_font to override; any Google Fonts family works.
    """
    palette = extract_palette(image_path)
    if not palette:
        raise ValueError(f"{Path(image_path).name}: no usable colors found")

    background = _pick_background(palette)
    accent = _pick_accent(palette, background)
    text = _pick_text(background, palette)
    muted = _mix(text, background, 0.45)

    accent_hex = _hex(accent)
    return Theme(
        template=name or Path(image_path).stem,
        heading_font=heading_font,
        body_font=body_font,
        accent=accent_hex,
        accent_dark=_darken(accent_hex),
        ink=_hex(text),
        muted=_hex(muted),
        bg=_hex(background),
        fg=_hex(text),
        webfonts=[f"{heading_font}:wght@600;800", f"{body_font}:wght@400;600"],
        heading_transform="uppercase",
    )


def theme_to_spec(theme: Theme, description: str | None = None) -> str:
    """Serialize a synthesized theme as a design-spec markdown file, so it can
    be reviewed, edited by hand, and committed like any other theme."""
    webfonts = "\n".join(f'  - "{font}"' for font in theme.webfonts)
    return f"""---
name: {theme.template}
description: {description or f"Generated from a brand image. Accent {theme.accent} on {theme.bg}."}

colors:
  background: "{theme.bg}"
  text: "{theme.text_color}"
  accent: "{theme.accent}"
  muted: "{theme.muted}"

color-aliases:
  c-bg: background
  c-fg: text
  c-accent: accent
  c-muted: muted

typography:
  display:
    fontFamily: "{theme.heading_font}, Helvetica, sans-serif"
    textTransform: {theme.heading_transform}
    fontWeight: 800
  body:
    fontFamily: "{theme.body_font}, system-ui, sans-serif"
    fontWeight: 400

webfonts:
{webfonts}
---

Generated by `doc_engine.brand` from a brand image. Colors were assigned by
role — background from the dominant tone, accent from the most saturated
color that stands off it, text checked for contrast — rather than by
frequency alone. Edit any value by hand; this is an ordinary design spec.
"""
