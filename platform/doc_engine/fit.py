"""Self-verifying layout: measure a rendered deck, then repair what overflows.

Generated slides go wrong in a specific, boring way — the model writes six
long bullets, the renderer draws them, and the last two fall off the bottom
of the canvas. Nobody notices until someone presents it.

The fix here is to stop guessing. The deck is rendered in the same headless
browser that produces the PDF, every slide's real content box is measured
against the usable area of the 1920x1080 stage, and slides that overflow are
repaired structurally (split a bullet list across two slides, break a table's
rows, move an image to its own slide). Only when a slide genuinely cannot be
split — one long quote — does it fall back to tightening the type scale.
Then it measures again, because a repair can itself overflow.

The loop is deterministic and needs no model: it is measurement plus rules.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path

from .deck_render import FIT_REPORT_ID, render_deck_html
from .theme import Theme

# A slide counts as overflowing past a few pixels of slack — sub-pixel
# rounding in the browser shouldn't trigger a rewrite.
OVERFLOW_SLACK_PX = 8

# Successive density steps, applied only when a slide cannot be split.
DENSITY_STEPS = ["tight", "tighter", "tightest"]

# Layouts whose content can be divided across additional slides.
SPLITTABLE = {"bullets", "prose", "table", "image_text"}

MAX_PASSES = 4

_REPORT_RE = re.compile(
    rf'<script[^>]*id="{FIT_REPORT_ID}"[^>]*>(.*?)</script>',
    re.DOTALL,
)


class MeasurementError(RuntimeError):
    """Raised when the browser did not produce a fit report."""


def measure_deck(
    deck: dict,
    theme: Theme,
    chromium: str,
    timeout_s: int = 120,
) -> list[dict]:
    """Render the deck headlessly and return one metrics dict per slide.

    Each entry: index, layout, usableHeight/Width, contentHeight/Width,
    overflowY/X (pixels past the usable box, 0 when it fits), and fillRatio
    (1.0 means the content exactly fills the slide).
    """
    html_text = render_deck_html(deck, theme, measure=True)
    with tempfile.TemporaryDirectory() as tmp:
        html_path = Path(tmp) / "measure.html"
        html_path.write_text(html_text)
        result = subprocess.run(
            [
                chromium,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--hide-scrollbars",
                "--allow-file-access-from-files",
                # Give webfonts time to load; measuring a fallback face would
                # report the wrong height.
                "--virtual-time-budget=8000",
                "--dump-dom",
                f"file://{html_path}",
            ],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    match = _REPORT_RE.search(result.stdout)
    if not match:
        raise MeasurementError(
            "browser produced no fit report "
            f"(exit {result.returncode}); stderr: {result.stderr[:400]}"
        )
    return json.loads(match.group(1))


def _split_items(items: list, ratio: float) -> list[list]:
    """Divide a list into roughly equal parts, sized from how far the slide
    overflowed. Splitting evenly in one step matters: repeatedly peeling off
    a head produces lopsided runs (6 bullets, then 1, then 5)."""
    if len(items) < 2:
        return [items]
    parts = min(max(2, math.ceil(ratio)), len(items))
    per_part = math.ceil(len(items) / parts)
    return [items[i : i + per_part] for i in range(0, len(items), per_part)]


def _repair_slide(slide: dict, metrics: dict) -> list[dict]:
    """Return the slides that should replace this one. A one-element list
    means the slide was tightened rather than split."""
    layout = slide.get("layout")
    ratio = max(metrics.get("fillRatio", 1.0), 1.01)

    if layout in ("bullets", "prose", "table"):
        field = {
            "bullets": "items",
            "prose": "paragraphs",
            "table": "rows",
        }[layout]
        chunks = _split_items(slide.get(field, []), ratio)
        if len(chunks) > 1:
            out = []
            for position, chunk in enumerate(chunks):
                part = {**slide, field: chunk}
                # Speaker notes belong with the first part only; a table's
                # header repeats so each continuation reads on its own.
                if position > 0:
                    part.pop("notes", None)
                out.append(part)
            return out

    elif layout == "image_text":
        # Give the picture its own slide and let the copy breathe.
        image_slide = {
            "layout": "image",
            "heading": slide.get("heading"),
            "image": slide.get("image"),
        }
        text_slide = {
            "layout": "bullets",
            "heading": slide.get("heading"),
            "items": slide.get("items", []),
        }
        if slide.get("notes"):
            text_slide["notes"] = slide["notes"]
        if not text_slide["items"]:
            return [image_slide]
        return [text_slide, image_slide]

    # Nothing structural left to do: tighten the type one step.
    current = slide.get("density")
    try:
        step = DENSITY_STEPS.index(current) + 1 if current else 0
    except ValueError:
        step = 0
    if step < len(DENSITY_STEPS):
        return [{**slide, "density": DENSITY_STEPS[step]}]
    return [slide]  # already as tight as we go; leave it rather than loop


def fit_deck(
    deck: dict,
    theme: Theme,
    chromium: str,
    max_passes: int = MAX_PASSES,
) -> tuple[dict, dict]:
    """Measure and repair until every slide fits (or passes run out).

    Returns (deck, report) where report describes what happened:
        {"passes": int, "repaired": int, "slides_before": int,
         "slides_after": int, "overflowing": [...], "fitted": bool}

    On a measurement failure the original deck is returned with the error
    recorded — a deck that renders is better than no deck.
    """
    working = deepcopy(deck)
    slides_before = len(working.get("slides", []))
    repaired_total = 0
    passes = 0
    last_overflow: list[dict] = []

    for _ in range(max_passes):
        try:
            metrics = measure_deck(working, theme, chromium)
        except (MeasurementError, subprocess.SubprocessError, OSError) as exc:
            return working, {
                "passes": passes,
                "repaired": repaired_total,
                "slides_before": slides_before,
                "slides_after": len(working.get("slides", [])),
                "fitted": False,
                "error": f"layout measurement skipped: {exc}",
            }
        passes += 1

        overflowing = [
            m
            for m in metrics
            if m["overflowY"] > OVERFLOW_SLACK_PX or m["overflowX"] > OVERFLOW_SLACK_PX
        ]
        last_overflow = overflowing
        if not overflowing:
            break

        by_index = {m["index"]: m for m in overflowing}
        rebuilt: list[dict] = []
        for index, slide in enumerate(working.get("slides", [])):
            if index in by_index:
                replacements = _repair_slide(slide, by_index[index])
                # A repair that changes nothing would spin the loop forever.
                if replacements != [slide]:
                    repaired_total += 1
                rebuilt.extend(replacements)
            else:
                rebuilt.append(slide)
        if rebuilt == working.get("slides"):
            break  # nothing left to try
        working["slides"] = rebuilt

    return working, {
        "passes": passes,
        "repaired": repaired_total,
        "slides_before": slides_before,
        "slides_after": len(working.get("slides", [])),
        "overflowing": [
            {"index": m["index"], "layout": m["layout"], "overflowY": m["overflowY"]}
            for m in last_overflow
        ],
        "fitted": not last_overflow,
    }
