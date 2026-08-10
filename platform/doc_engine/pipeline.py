"""End-to-end generation pipelines: documents (PDF/DOCX/HTML pages) and
interactive HTML decks, both themed by slide templates or design specs."""

from __future__ import annotations

import json
from pathlib import Path

from . import deck as deck_mod
from . import deck_render, export, llm, render, structure
from .theme import resolve_theme


def generate_document(
    content: str,
    instructions: str | None = None,
    template: str = "general",
    formats: list[str] | None = None,
    templates_dir: str | Path = "templates",
    out_dir: str | Path = "out",
    chromium: str = "/usr/bin/chromium",
    specs_dir: str | Path | None = None,
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

    theme = resolve_theme(template, templates_dir=templates_dir, specs_dir=specs_dir)
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
) -> dict[str, str]:
    """Generate a self-contained interactive HTML presentation.

    Returns {"html": output_path}. With an LLM configured the content is
    expanded slide by slide; otherwise markdown maps deterministically onto
    slide layouts (see deck.py).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if llm.llm_configured():
        deck = llm.generate_deck_structure(content, instructions)
    else:
        deck = deck_mod.markdown_to_deck(content)

    theme = resolve_theme(template, templates_dir=templates_dir, specs_dir=specs_dir)
    html_text = deck_render.render_deck_html(deck, theme)

    out_path = out_dir / "deck.html"
    out_path.write_text(html_text)
    (out_dir / "deck.json").write_text(json.dumps(deck, indent=2))
    return {"html": str(out_path)}
