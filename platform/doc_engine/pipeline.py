"""End-to-end generation pipelines: documents (PDF/DOCX/HTML pages) and
interactive HTML decks, both themed by slide templates or design specs."""

from __future__ import annotations

import json
from pathlib import Path

from . import deck as deck_mod
from . import (
    deck_render,
    export,
    llm,
    pptx_import,
    preview,
    render,
    structure,
)
from . import brand
from . import patch as patch_mod
from . import fit as fit_engine
from .theme import Theme, resolve_theme


def _theme_for(
    template: str,
    templates_dir,
    specs_dir,
    brand_image=None,
) -> Theme:
    """A brand image, when given, replaces the named theme entirely."""
    if brand_image:
        return brand.theme_from_image(brand_image)
    return resolve_theme(template, templates_dir=templates_dir, specs_dir=specs_dir)


def generate_document(
    content: str,
    instructions: str | None = None,
    template: str = "general",
    formats: list[str] | None = None,
    templates_dir: str | Path = "templates",
    out_dir: str | Path = "out",
    chromium: str = "/usr/bin/chromium",
    specs_dir: str | Path | None = None,
    brand_image: str | Path | None = None,
) -> dict[str, str]:
    """Generate an A4 document in a template/spec aesthetic.

    Returns {format: output_path}. Formats: pdf, docx, html.
    If an LLM is configured (see llm.py) the content is expanded into a full
    document; otherwise the content is parsed as markdown as-is.
    """
    formats = formats or ["pdf"]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if llm.llm_configured():
        doc = llm.generate_structure(content, instructions)
    else:
        doc = structure.parse_markdown(content)

    theme = _theme_for(template, templates_dir, specs_dir, brand_image)
    html_text = render.render_html(doc, theme)

    outputs: dict[str, str] = {}
    if "html" in formats:
        html_path = out_dir / "document.html"
        html_path.write_text(html_text)
        outputs["html"] = str(html_path)
    if "pdf" in formats:
        outputs["pdf"] = str(
            export.html_to_pdf(html_text, out_dir / "document.pdf", chromium)
        )
    if "docx" in formats:
        outputs["docx"] = str(export.doc_to_docx(doc, theme, out_dir / "document.docx"))
    return outputs


def generate_deck(
    content: str,
    instructions: str | None = None,
    template: str = "general",
    templates_dir: str | Path = "templates",
    out_dir: str | Path = "out",
    specs_dir: str | Path | None = None,
    formats: list[str] | None = None,
    source_pptx: str | Path | None = None,
    chromium: str = "/usr/bin/chromium",
    fit: bool = True,
    brand_image: str | Path | None = None,
    source_deck: dict | None = None,
    patch: list[dict] | None = None,
) -> dict[str, str]:
    """Generate a presentation deck.

    Returns {format: output_path} for the requested formats (`html`, `pdf`).

    The deck model comes from, in order: `source_deck` (an existing deck.json,
    optionally edited by `patch`), `source_pptx` (converting a PowerPoint), an
    LLM when one is configured, or markdown parsed deterministically.
    """
    formats = formats or ["html"]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if source_deck is not None:
        # Re-render an existing deck, optionally with surgical edits applied.
        # Cheaper and far more predictable than regenerating to change a
        # number, and every untouched slide stays byte-identical.
        deck = (
            patch_mod.apply_patch(source_deck, patch)[0] if patch else source_deck
        )
    elif source_pptx:
        # Extracted images live under the output dir; they are inlined into
        # the HTML, so they are intermediates rather than deliverables.
        deck = pptx_import.pptx_to_deck(
            source_pptx, images_dir=out_dir / "images"
        )
    elif llm.llm_configured():
        deck = llm.generate_deck_structure(content, instructions)
    else:
        deck = deck_mod.markdown_to_deck(content)

    theme = _theme_for(template, templates_dir, specs_dir, brand_image)

    # Measure the rendered deck and repair anything that overflows the
    # canvas before writing it out (see fit.py). Deterministic, no model.
    if fit:
        deck, fit_report = fit_engine.fit_deck(deck, theme, chromium)
        (out_dir / "fit-report.json").write_text(json.dumps(fit_report, indent=2))

    (out_dir / "deck.json").write_text(json.dumps(deck, indent=2))

    outputs: dict[str, str] = {}
    if "html" in formats:
        html_path = out_dir / "deck.html"
        html_path.write_text(deck_render.render_deck_html(deck, theme))
        outputs["html"] = str(html_path)
    if "pdf" in formats:
        outputs["pdf"] = str(
            export.html_to_pdf(
                deck_render.render_deck_html(deck, theme, print_mode=True),
                out_dir / "deck.pdf",
                chromium,
                virtual_time_budget_ms=8000,
            )
        )
    return outputs


def generate_style_previews(
    title: str,
    subtitle: str | None = None,
    meta: str | None = None,
    themes: list[str] | None = None,
    templates_dir: str | Path = "templates",
    specs_dir: str | Path | None = None,
    out_dir: str | Path = "out",
    chromium: str = "/usr/bin/chromium",
) -> dict[str, str]:
    """Render one title-slide PNG per candidate theme. {theme: png_path}."""
    return preview.render_previews(
        title=title,
        subtitle=subtitle,
        meta=meta,
        themes=themes,
        templates_dir=templates_dir,
        specs_dir=specs_dir,
        out_dir=out_dir,
        chromium=chromium,
    )
