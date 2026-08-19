"""Speaker cues and timing, so a deck is something you can walk in with.

A generated deck is only half the deliverable. The person presenting it still
has to work out what to say over each slide and whether the whole thing fits
the slot they were given — which is exactly the part an agent could hand over
and currently doesn't.

This derives per-slide cues and a duration estimate from the deck model
itself, with no model call. The cues are deliberately framed as prompts
rather than a script to read aloud: a deterministic pass cannot know the
argument being made, and pretending otherwise produces confident nonsense.
What you get is honest scaffolding plus a timing budget.

Generating real narration would need an LLM pass over the deck (the hook
would sit alongside llm.generate_deck_structure); that is not implemented
here.
"""

from __future__ import annotations

# Conversational presenting pace. Slower than reading aloud (~150) because
# speakers pause, gesture, and answer the odd question.
WORDS_PER_MINUTE = 130

# Every slide costs something even when nearly empty: the transition, the
# beat before speaking, the audience's eyes moving.
BASE_SECONDS_PER_SLIDE = 8.0
MIN_SECONDS_PER_SLIDE = 12.0


def _words_on(slide: dict) -> int:
    parts: list[str] = []
    for field in ("title", "subtitle", "meta", "heading", "text", "subheading"):
        value = slide.get(field)
        if isinstance(value, str):
            parts.append(value)
    for field in ("items", "paragraphs"):
        for item in slide.get(field) or []:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):  # stat cards
                parts.append(f"{item.get('value', '')} {item.get('label', '')}")
    for row in slide.get("rows") or []:
        parts.extend(str(cell) for cell in row)
    return sum(len(part.split()) for part in parts)


def estimate_seconds(slide: dict) -> float:
    """How long this slide plausibly takes to present."""
    spoken = _words_on(slide) * (60.0 / WORDS_PER_MINUTE)
    # Talking over a slide takes longer than reading it: the words on screen
    # are prompts for a fuller spoken version.
    return max(MIN_SECONDS_PER_SLIDE, BASE_SECONDS_PER_SLIDE + spoken * 1.6)


def _join(items: list[str], limit: int = 3) -> str:
    shown = [str(item).rstrip(".") for item in items[:limit]]
    if len(items) > limit:
        shown.append(f"and {len(items) - limit} more")
    return "; ".join(shown)


def cue_for(slide: dict) -> str:
    """A prompt for what to say over this slide. Not a script."""
    layout = slide.get("layout")

    if layout == "title":
        title = slide.get("title") or "the deck"
        return (
            f"Open on {title}. Say who you are and why this matters to this "
            "room before moving on."
        )
    if layout == "section":
        return (
            f"Transition into {slide.get('heading') or 'the next section'}. "
            "One sentence on why it follows from what came before."
        )
    if layout == "bullets":
        items = slide.get("items") or []
        return (
            f"Walk through {len(items)} point"
            f"{'s' if len(items) != 1 else ''}: {_join(items)}. "
            "Expand the one that matters most and keep the rest brief."
        )
    if layout == "prose":
        paragraphs = slide.get("paragraphs") or []
        opener = (paragraphs[0].split(".")[0] if paragraphs else "").strip()
        return (
            f"Make the point: {opener}. "
            "Do not read the slide — the audience is already reading it."
        )
    if layout == "stats":
        items = slide.get("items") or []
        figures = ", ".join(
            f"{item.get('value')} {item.get('label')}" for item in items[:4]
        )
        return (
            f"Land the numbers: {figures}. "
            "Give one of them a comparison so it means something."
        )
    if layout == "quote":
        who = slide.get("attribution")
        return (
            "Read the quote, then pause and let it land"
            + (f" — it is from {who}." if who else ".")
        )
    if layout == "table":
        rows = slide.get("rows") or []
        return (
            f"Take the table one row at a time ({len(rows)} rows). "
            "Point out the row that changes the decision."
        )
    if layout == "image":
        return (
            f"Let the image do the work for a beat, then say what "
            f"{slide.get('heading') or 'it'} shows."
        )
    if layout == "image_text":
        return (
            "Talk to the points on the left, referring to the image on the "
            "right rather than describing it."
        )
    if layout == "closing":
        return "Close on the ask, then stop talking and take questions."
    return "Speak to this slide."


def narrate_deck(deck: dict, overwrite: bool = False) -> dict:
    """Attach `notes` and `seconds` to every slide, plus a deck total.

    Existing notes — from a PowerPoint import or a previous pass — are kept
    unless overwrite is set: someone's real speaker notes beat a generated
    cue every time.
    """
    slides = []
    total = 0.0
    for slide in deck.get("slides", []):
        seconds = estimate_seconds(slide)
        total += seconds
        entry = {**slide, "seconds": round(seconds)}
        if overwrite or not entry.get("notes"):
            entry["notes"] = cue_for(slide)
        slides.append(entry)
    return {**deck, "slides": slides, "seconds": round(total)}


def format_duration(seconds: float) -> str:
    minutes, remainder = divmod(int(round(seconds)), 60)
    return f"{minutes}:{remainder:02d}"


def to_script(deck: dict) -> str:
    """A speaker script: one section per slide, with a running clock."""
    narrated = deck if "seconds" in deck else narrate_deck(deck)
    lines = [
        f"# {narrated.get('title') or 'Deck'} — speaker script",
        "",
        f"{len(narrated['slides'])} slides · "
        f"about {format_duration(narrated['seconds'])} at "
        f"{WORDS_PER_MINUTE} words per minute.",
        "",
        "Timings are estimates from the words on each slide — treat them as a",
        "budget, not a plan.",
        "",
    ]
    elapsed = 0.0
    for index, slide in enumerate(narrated["slides"], start=1):
        label = (
            slide.get("heading")
            or slide.get("title")
            or slide.get("text", "")[:40]
            or slide["layout"]
        )
        lines.append(f"## {index}. {label}")
        lines.append("")
        lines.append(
            f"*{slide['layout']} · {slide['seconds']}s · "
            f"at {format_duration(elapsed)}*"
        )
        lines.append("")
        lines.append(slide.get("notes", ""))
        lines.append("")
        elapsed += slide["seconds"]
    return "\n".join(lines)
