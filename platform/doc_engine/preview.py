"""Style previews — "show, don't tell".

Renders the same title slide across several themes as PNGs so a person (or an
agent acting for one) picks a visual direction by looking at it, instead of
guessing from a theme name. Cheap: one Chromium screenshot per candidate, no
LLM call and no engine boot.

The approach is borrowed from the MIT-licensed frontend-slides project
(github.com/zarazhangrui/frontend-slides), which uses generated previews as
its style-discovery step.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .deck_render import render_deck_html
from .theme import resolve_theme

# Themes offered when the caller doesn't name any: a spread across light/dark
# and serif/sans rather than six variations of the same idea.
DEFAULT_CANDIDATES = ["momentum", "midnight-gold", "swiss-crimson"]

PREVIEW_WIDTH = 1280
PREVIEW_HEIGHT = 720


def _preview_deck(title: str, subtitle: str | None, meta: str | None) -> dict:
    return {
        "title": title,
        "slides": [
            {
                "layout": "title",
                "title": title,
                "subtitle": subtitle,
                "meta": meta,
            }
        ],
    }


def render_previews(
    title: str,
    subtitle: str | None = None,
    meta: str | None = None,
    themes: list[str] | None = None,
    templates_dir: str | Path = "templates",
    specs_dir: str | Path | None = None,
    out_dir: str | Path = "out",
    chromium: str = "/usr/bin/chromium",
) -> dict[str, str]:
    """Render one title-slide PNG per theme. Returns {theme: png_path}.

    A theme that fails to load is skipped rather than failing the batch — a
    preview set is useful even if one candidate is missing.
    """
    themes = themes or DEFAULT_CANDIDATES
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    deck = _preview_deck(title, subtitle, meta)

    previews: dict[str, str] = {}
    for name in themes:
        try:
            theme = resolve_theme(
                name, templates_dir=templates_dir, specs_dir=specs_dir
            )
        except (FileNotFoundError, ValueError):
            continue

        html_text = render_deck_html(deck, theme)
        png_path = out_dir / f"preview-{name}.png"
        with tempfile.NamedTemporaryFile(
            "w", suffix=".html", delete=False, dir=out_dir
        ) as f:
            f.write(html_text)
            html_path = f.name
        try:
            subprocess.run(
                [
                    chromium,
                    "--headless=new",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--hide-scrollbars",
                    "--allow-file-access-from-files",
                    f"--window-size={PREVIEW_WIDTH},{PREVIEW_HEIGHT}",
                    # Let webfonts and the entrance animation settle.
                    "--virtual-time-budget=6000",
                    f"--screenshot={png_path}",
                    f"file://{html_path}",
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )
        finally:
            Path(html_path).unlink(missing_ok=True)
        if png_path.exists():
            previews[name] = str(png_path)
    return previews
