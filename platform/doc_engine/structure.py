"""Document structure model and a deterministic markdown fallback parser.

A document is a plain dict:

    {
      "title": str,
      "subtitle": str | None,
      "meta": str | None,           # e.g. author / date line on the cover
      "sections": [
        {
          "heading": str,
          "blocks": [
            {"type": "paragraph", "text": str},
            {"type": "bullets", "items": [str, ...]},
            {"type": "quote", "text": str},
            {"type": "stats", "items": [{"value": str, "label": str}, ...]},
            {"type": "table", "header": [str], "rows": [[str, ...], ...]},
          ]
        }
      ]
    }
"""

from __future__ import annotations

import re


def parse_markdown(content: str) -> dict:
    """Turn markdown-ish text into a document structure without an LLM.

    Used when the caller supplies already-written content, and as a fallback
    when no LLM is configured.
    """
    lines = content.splitlines()
    doc: dict = {"title": None, "subtitle": None, "meta": None, "sections": []}
    section: dict | None = None
    paragraph: list[str] = []
    bullets: list[str] = []
    table: list[list[str]] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph and section is not None:
            section["blocks"].append(
                {"type": "paragraph", "text": " ".join(paragraph).strip()}
            )
        paragraph = []

    def flush_bullets() -> None:
        nonlocal bullets
        if bullets and section is not None:
            section["blocks"].append({"type": "bullets", "items": bullets})
        bullets = []

    def flush_table() -> None:
        nonlocal table
        if table and section is not None:
            header, *rows = table
            section["blocks"].append(
                {"type": "table", "header": header, "rows": rows}
            )
        table = []

    def flush_all() -> None:
        flush_paragraph()
        flush_bullets()
        flush_table()

    def ensure_section(heading: str = "Overview") -> dict:
        nonlocal section
        if section is None:
            section = {"heading": heading, "blocks": []}
            doc["sections"].append(section)
        return section

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_all()
            continue
        if stripped.startswith("# "):
            flush_all()
            if doc["title"] is None:
                doc["title"] = stripped[2:].strip()
            else:
                section = {"heading": stripped[2:].strip(), "blocks": []}
                doc["sections"].append(section)
            continue
        if stripped.startswith("## "):
            flush_all()
            section = {"heading": stripped[3:].strip(), "blocks": []}
            doc["sections"].append(section)
            continue
        if stripped.startswith("> "):
            flush_all()
            ensure_section()
            section["blocks"].append({"type": "quote", "text": stripped[2:].strip()})
            continue
        if re.match(r"^[-*] ", stripped):
            flush_paragraph()
            flush_table()
            ensure_section()
            bullets.append(stripped[2:].strip())
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            flush_paragraph()
            flush_bullets()
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                continue  # separator row
            ensure_section()
            table.append(cells)
            continue
        if doc["title"] is None:
            doc["title"] = stripped
            continue
        if doc["subtitle"] is None and not doc["sections"]:
            doc["subtitle"] = stripped
            continue
        if doc["meta"] is None and not doc["sections"]:
            doc["meta"] = stripped
            continue
        ensure_section()
        paragraph.append(stripped)

    flush_all()
    if doc["title"] is None:
        doc["title"] = "Untitled document"
    return doc


DOCUMENT_JSON_SPEC = """
Return ONLY a JSON object with this shape (no markdown fences):
{
  "title": "...", "subtitle": "...", "meta": "...",
  "sections": [
    {"heading": "...", "blocks": [
      {"type": "paragraph", "text": "..."},
      {"type": "bullets", "items": ["..."]},
      {"type": "quote", "text": "..."},
      {"type": "stats", "items": [{"value": "42%", "label": "..."}]},
      {"type": "table", "header": ["..."], "rows": [["..."]]}
    ]}
  ]
}
Use "stats" blocks for headline figures, tables for comparisons, and keep
paragraphs to 2-4 sentences. 3-6 sections total unless asked otherwise.
"""
