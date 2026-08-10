---
name: Midnight Gold
description: A dark scholarly stage — near-black indigo field with warm gold
  italic serifs floating on it. Fraunces carries every headline in italic;
  Karla handles body text in a quiet supporting role. The mood is a rare-book
  reading room after hours. One color, two typefaces, plenty of stillness.

colors:
  indigo: "#171B33"
  indigo-deep: "#101324"
  gold: "#E4C464"
  gold-soft: "#EFD98F"
  brass: "#A98F3F"

color-aliases:
  c-bg: indigo
  c-fg: gold
  c-accent: gold-soft
  c-muted: brass

typography:
  display:
    fontFamily: "Fraunces, Georgia, serif"
    fontStyle: italic
    textTransform: none
    fontWeight: 600
  body:
    fontFamily: "Karla, system-ui, sans-serif"
    fontWeight: 400

webfonts:
  - "Fraunces:ital,wght@0,600;1,400;1,600"
  - "Karla:wght@400;700"
---

Usage guidance for renderers and LLMs: keep the stage monochromatic; gold on
indigo only. Headlines are italic serif at generous sizes; never uppercase.
Body copy stays short — this theme rewards whitespace. Rules and borders use
the muted brass at low opacity.
