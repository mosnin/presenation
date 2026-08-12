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

- `deck_render.render_deck_html(..., print_mode=True)` — a paged variant
  (one 16:9 page per slide, no navigation chrome, no animation) printed to a
  vector PDF, so a static copy keeps selectable text instead of being a pile
  of screenshots.
- `pptx_import.py` — python-pptx pulls titles, bullets, tables, speaker
  notes, and embedded images out of an existing `.pptx` and maps them onto
  the deck model, so a deck someone already has can be re-typeset in any
  theme. Pictures are downscaled and inlined as data URIs; sub-80px images
  are skipped as icons. Original positioning is dropped by design.
- `fit.py` — **self-verifying layout**. Renders the deck headlessly, measures
  each slide's content box against the stage's usable area, and repairs
  overflow: even splits for bullets/prose/tables, `image_text` separated into
  copy and picture, and a type-scale step-down (`--tscale`) only for content
  that cannot be divided. Re-measures after each pass, up to four. Verified
  by measuring the repaired deck independently rather than trusting the
  loop's own report.
- `brand.py` — **themes synthesized from a logo or screenshot**. Quantizes
  the image, merges near-duplicate colors, and assigns background / accent /
  text by role and contrast rather than by frequency. Text contrast is
  verified (>= 4.0) before a theme is returned. Serializes to a normal
  design spec so it can be edited by hand afterwards.
- `preview.py` — renders the same title slide across candidate themes as
  PNGs ("show, don't tell"), so the look is chosen by looking. One Chromium
  screenshot per candidate; no LLM call, no engine boot.

The fixed-stage technique, the design-spec format, and the preview-driven
style discovery are adapted from the MIT-licensed
[frontend-slides](https://github.com/zarazhangrui/frontend-slides).

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
6. **Deck art direction.** Per-slide background treatments, image support,
   and richer layout variety — the current eight layouts are deliberately
   plain so every theme renders predictably.
7. **PPTX conversion fidelity.** Infer stats and quote layouts from source
   formatting rather than mapping most content to bullets, and handle
   grouped shapes and SmartArt (currently skipped).
8. **Preview depth.** Previews render the title slide only; a second preview
   slide with a content layout would show more of each theme's personality.
