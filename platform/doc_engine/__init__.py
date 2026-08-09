"""Presenton doc-engine: generate A4 documents (PDF/DOCX/HTML) that share the
aesthetic of a Presenton slide template.

Theme tokens (fonts, accent palette, ink colors) are extracted from the same
`templates/<name>/template.json` files that drive slide generation, so a
document generated with `template="momentum"` visually matches a Momentum
deck.
"""

from .pipeline import generate_document

__all__ = ["generate_document"]
