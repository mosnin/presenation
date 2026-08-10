"""Deck model for interactive HTML presentations.

A deck is a plain dict:

    {
      "title": str, "subtitle": str | None, "meta": str | None,
      "slides": [
        {"layout": "title", "title": str, "subtitle": str?, "meta": str?},
        {"layout": "section", "kicker": "01", "heading": str},
        {"layout": "bullets", "heading": str, "items": [str]},
        {"layout": "prose", "heading": str, "paragraphs": [str]},
        {"layout": "stats", "heading": str,
         "items": [{"value": str, "label": str}]},
        {"layout": "quote", "text": str, "attribution": str?},
        {"layout": "table", "heading": str, "header": [str], "rows": [[str]]},
        {"layout": "closing", "heading": str, "subheading": str?},
      ]
    }
"""

from __future__ import annotations

from .structure import parse_markdown


def doc_to_deck(doc: dict) -> dict:
    """Map a document structure (structure.py) onto deck slides."""
    slides: list[dict] = [
        {
            "layout": "title",
            "title": doc.get("title") or "Untitled",
            "subtitle": doc.get("subtitle"),
            "meta": doc.get("meta"),
        }
    ]
    sections = doc.get("sections", [])
    for index, section in enumerate(sections, start=1):
        heading = section.get("heading", "")
        blocks = section.get("blocks", [])
        if len(sections) > 3:
            slides.append(
                {"layout": "section", "kicker": f"{index:02d}", "heading": heading}
            )
        paragraphs: list[str] = []
        for block in blocks:
            kind = block.get("type")
            if kind == "paragraph":
                paragraphs.append(block.get("text", ""))
                continue
            if paragraphs:
                slides.append(
                    {"layout": "prose", "heading": heading, "paragraphs": paragraphs}
                )
                paragraphs = []
            if kind == "bullets":
                items = block.get("items", [])
                for start in range(0, len(items), 6):
                    slides.append(
                        {
                            "layout": "bullets",
                            "heading": heading,
                            "items": items[start : start + 6],
                        }
                    )
            elif kind == "stats":
                slides.append(
                    {
                        "layout": "stats",
                        "heading": heading,
                        "items": block.get("items", [])[:4],
                    }
                )
            elif kind == "quote":
                slides.append(
                    {
                        "layout": "quote",
                        "text": block.get("text", ""),
                        "attribution": block.get("attribution"),
                    }
                )
            elif kind == "table":
                slides.append(
                    {
                        "layout": "table",
                        "heading": heading,
                        "header": block.get("header", []),
                        "rows": block.get("rows", []),
                    }
                )
        if paragraphs:
            slides.append(
                {"layout": "prose", "heading": heading, "paragraphs": paragraphs}
            )
    slides.append(
        {
            "layout": "closing",
            "heading": "Thank you",
            "subheading": doc.get("title"),
        }
    )
    return {
        "title": doc.get("title") or "Untitled",
        "subtitle": doc.get("subtitle"),
        "meta": doc.get("meta"),
        "slides": slides,
    }


def markdown_to_deck(content: str) -> dict:
    return doc_to_deck(parse_markdown(content))


DECK_JSON_SPEC = """
Return ONLY a JSON object (no markdown fences) shaped:
{
  "title": "...", "subtitle": "...", "meta": "...",
  "slides": [
    {"layout": "title", "title": "...", "subtitle": "...", "meta": "..."},
    {"layout": "section", "kicker": "01", "heading": "..."},
    {"layout": "bullets", "heading": "...", "items": ["..."]},
    {"layout": "prose", "heading": "...", "paragraphs": ["..."]},
    {"layout": "stats", "heading": "...",
     "items": [{"value": "42%", "label": "..."}]},
    {"layout": "quote", "text": "...", "attribution": "..."},
    {"layout": "table", "heading": "...", "header": ["..."], "rows": [["..."]]},
    {"layout": "closing", "heading": "...", "subheading": "..."}
  ]
}
Slide rules: start with one title slide, end with one closing slide. One idea
per slide. Max 6 bullets, 4 stats, 5 table rows per slide — split instead of
cramming. Use section slides as chapter dividers when there are 4+ topics.
Prefer stats layouts for headline figures and quote layouts for key claims.
"""
