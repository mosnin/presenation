"""Surgical edits to a deck, so agents don't regenerate to change one number.

Today the only way to fix "slide 4 says 41%, it should say 43%" is to
regenerate the whole deck — a new model call, a new layout, and every other
slide silently different. That is the wrong shape for an agent loop, where
the natural motion is: produce a draft, get feedback, apply it.

A deck is already a plain JSON document (`deck.json` ships with every deck
job), so it can be edited directly. This module defines a small operation
set over that document and applies it deterministically, with errors that
name what went wrong rather than raising an IndexError from somewhere deep.

Operations (each is a dict with an "op" key):

    {"op": "set", "slide": 3, "field": "heading", "value": "New heading"}
    {"op": "set", "slide": 3, "field": "items", "value": ["a", "b"]}
    {"op": "set_item", "slide": 3, "index": 1, "value": "replacement bullet"}
    {"op": "replace", "slide": 3, "value": {...whole slide...}}
    {"op": "insert", "index": 4, "value": {...whole slide...}}
    {"op": "delete", "slide": 4}
    {"op": "move", "from": 4, "to": 1}
    {"op": "set_meta", "field": "title", "value": "Deck title"}

Slide indexes are 0-based and refer to the deck *as it was when the patch
started* for `set`/`replace`/`delete`/`move`, which makes a batch of edits
predictable — an agent can write them from one reading of deck.json without
tracking how earlier ops shifted the list.
"""

from __future__ import annotations

from copy import deepcopy

# Fields an agent may write. Anything else is rejected: a typo like
# "headding" should fail loudly, not silently add a field nothing renders.
EDITABLE_SLIDE_FIELDS = {
    "layout",
    "title",
    "subtitle",
    "meta",
    "heading",
    "kicker",
    "items",
    "paragraphs",
    "text",
    "attribution",
    "header",
    "rows",
    "image",
    "notes",
    "density",
    "subheading",
}

EDITABLE_DECK_FIELDS = {"title", "subtitle", "meta"}

LIST_FIELDS = {"items", "paragraphs", "rows", "header"}

VALID_LAYOUTS = {
    "title",
    "section",
    "bullets",
    "prose",
    "stats",
    "quote",
    "table",
    "closing",
    "image",
    "image_text",
}


class PatchError(ValueError):
    """A patch operation that cannot be applied, described in plain terms."""


def _check_index(index, count: int, label: str) -> int:
    if not isinstance(index, int) or isinstance(index, bool):
        raise PatchError(f"{label} must be an integer, got {index!r}")
    if index < 0 or index >= count:
        raise PatchError(
            f"{label} {index} is out of range: the deck has {count} slides "
            f"(valid 0-{count - 1})"
        )
    return index


def _check_slide(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise PatchError(f"{label} must be a slide object")
    layout = value.get("layout")
    if layout not in VALID_LAYOUTS:
        raise PatchError(
            f"{label} has layout {layout!r}; expected one of "
            f"{', '.join(sorted(VALID_LAYOUTS))}"
        )
    return value


def apply_patch(deck: dict, operations: list[dict]) -> tuple[dict, list[str]]:
    """Apply operations to a deck. Returns (new_deck, summaries).

    The input deck is not modified. Any failing operation raises PatchError
    and nothing is applied — a half-applied patch would be worse than a
    rejected one.
    """
    if not isinstance(operations, list) or not operations:
        raise PatchError("patch must be a non-empty list of operations")

    working = deepcopy(deck)
    slides = working.setdefault("slides", [])
    original_count = len(slides)

    # Resolve every index against the deck as the caller saw it, then apply
    # structural changes in an order that keeps those indexes meaningful.
    summaries: list[str] = []
    inserts: list[tuple[int, dict]] = []
    deletions: set[int] = set()
    moves: list[tuple[int, int]] = []

    for position, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise PatchError(f"operation {position} is not an object")
        op = operation.get("op")

        if op == "set":
            index = _check_index(operation.get("slide"), original_count, "slide")
            field = operation.get("field")
            if field not in EDITABLE_SLIDE_FIELDS:
                raise PatchError(
                    f"field {field!r} is not editable; allowed: "
                    f"{', '.join(sorted(EDITABLE_SLIDE_FIELDS))}"
                )
            value = operation.get("value")
            if field in LIST_FIELDS and not isinstance(value, list):
                raise PatchError(f"field {field!r} expects a list")
            if field == "layout" and value not in VALID_LAYOUTS:
                raise PatchError(f"layout {value!r} is not a known layout")
            slides[index][field] = value
            summaries.append(f"set slide {index}.{field}")

        elif op == "set_item":
            index = _check_index(operation.get("slide"), original_count, "slide")
            slide = slides[index]
            field = next((f for f in ("items", "paragraphs") if f in slide), None)
            if field is None:
                raise PatchError(
                    f"slide {index} ({slide.get('layout')}) has no list of items"
                )
            item_index = _check_index(
                operation.get("index"), len(slide[field]), "index"
            )
            slide[field][item_index] = operation.get("value")
            summaries.append(f"set slide {index}.{field}[{item_index}]")

        elif op == "replace":
            index = _check_index(operation.get("slide"), original_count, "slide")
            slides[index] = _check_slide(operation.get("value"), "value")
            summaries.append(f"replaced slide {index}")

        elif op == "insert":
            index = operation.get("index")
            if not isinstance(index, int) or isinstance(index, bool):
                raise PatchError("insert index must be an integer")
            if index < 0 or index > original_count:
                raise PatchError(
                    f"insert index {index} is out of range (0-{original_count})"
                )
            inserts.append((index, _check_slide(operation.get("value"), "value")))
            summaries.append(f"inserted a slide at {index}")

        elif op == "delete":
            index = _check_index(operation.get("slide"), original_count, "slide")
            deletions.add(index)
            summaries.append(f"deleted slide {index}")

        elif op == "move":
            source = _check_index(operation.get("from"), original_count, "from")
            target = _check_index(operation.get("to"), original_count, "to")
            moves.append((source, target))
            summaries.append(f"moved slide {source} to {target}")

        elif op == "set_meta":
            field = operation.get("field")
            if field not in EDITABLE_DECK_FIELDS:
                raise PatchError(
                    f"deck field {field!r} is not editable; allowed: "
                    f"{', '.join(sorted(EDITABLE_DECK_FIELDS))}"
                )
            working[field] = operation.get("value")
            summaries.append(f"set deck {field}")

        else:
            raise PatchError(
                f"unknown op {op!r}; expected set, set_item, replace, insert, "
                "delete, move, or set_meta"
            )

    # Structural ops are resolved against slide *identity*, not position, so
    # a batch behaves the way the caller wrote it: "insert at 3, delete 2"
    # puts the new slide before the original slide 3 regardless of the
    # deletion, instead of the two ops shifting each other around.
    tagged: list[tuple[int, dict]] = list(enumerate(slides))

    for source, target in moves:
        entry = next(e for e in tagged if e[0] == source)
        tagged.remove(entry)
        tagged.insert(min(target, len(tagged)), entry)

    if deletions:
        if len(deletions) >= original_count:
            raise PatchError("a patch cannot delete every slide")
        tagged = [entry for entry in tagged if entry[0] not in deletions]

    for anchor, slide in inserts:
        # Insert before the slide that had this index; if it was deleted or
        # moved away, fall back to the next surviving slide, then the end.
        position = next(
            (i for i, (original, _) in enumerate(tagged) if original >= anchor),
            len(tagged),
        )
        tagged.insert(position, (-1, slide))

    working["slides"] = [slide for _, slide in tagged]
    return working, summaries
