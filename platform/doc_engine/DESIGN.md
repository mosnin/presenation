# Doc-Engine Design — decks and documents in the template's aesthetic

## Why this approach

Presenton's differentiator is that every template is a real design system:
`templates/<name>/template.json` carries the font files, the exact families
and sizes per role, and every color the design uses. Slides are rendered from
that data by React components and printed via Chromium.

Documents can ride the same rails. The doc-engine derives **theme tokens**
from the template file — heading font (family used at the largest size),
body font (most-used other family), accent (most-used saturated mid-tone),
ink (most-used near-black), plus the bundled TTFs — and applies them to A4
layouts. A "momentum" report visibly belongs to the same family as a
"momentum" deck, without designing anything twice.

## Phase 1 — implemented here

- `theme.py` — token extraction (verified across momentum / executive /
  modern / general).
- `structure.py` — a document model (sections with paragraph / bullets /
  quote / stats / table blocks) + deterministic markdown parser.
- `llm.py` — optional LLM step (any OpenAI-compatible endpoint) that expands
  a prompt into the document model.
- `render.py` — A4 print CSS: cover page with accent bar, uppercase display
  headings with accent rules, themed stat cards / quotes / tables.
- `export.py` — PDF via headless Chromium (same rendering path the slide
  exporter uses) and native DOCX via python-docx.
- `theme.py` also loads **design specs** — YAML front matter declaring
  colors, semantic aliases (`c-bg`/`c-fg`/`c-accent`/`c-muted`), typography
  roles, and Google Fonts. ~40 lines per aesthetic instead of a
  coordinate-based `template.json`, and they can define dark stages.
  `resolve_theme()` prefers a spec, then falls back to template extraction.
- `deck.py` + `deck_render.py` — **interactive HTML decks**: a slide model
  (title/section/bullets/prose/stats/quote/table/closing) rendered to one
  self-contained file. Fixed 1920×1080 stage scaled uniformly to the
  viewport (letterboxes, never reflows), fonts embedded as data URIs,
  keyboard/click/swipe navigation, staggered reveals, progress bar, `#n`
  deep links, `prefers-reduced-motion` honored.

The fixed-stage technique and the design-spec format are adapted from the
MIT-licensed [frontend-slides](https://github.com/zarazhangrui/frontend-slides).

Scope limits: single-column A4 documents, one cover style, no images/charts,
DOCX is coarser than the PDF (Word styles, not CSS). Decks have eight
layouts and no per-slide art direction. Paged output always prints on white
(`Theme.for_print()`) — see `platform/design-specs/README.md` for why.

## Phase 2 — integrate into Presenton itself

1. **Document layouts as React components.** Mirror the slide system: a
   `documents/` layout family per template in the Next.js renderer with
   components like `CoverPage`, `SectionPage`, `StatsBand`, `DataTable`.
   The existing template-v2 JSON→HTML machinery already knows how to render
   arbitrary layout components; documents are "pages" instead of "slides"
   with A4 geometry.
2. **Editable documents.** Reuse the drag-edit UI: the slide editor operates
   on layout JSON, so document pages become editable the same way, with
   PPTX-style export swapped for PDF/DOCX.
3. **LLM planning per document type.** Add document outlines (report, memo,
   one-pager, proposal) next to the slide outline prompts in the FastAPI
   service, sharing the research/web-grounding pipeline.
4. **DOCX fidelity.** Replace python-docx mapping with an HTML→OOXML pass on
   the rendered layout (or LibreOffice headless, already in the Docker
   image) so Word output matches the PDF closely.
5. **New artifact kinds.** The same tokens extend naturally to one-page
   summaries, letterheads, and invoices — anything A4 — and the platform's
   `kind` field is already open-ended.
6. **Style previews.** Render three title slides in three themes as PNGs so
   the user picks a direction by looking rather than by naming a template
   ("show, don't tell"). Cheap to run: one Chromium screenshot per candidate.
7. **Deck art direction.** Per-slide background treatments and image support,
   plus a deck→PDF path (screenshot each slide, combine) for static sharing.
