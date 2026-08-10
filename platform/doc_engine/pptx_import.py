"""Convert an existing .pptx into the deck model.

Lets someone bring a deck they already have and re-render it in any theme as
an interactive HTML deck (or a document). Text, bullet structure, tables, and
speaker notes are preserved; original images and precise positioning are not
— the point is to re-typeset the content in a coherent design system, not to
photocopy the original layout.

Requires python-pptx.
"""

from __future__ import annotations

from pathlib import Path

# python-pptx shape-type ids we care about (avoids importing the enum at
# module scope so the rest of doc_engine works without python-pptx).
_TABLE = 19
_PLACEHOLDER_TITLE_IDX = {0, 1}  # title / center-title placeholder idx values


def _shape_text_lines(shape) -> list[str]:
    if not getattr(shape, "has_text_frame", False):
        return []
    lines = []
    for para in shape.text_frame.paragraphs:
        text = "".join(run.text for run in para.runs).strip()
        if text:
            lines.append(text)
    return lines


def _is_title(shape) -> bool:
    try:
        if shape.is_placeholder:
            return shape.placeholder_format.idx in _PLACEHOLDER_TITLE_IDX or (
                shape.placeholder_format.type is not None
                and "TITLE" in str(shape.placeholder_format.type)
            )
    except (AttributeError, ValueError):
        pass
    return False


def _table_block(shape) -> dict | None:
    table = shape.table
    rows = [
        [cell.text.strip() for cell in row.cells] for row in table.rows
    ]
    if not rows:
        return None
    header, *body = rows
    return {"header": header, "rows": body[:5]}


def _notes(slide) -> str | None:
    try:
        if slide.has_notes_slide:
            text = slide.notes_slide.notes_text_frame.text.strip()
            return text or None
    except (AttributeError, ValueError):
        pass
    return None


def pptx_to_deck(path: str | Path, keep_notes: bool = True) -> dict:
    """Parse a .pptx into the deck structure used by deck_render."""
    from pptx import Presentation

    prs = Presentation(str(path))
    slides: list[dict] = []
    deck_title: str | None = None
    deck_subtitle: str | None = None

    for index, slide in enumerate(prs.slides):
        title: str | None = None
        body_lines: list[str] = []
        tables: list[dict] = []

        for shape in slide.shapes:
            if getattr(shape, "shape_type", None) == _TABLE or getattr(
                shape, "has_table", False
            ):
                block = _table_block(shape)
                if block:
                    tables.append(block)
                continue
            lines = _shape_text_lines(shape)
            if not lines:
                continue
            if title is None and _is_title(shape):
                title = lines[0]
                body_lines.extend(lines[1:])
            else:
                body_lines.extend(lines)

        # No explicit title placeholder: treat the first line as the heading.
        if title is None and body_lines:
            title = body_lines.pop(0)
        heading = title or f"Slide {index + 1}"

        if index == 0:
            deck_title = heading
            deck_subtitle = body_lines[0] if body_lines else None
            slides.append(
                {
                    "layout": "title",
                    "title": heading,
                    "subtitle": deck_subtitle,
                    "meta": body_lines[1] if len(body_lines) > 1 else None,
                }
            )
            continue

        notes = _notes(slide) if keep_notes else None

        if body_lines:
            # Long single blocks read better as prose than as one giant
            # bullet; short lines are almost always bullets.
            long_lines = [line for line in body_lines if len(line) > 160]
            if long_lines and len(body_lines) <= 3:
                slides.append(
                    {
                        "layout": "prose",
                        "heading": heading,
                        "paragraphs": body_lines,
                        **({"notes": notes} if notes else {}),
                    }
                )
            else:
                for start in range(0, len(body_lines), 6):
                    slides.append(
                        {
                            "layout": "bullets",
                            "heading": heading,
                            "items": body_lines[start : start + 6],
                            **(
                                {"notes": notes}
                                if notes and start == 0
                                else {}
                            ),
                        }
                    )
        elif not tables:
            slides.append({"layout": "section", "kicker": f"{index:02d}", "heading": heading})

        for table in tables:
            slides.append(
                {
                    "layout": "table",
                    "heading": heading,
                    "header": table["header"],
                    "rows": table["rows"],
                }
            )

    if not slides:
        raise ValueError(f"{path}: no readable slides found")

    return {
        "title": deck_title or Path(path).stem,
        "subtitle": deck_subtitle,
        "slides": slides,
    }
