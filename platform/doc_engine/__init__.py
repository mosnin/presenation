"""Presenton doc-engine: generate A4 documents (PDF/DOCX/HTML) and
self-contained interactive HTML decks that share the aesthetic of a Presenton
slide template.

Theme tokens (fonts, accent palette, ink colors) are extracted from the same
`templates/<name>/template.json` files that drive slide generation, so a
document generated with `template="momentum"` visually matches a Momentum
deck. Themes may also be declared directly as YAML design specs (see
`platform/design-specs/`), which is cheaper to author and supports dark
stages that the slide templates don't cover.
"""

from .brand import theme_from_image
from .patch import apply_patch
from .pipeline import generate_deck, generate_document, generate_style_previews

__all__ = [
    "apply_patch",
    "generate_deck",
    "generate_document",
    "generate_style_previews",
    "theme_from_image",
]
