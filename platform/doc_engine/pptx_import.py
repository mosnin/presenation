"""Convert an existing .pptx into the deck model.

Lets someone bring a deck they already have and re-render it in any theme as
an interactive HTML deck (or a document). Text, bullet structure, tables,
speaker notes, and embedded images are preserved; precise positioning is not
— the point is to re-typeset the content in a coherent design system, not to
photocopy the original layout.

Requires python-pptx (and Pillow to downscale extracted images).
"""

from __future__ import annotations

from pathlib import Path

# python-pptx shape-type ids we care about (avoids importing the enum at
# module scope so the rest of doc_engine works without python-pptx).
_TABLE = 19
_PICTURE = 13
_PLACEHOLDER_TITLE_IDX = {0, 1}  # title / center-title placeholder idx values

# Images are inlined as data URIs to keep decks single-file, so they are
# downscaled first — a 4000px photo would otherwise add megabytes of base64.
MAX_IMAGE_WIDTH = 1600
MIN_USEFUL_IMAGE_PX = 80  # skip bullets, logos, and spacer graphics


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


def _is_picture(shape) -> bool:
    if getattr(shape, "shape_type", None) == _PICTURE:
        return True
    return hasattr(shape, "image")


def _extract_image(shape, out_dir: Path, index: int) -> str | None:
    """Save one picture shape, downscaled. Returns the path, or None when the
    image is too small to be worth carrying (icons, bullets, spacers)."""
    try:
        image = shape.image
        blob = image.blob
        ext = (image.ext or "png").lower()
    except (AttributeError, ValueError):
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / f"image-{index}.{ext}"
    raw_path.write_bytes(blob)

    try:
        from PIL import Image

        with Image.open(raw_path) as img:
            width, height = img.size
            if width < MIN_USEFUL_IMAGE_PX or height < MIN_USEFUL_IMAGE_PX:
                raw_path.unlink(missing_ok=True)
                return None
            if width > MAX_IMAGE_WIDTH:
                ratio = MAX_IMAGE_WIDTH / width
                img = img.resize(
                    (MAX_IMAGE_WIDTH, int(height * ratio)), Image.LANCZOS
                )
            if img.mode in ("P", "RGBA", "LA"):
                img = img.convert("RGBA" if "A" in img.mode else "RGB")
            save_path = out_dir / f"image-{index}.png"
            img.save(save_path, "PNG", optimize=True)
        if save_path != raw_path:
            raw_path.unlink(missing_ok=True)
        return str(save_path)
    except (ImportError, OSError):
        # No Pillow, or an image format it can't read: keep the original.
        return str(raw_path)


def _notes(slide) -> str | None:
    try:
        if slide.has_notes_slide:
            text = slide.notes_slide.notes_text_frame.text.strip()
            return text or None
    except (AttributeError, ValueError):
        pass
    return None


def pptx_to_deck(
    path: str | Path,
    keep_notes: bool = True,
    keep_images: bool = True,
    images_dir: str | Path | None = None,
) -> dict:
    """Parse a .pptx into the deck structure used by deck_render."""
    from pptx import Presentation

    prs = Presentation(str(path))
    slides: list[dict] = []
    deck_title: str | None = None
    deck_subtitle: str | None = None
    image_dir = Path(images_dir) if images_dir else Path(path).parent / "images"
    image_count = 0

    for index, slide in enumerate(prs.slides):
        title: str | None = None
        body_lines: list[str] = []
        tables: list[dict] = []
        images: list[str] = []

        for shape in slide.shapes:
            if getattr(shape, "shape_type", None) == _TABLE or getattr(
                shape, "has_table", False
            ):
                block = _table_block(shape)
                if block:
                    tables.append(block)
                continue
            if keep_images and _is_picture(shape):
                saved = _extract_image(shape, image_dir, image_count)
                if saved:
                    images.append(saved)
                    image_count += 1
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
        # The first image pairs with this slide's text; any others become
        # their own image slides rather than being crammed in.
        lead_image = images[0] if images else None
        extra_images = images[1:]

        if body_lines:
            # Long single blocks read better as prose than as one giant
            # bullet; short lines are almost always bullets.
            long_lines = [line for line in body_lines if len(line) > 160]
            if lead_image:
                slides.append(
                    {
                        "layout": "image_text",
                        "heading": heading,
                        "image": lead_image,
                        "items": body_lines[:5],
                        **({"notes": notes} if notes else {}),
                    }
                )
                body_lines = body_lines[5:]
            if long_lines and len(body_lines) <= 3 and body_lines:
                slides.append(
                    {
                        "layout": "prose",
                        "heading": heading,
                        "paragraphs": body_lines,
                        **({"notes": notes and not lead_image} if notes else {}),
                    }
                )
            elif body_lines:
                for start in range(0, len(body_lines), 6):
                    slides.append(
                        {
                            "layout": "bullets",
                            "heading": heading,
                            "items": body_lines[start : start + 6],
                            **(
                                {"notes": notes}
                                if notes and start == 0 and not lead_image
                                else {}
                            ),
                        }
                    )
        elif lead_image:
            slides.append(
                {
                    "layout": "image",
                    "heading": heading,
                    "image": lead_image,
                    **({"notes": notes} if notes else {}),
                }
            )
        elif not tables:
            slides.append({"layout": "section", "kicker": f"{index:02d}", "heading": heading})

        for image in extra_images:
            slides.append({"layout": "image", "heading": heading, "image": image})

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
