"""Route content to the layout it deserves.

Everything arriving as prose becomes bullets, which is exactly why generated
decks read as templated: four headline numbers, a customer quote, and a
project timeline all get the same grey list treatment. The information was
there — the shape was thrown away.

This recovers the shape before rendering. Bullet lists that are really
figures become stat cards; a quotation with an attribution keeps its
attribution; a run of dated milestones becomes a timeline table. No model
call: these are patterns with high enough precision to detect outright.

Everything here is deliberately conservative. A false positive — three
ordinary sentences forced into stat cards — looks far worse than a missed
conversion, so each rule demands that *every* item in a group match, not a
majority.
"""

from __future__ import annotations

import re

# A headline figure: currency, percentage, multiplier, or a grouped number,
# optionally with a magnitude suffix. Deliberately not "any digit" — "we
# opened 2 depots" is a sentence, not a statistic.
FIGURE = r"(?:[$£€]\s?\d[\d,.]*\s?[KMB]?\b|\d[\d,.]*\s?%|\d[\d,.]*\s?x\b|\d{1,3}(?:,\d{3})+\b|\d+\.\d+\b)"

_FIGURE_RE = re.compile(FIGURE, re.IGNORECASE)

# "Label: $4.2M" / "Label — 18%"
_LABELLED_RE = re.compile(rf"^(?P<label>[^:—–]{{2,48}})\s*[:—–]\s*(?P<value>.{{1,24}})$")

# A value in the labelled form may be a bare number ("NPS: 61"): the label
# and separator already establish that this is a measurement, so the figure
# itself needn't be decorated with a currency or percent sign.
_BARE_VALUE_RE = re.compile(r"^[$£€]?\d[\d,.]*\s*(?:[%x]|[KMB]\b|\+)?$", re.IGNORECASE)

# "$4.2M revenue" / "18% growth"
_LEADING_FIGURE_RE = re.compile(rf"^(?P<value>{FIGURE})\s+(?P<label>.{{2,44}})$", re.I)

# "— Someone, Title" or "- Someone" at the end of a quotation
_ATTRIBUTION_RE = re.compile(r"\s*[—–-]{1,2}\s*([A-Z][^\n]{2,60})$")

# Dates a timeline row can start with: Q1 2026, 2026, Jan 2026, January 2026,
# 2026-03, 03/2026.
_DATE_PREFIX_RE = re.compile(
    r"^(?P<date>"
    r"Q[1-4]\s*(?:FY)?\s*'?\d{2,4}"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}"
    r"|\d{4}-\d{2}(?:-\d{2})?"
    r"|\d{1,2}/\d{4}"
    r"|(?:19|20)\d{2}"
    r")\s*[:—–-]?\s+(?P<rest>.+)$",
    re.IGNORECASE,
)

MAX_STAT_CARDS = 4
MIN_STAT_CARDS = 2
MIN_TIMELINE_ROWS = 3
MAX_STAT_ITEM_CHARS = 60

# Connectives left dangling when a figure is lifted out of a sentence:
# "Revenue grew to $4.2M" would otherwise label the card "Revenue grew to".
_TRIM_WORDS = {
    "a", "an", "and", "at", "by", "for", "from", "in", "of", "on", "the",
    "to", "was", "were", "is", "are", "with", "over", "up", "down",
}


def _tidy_label(label: str) -> str:
    words = label.strip(" ,:—–-").split()
    while words and words[0].lower() in _TRIM_WORDS:
        words.pop(0)
    while words and words[-1].lower() in _TRIM_WORDS:
        words.pop()
    return " ".join(words)


def _as_stat(item: str) -> dict | None:
    """Parse one bullet into {value, label}, or None if it isn't a figure."""
    text = item.strip().rstrip(".")
    if len(text) > MAX_STAT_ITEM_CHARS:
        return None
    if not _FIGURE_RE.search(text) and not re.search(r"\d", text):
        return None

    match = _LABELLED_RE.match(text)
    if match and (
        _FIGURE_RE.search(match.group("value"))
        or _BARE_VALUE_RE.match(match.group("value").strip())
    ):
        return {
            "value": match.group("value").strip(),
            "label": _tidy_label(match.group("label")),
        }

    match = _LEADING_FIGURE_RE.match(text)
    if match:
        return {
            "value": match.group("value").strip(),
            "label": _tidy_label(match.group("label")),
        }

    # "Revenue grew to $4.2M" — figure at the end, label before it.
    figures = list(_FIGURE_RE.finditer(text))
    if len(figures) == 1:
        figure = figures[0]
        label = _tidy_label(text[: figure.start()] + text[figure.end() :])
        if 2 <= len(label) <= 44:
            return {"value": figure.group(0).strip(), "label": label}
    return None


def extract_stats(items: list[str]) -> list[dict] | None:
    """A bullet list that is really a row of figures, or None."""
    if not (MIN_STAT_CARDS <= len(items) <= MAX_STAT_CARDS):
        return None
    stats = [_as_stat(item) for item in items]
    # Every item must be a figure: a mixed list is a list.
    if any(stat is None for stat in stats):
        return None
    return stats  # type: ignore[return-value]


def extract_timeline(items: list[str]) -> tuple[list[str], list[list[str]]] | None:
    """A run of dated milestones, as (header, rows), or None."""
    if len(items) < MIN_TIMELINE_ROWS:
        return None
    rows = []
    for item in items:
        match = _DATE_PREFIX_RE.match(item.strip())
        if not match:
            return None
        rows.append([match.group("date").strip(), match.group("rest").strip()])
    return ["When", "What"], rows


def split_attribution(text: str) -> tuple[str, str | None]:
    """Separate a trailing attribution from a quotation."""
    body = text.strip().strip('"“”')
    match = _ATTRIBUTION_RE.search(body)
    if not match:
        return body, None
    attribution = match.group(1).strip()
    # A trailing clause is not an attribution; names are short and start
    # with a capital.
    if len(attribution.split()) > 8:
        return body, None
    quoted = body[: match.start()].strip().rstrip(",").strip()
    return quoted.strip('"“”').strip(), attribution


def enrich_blocks(blocks: list[dict]) -> list[dict]:
    """Rewrite a document section's blocks into their true shapes."""
    out: list[dict] = []
    for block in blocks:
        kind = block.get("type")

        if kind == "bullets":
            items = [str(item) for item in block.get("items", [])]
            stats = extract_stats(items)
            if stats:
                out.append({"type": "stats", "items": stats})
                continue
            timeline = extract_timeline(items)
            if timeline:
                header, rows = timeline
                out.append({"type": "table", "header": header, "rows": rows})
                continue

        elif kind == "quote" and not block.get("attribution"):
            text, attribution = split_attribution(str(block.get("text", "")))
            block = {**block, "text": text}
            if attribution:
                block["attribution"] = attribution

        out.append(block)
    return out


def enrich_document(doc: dict) -> dict:
    """Apply inference across every section of a parsed document."""
    return {
        **doc,
        "sections": [
            {**section, "blocks": enrich_blocks(section.get("blocks", []))}
            for section in doc.get("sections", [])
        ],
    }
