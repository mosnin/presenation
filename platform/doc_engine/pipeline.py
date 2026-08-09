"""End-to-end document generation pipeline."""

from __future__ import annotations

from pathlib import Path

from . import export, llm, render, structure
from .theme import load_theme


def generate_document(
    content: str,
    instructions: str | None = None,
    template: str = "general",
    formats: list[str] | None = None,
    templates_dir: str | Path = "templates",
    out_dir: str | Path = "out",
    chromium: str = "/usr/bin/chromium",
) -> dict[str, str]:
    """Generate a document in the aesthetic of a Presenton slide template.

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

    theme = load_theme(templates_dir, template)
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
