# Design specs

Lightweight theme definitions for the doc-engine and HTML deck renderer — an
alternative to full slide templates. A spec is a markdown file with YAML front
matter declaring colors, semantic color aliases, typography roles, and Google
Fonts to load. Adding a new aesthetic is ~40 lines of YAML instead of a
coordinate-based `template.json`.

Themes are resolved by name: `platform/design-specs/<name>.md` first, then
`templates/<name>/template.json` (extracted tokens). So `momentum` still maps
to the slide template, while `midnight-gold` maps to the spec here.

The spec format follows the design-system style of the MIT-licensed
[frontend-slides](https://github.com/zarazhangrui/frontend-slides) project.
Specs in this directory are original to this repository.

Notes:

- `color-aliases` map semantic roles to named colors (or literal hex):
  `c-bg`, `c-fg`, `c-accent`, `c-muted`.
- `typography` roles used today: `display` (fontFamily, fontStyle,
  textTransform) and `body` (fontFamily). More roles are allowed and ignored.
- `webfonts` entries are Google Fonts family specs, e.g.
  `Fraunces:ital,wght@0,600;1,600`.
- Specs may define dark stages (see `midnight-gold`); PPTX export is not
  available for spec themes — they target HTML decks and PDF/DOCX documents.
- `c-bg` applies to **HTML decks**. Paged output (PDF/DOCX) always prints on
  white: CSS cannot paint the `@page` margin area, so a colored body would
  leave a white frame on every page, and dark pages print badly. For a
  dark-stage theme, `Theme.for_print()` also restores near-black text and
  darkens a too-light accent so documents stay legible — fonts, accent, and
  component fills still carry the aesthetic.
