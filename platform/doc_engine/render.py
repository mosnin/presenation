"""Render a document structure + theme into print-ready A4 HTML."""

from __future__ import annotations

import html
from pathlib import Path

from .theme import Theme, google_fonts_links


def _font_faces(theme: Theme) -> str:
    faces = []
    for family, path in theme.fonts.items():
        if Path(path).exists():
            faces.append(
                f"""@font-face {{
  font-family: "{family}";
  src: url("file://{path}") format("truetype");
}}"""
            )
    return "\n".join(faces)


def _css(theme: Theme) -> str:
    return f"""
{_font_faces(theme)}

:root {{
  --accent: {theme.accent};
  --accent-dark: {theme.accent_dark};
  --ink: {theme.text_color};
  --muted: {theme.muted};
  --bg: {theme.bg};
}}

@page {{
  size: A4;
  margin: 22mm 18mm 20mm 18mm;
}}

* {{ box-sizing: border-box; }}

html {{
  background: var(--bg);
  /* Keep themed page/table backgrounds when printing to PDF. */
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}}

body {{
  margin: 0;
  background: var(--bg);
  font-family: "{theme.body_font}", system-ui, sans-serif;
  color: var(--ink);
  font-size: 10.5pt;
  line-height: 1.55;
}}


.cover {{
  page-break-after: always;
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 240mm;
  position: relative;
}}

.cover .accent-bar {{
  position: absolute;
  top: 0;
  left: 0;
  width: 34mm;
  height: 9mm;
  background: var(--accent);
}}

.cover h1 {{
  font-family: "{theme.heading_font}", "{theme.body_font}", sans-serif;
  font-size: 42pt;
  line-height: 1.02;
  letter-spacing: -0.02em;
  margin: 0 0 8mm;
  font-style: {theme.heading_style};
  text-transform: {theme.heading_transform};
}}

.cover .subtitle {{
  font-size: 14pt;
  color: var(--muted);
  max-width: 130mm;
  margin: 0 0 14mm;
}}

.cover .meta {{
  border-top: 2px solid var(--accent);
  padding-top: 4mm;
  font-size: 10pt;
  color: var(--muted);
  width: 70mm;
}}

section {{ margin-bottom: 9mm; }}

h2 {{
  font-family: "{theme.heading_font}", "{theme.body_font}", sans-serif;
  font-size: 17pt;
  letter-spacing: -0.01em;
  font-style: {theme.heading_style};
  text-transform: {theme.heading_transform};
  margin: 0 0 4mm;
  padding-bottom: 2mm;
  border-bottom: 2.5px solid var(--accent);
  break-after: avoid;
}}

p {{ margin: 0 0 3.5mm; }}

ul {{ margin: 0 0 3.5mm; padding-left: 5mm; }}

li {{ margin-bottom: 1.6mm; }}

li::marker {{ color: var(--accent); }}

blockquote {{
  margin: 4mm 0;
  padding: 3mm 5mm;
  border-left: 3.5px solid var(--accent);
  background: color-mix(in srgb, var(--accent) 6%, var(--bg));
  font-size: 12pt;
  font-style: italic;
}}

.stats {{
  display: flex;
  gap: 4mm;
  margin: 4mm 0;
}}

.stat {{
  flex: 1;
  border-top: 3.5px solid var(--accent);
  background: color-mix(in srgb, var(--accent) 5%, var(--bg));
  padding: 4mm;
}}

.stat .value {{
  font-family: "{theme.heading_font}", sans-serif;
  font-size: 22pt;
  color: var(--accent-dark);
  line-height: 1.1;
}}

.stat .label {{
  font-size: 8.5pt;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-top: 1.5mm;
}}

table {{
  width: 100%;
  border-collapse: collapse;
  margin: 4mm 0;
  font-size: 9.5pt;
}}

th {{
  background: var(--accent);
  color: var(--bg);
  text-align: left;
  padding: 2.5mm 3mm;
  font-family: "{theme.heading_font}", sans-serif;
  font-weight: normal;
  letter-spacing: 0.03em;
}}

td {{
  padding: 2.2mm 3mm;
  border-bottom: 1px solid color-mix(in srgb, var(--ink) 15%, var(--bg));
}}

tr:nth-child(even) td {{
  background: color-mix(in srgb, var(--accent) 3%, var(--bg));
}}
"""


def _render_block(block: dict) -> str:
    kind = block.get("type")
    if kind == "paragraph":
        return f"<p>{html.escape(block.get('text', ''))}</p>"
    if kind == "bullets":
        items = "".join(
            f"<li>{html.escape(item)}</li>" for item in block.get("items", [])
        )
        return f"<ul>{items}</ul>"
    if kind == "quote":
        return f"<blockquote>{html.escape(block.get('text', ''))}</blockquote>"
    if kind == "stats":
        cards = "".join(
            f"""<div class="stat">
  <div class="value">{html.escape(str(item.get('value', '')))}</div>
  <div class="label">{html.escape(str(item.get('label', '')))}</div>
</div>"""
            for item in block.get("items", [])[:4]
        )
        return f'<div class="stats">{cards}</div>'
    if kind == "table":
        head = "".join(
            f"<th>{html.escape(str(c))}</th>" for c in block.get("header", [])
        )
        rows = "".join(
            "<tr>"
            + "".join(f"<td>{html.escape(str(c))}</td>" for c in row)
            + "</tr>"
            for row in block.get("rows", [])
        )
        return f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>"
    return ""


def render_html(doc: dict, theme: Theme) -> str:
    theme = theme.for_print()
    sections = "".join(
        f"""<section>
<h2>{html.escape(section.get('heading', ''))}</h2>
{''.join(_render_block(b) for b in section.get('blocks', []))}
</section>"""
        for section in doc.get("sections", [])
    )

    subtitle = doc.get("subtitle")
    meta = doc.get("meta")
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{html.escape(doc.get('title', 'Document'))}</title>
{google_fonts_links(theme)}
<style>{_css(theme)}</style>
</head>
<body>
<div class="cover">
  <div class="accent-bar"></div>
  <h1>{html.escape(doc.get('title', 'Document'))}</h1>
  {f'<p class="subtitle">{html.escape(subtitle)}</p>' if subtitle else ''}
  {f'<div class="meta">{html.escape(meta)}</div>' if meta else ''}
</div>
{sections}
</body>
</html>"""
