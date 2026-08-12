"""Render a deck into a single self-contained interactive HTML file.

Zero runtime dependencies: inline CSS/JS, fonts embedded (bundled template
TTFs as data: URIs) or loaded from Google Fonts (design-spec themes).

The fixed-stage approach — a 1920x1080 canvas scaled uniformly to the
viewport, never reflowed — follows the technique of the MIT-licensed
frontend-slides project (github.com/zarazhangrui/frontend-slides).
"""

from __future__ import annotations

import base64
import html
from pathlib import Path

from .theme import Theme, google_fonts_links


def _embedded_font_faces(theme: Theme) -> str:
    """Embed the heading/body font files (when the theme bundles TTFs) so the
    deck stays a single portable file."""
    faces = []
    for family in dict.fromkeys([theme.heading_font, theme.body_font]):
        path = theme.fonts.get(family)
        if path and Path(path).exists():
            data = base64.b64encode(Path(path).read_bytes()).decode()
            faces.append(
                f"""@font-face {{
  font-family: "{family}";
  src: url(data:font/ttf;base64,{data}) format("truetype");
  font-display: swap;
}}"""
            )
    return "\n".join(faces)


def _css(theme: Theme) -> str:
    return f"""
{_embedded_font_faces(theme)}

:root {{
  --bg: {theme.bg};
  --fg: {theme.text_color};
  --accent: {theme.accent};
  --muted: {theme.muted};
  --panel: color-mix(in srgb, var(--accent) 7%, var(--bg));
  --rule: color-mix(in srgb, var(--fg) 18%, var(--bg));
}}

* {{ box-sizing: border-box; margin: 0; }}

html, body {{ height: 100%; }}

body {{
  background: color-mix(in srgb, var(--bg) 86%, black);
  font-family: "{theme.body_font}", system-ui, sans-serif;
  color: var(--fg);
  overflow: hidden;
}}

/* Viewport wrapper fills the window; the 1920x1080 stage is scaled as a
   whole (letterboxed when needed) and never reflows. */
.viewport {{
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}}

.stage {{
  width: 1920px;
  height: 1080px;
  flex: none; /* keep the fixed canvas; scaling happens via transform only */
  position: relative;
  background: var(--bg);
  overflow: hidden;
  transform-origin: center center;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
}}

.slide {{
  position: absolute;
  inset: 0;
  padding: 110px 140px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  visibility: hidden;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.45s ease;
}}

.slide.active {{
  visibility: visible;
  opacity: 1;
  pointer-events: auto;
}}

.heading-font {{
  font-family: "{theme.heading_font}", "{theme.body_font}", sans-serif;
  font-style: {theme.heading_style};
  text-transform: {theme.heading_transform};
}}

.kicker {{
  font-size: 26px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--accent);
  margin-bottom: 34px;
  font-weight: 700;
}}

.slide h1 {{
  font-size: calc(148px * var(--tscale, 1));
  line-height: 1.0;
  letter-spacing: -0.015em;
  font-weight: 800;
}}

.slide h2 {{
  font-size: calc(84px * var(--tscale, 1));
  line-height: 1.04;
  letter-spacing: -0.01em;
  font-weight: 700;
  margin-bottom: 56px;
}}

.accent-bar {{
  width: 170px;
  height: 22px;
  background: var(--accent);
  margin-bottom: 60px;
}}

.subtitle {{
  font-size: calc(40px * var(--tscale, 1));
  color: var(--muted);
  max-width: 1150px;
  line-height: 1.4;
  margin-top: 44px;
}}

.meta {{
  margin-top: 90px;
  padding-top: 26px;
  border-top: 3px solid var(--accent);
  width: 520px;
  font-size: 27px;
  color: var(--muted);
}}

.slide.layout-section .kicker {{ font-size: 34px; }}

.slide.layout-section h1 {{ font-size: calc(170px * var(--tscale, 1)); }}

.slide.layout-section::after {{
  content: "";
  position: absolute;
  left: 140px;
  bottom: 130px;
  width: 320px;
  height: 22px;
  background: var(--accent);
}}

ul.bullets {{
  list-style: none;
  font-size: calc(44px * var(--tscale, 1));
  line-height: 1.35;
  max-width: 1480px;
}}

ul.bullets li {{
  padding: 30px 0 30px 66px;
  position: relative;
  border-bottom: 1px solid var(--rule);
}}

ul.bullets li::before {{
  content: "";
  position: absolute;
  left: 0;
  top: 50px;
  width: 30px;
  height: 10px;
  background: var(--accent);
}}

.paragraphs {{
  font-size: calc(42px * var(--tscale, 1));
  line-height: 1.5;
  max-width: 1420px;
  display: flex;
  flex-direction: column;
  gap: 44px;
}}

.stats-row {{
  display: flex;
  gap: 44px;
}}

.stat-card {{
  flex: 1;
  background: var(--panel);
  border-top: 12px solid var(--accent);
  padding: 60px 48px;
}}

.stat-card .value {{
  font-family: "{theme.heading_font}", sans-serif;
  font-style: {theme.heading_style};
  font-size: calc(112px * var(--tscale, 1));
  line-height: 1;
  color: var(--accent);
}}

.stat-card .label {{
  margin-top: 30px;
  font-size: 26px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  line-height: 1.35;
}}

.slide.layout-quote {{ padding: 110px 200px; }}

.quote-mark {{
  font-family: "{theme.heading_font}", serif;
  font-size: 220px;
  line-height: 0.6;
  color: var(--accent);
}}

blockquote {{
  font-family: "{theme.heading_font}", serif;
  font-style: {theme.heading_style};
  font-size: calc(76px * var(--tscale, 1));
  line-height: 1.22;
  margin-top: 50px;
  max-width: 1480px;
}}

.attribution {{
  margin-top: 64px;
  font-size: 30px;
  color: var(--muted);
}}

table {{
  border-collapse: collapse;
  font-size: calc(36px * var(--tscale, 1));
  width: 100%;
  max-width: 1560px;
}}

th {{
  font-family: "{theme.heading_font}", sans-serif;
  text-align: left;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-size: 30px;
  color: var(--bg);
  background: var(--accent);
  padding: 26px 34px;
}}

td {{
  padding: 26px 34px;
  border-bottom: 2px solid var(--rule);
}}

/* Image layouts. Pictures are inlined as data URIs so the deck stays one
   portable file; object-fit keeps them from distorting at any aspect. */
.slide.layout-image {{ padding: 90px 140px; }}

.slide.layout-image .figure {{
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 40px;
}}

.slide.layout-image img {{
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}}

.split {{
  display: flex;
  gap: 80px;
  align-items: center;
  flex: 1;
  min-height: 0;
}}

.split .copy {{ flex: 1.1; }}

.split .art {{
  flex: 1;
  align-self: stretch;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
}}

.split .art img {{
  max-width: 100%;
  max-height: 620px;
  object-fit: contain;
}}

.split ul.bullets {{ font-size: 38px; }}

.split ul.bullets li {{ padding: 22px 0 22px 56px; }}

.split ul.bullets li::before {{ top: 38px; }}

/* Set by the fit engine (fit.py) when a slide's content cannot be split
   across slides — scales the type down rather than letting it clip. */
.slide.density-tight {{ --tscale: 0.86; }}
.slide.density-tighter {{ --tscale: 0.74; }}
.slide.density-tightest {{ --tscale: 0.62; }}

.slide.layout-closing {{ align-items: flex-start; text-align: left; }}

.slide.layout-closing .subtitle {{ margin-top: 56px; }}

/* Staggered entrance for slide children */
.slide .reveal {{
  opacity: 0;
  transform: translateY(26px);
}}

.slide.active .reveal {{
  animation: rise 0.6s cubic-bezier(0.2, 0.7, 0.2, 1) forwards;
}}

.slide.active .reveal:nth-child(1) {{ animation-delay: 0.05s; }}
.slide.active .reveal:nth-child(2) {{ animation-delay: 0.15s; }}
.slide.active .reveal:nth-child(3) {{ animation-delay: 0.25s; }}
.slide.active .reveal:nth-child(4) {{ animation-delay: 0.35s; }}
.slide.active .reveal:nth-child(5) {{ animation-delay: 0.45s; }}
.slide.active .reveal:nth-child(n + 6) {{ animation-delay: 0.55s; }}

@keyframes rise {{
  to {{ opacity: 1; transform: none; }}
}}

/* Sits over the stage when the window is exactly 16:9, and over the
   letterbox otherwise — so it carries its own contrast. */
.hud {{
  position: fixed;
  right: 22px;
  bottom: 18px;
  padding: 5px 12px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  font-size: 14px;
  font-family: system-ui, sans-serif;
  font-variant-numeric: tabular-nums;
  z-index: 3;
  user-select: none;
}}

.progress {{
  position: fixed;
  left: 0;
  bottom: 0;
  height: 5px;
  background: var(--accent);
  width: 0;
  transition: width 0.3s ease;
  z-index: 3;
}}

@media (prefers-reduced-motion: reduce) {{
  .slide {{ transition: none; }}
  .slide .reveal,
  .slide.active .reveal {{
    animation: none;
    opacity: 1;
    transform: none;
  }}
  .progress {{ transition: none; }}
}}
"""


_JS = """
(() => {
  const stage = document.querySelector(".stage");
  const slides = [...document.querySelectorAll(".slide")];
  const progress = document.querySelector(".progress");
  const counter = document.querySelector(".hud");
  let index = 0;

  function fit() {
    const scale = Math.min(innerWidth / 1920, innerHeight / 1080);
    stage.style.transform = `scale(${scale})`;
  }

  function show(next, pushHash = true) {
    index = Math.max(0, Math.min(slides.length - 1, next));
    slides.forEach((slide, i) => slide.classList.toggle("active", i === index));
    progress.style.width = `${((index + 1) / slides.length) * 100}%`;
    counter.textContent = `${index + 1} / ${slides.length}`;
    if (pushHash) history.replaceState(null, "", `#${index + 1}`);
  }

  addEventListener("resize", fit);
  addEventListener("keydown", (event) => {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (["ArrowRight", "ArrowDown", "PageDown", " "].includes(event.key)) {
      event.preventDefault();
      show(index + 1);
    } else if (["ArrowLeft", "ArrowUp", "PageUp"].includes(event.key)) {
      event.preventDefault();
      show(index - 1);
    } else if (event.key === "Home") show(0);
    else if (event.key === "End") show(slides.length - 1);
  });

  let touchX = null;
  addEventListener("touchstart", (e) => (touchX = e.touches[0].clientX), {
    passive: true,
  });
  addEventListener(
    "touchend",
    (e) => {
      if (touchX === null) return;
      const dx = e.changedTouches[0].clientX - touchX;
      if (Math.abs(dx) > 40) show(index + (dx < 0 ? 1 : -1));
      touchX = null;
    },
    { passive: true }
  );
  stage.addEventListener("click", (e) => {
    if (window.getSelection()?.toString()) return;
    show(index + (e.clientX < innerWidth / 3 ? -1 : 1));
  });

  fit();
  const fromHash = parseInt(location.hash.slice(1), 10);
  show(Number.isFinite(fromHash) ? fromHash - 1 : 0, false);
})();
"""


def _esc(value: object) -> str:
    return html.escape(str(value)) if value is not None else ""


_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}


def _image_src(path: str | None) -> str | None:
    """Inline an image as a data URI, keeping the deck a single file.

    A missing or unreadable image yields None so the slide renders without
    it rather than showing a broken-image icon.
    """
    if not path:
        return None
    file = Path(path)
    if not file.exists():
        return None
    mime = _MIME_BY_SUFFIX.get(file.suffix.lower(), "image/png")
    try:
        data = base64.b64encode(file.read_bytes()).decode()
    except OSError:
        return None
    return f"data:{mime};base64,{data}"


def _render_slide(slide: dict) -> str:
    layout = slide.get("layout", "prose")
    parts: list[str] = []

    if layout == "title":
        parts.append('<div class="accent-bar reveal"></div>')
        parts.append(f'<h1 class="heading-font reveal">{_esc(slide.get("title"))}</h1>')
        if slide.get("subtitle"):
            parts.append(f'<p class="subtitle reveal">{_esc(slide["subtitle"])}</p>')
        if slide.get("meta"):
            parts.append(f'<div class="meta reveal">{_esc(slide["meta"])}</div>')
    elif layout == "section":
        parts.append(f'<div class="kicker reveal">{_esc(slide.get("kicker", ""))}</div>')
        parts.append(
            f'<h1 class="heading-font reveal">{_esc(slide.get("heading"))}</h1>'
        )
    elif layout == "bullets":
        parts.append(
            f'<h2 class="heading-font reveal">{_esc(slide.get("heading"))}</h2>'
        )
        items = "".join(
            f'<li class="reveal">{_esc(item)}</li>' for item in slide.get("items", [])
        )
        parts.append(f'<ul class="bullets">{items}</ul>')
    elif layout == "prose":
        parts.append(
            f'<h2 class="heading-font reveal">{_esc(slide.get("heading"))}</h2>'
        )
        paragraphs = "".join(
            f'<p class="reveal">{_esc(p)}</p>' for p in slide.get("paragraphs", [])
        )
        parts.append(f'<div class="paragraphs">{paragraphs}</div>')
    elif layout == "stats":
        parts.append(
            f'<h2 class="heading-font reveal">{_esc(slide.get("heading"))}</h2>'
        )
        cards = "".join(
            f"""<div class="stat-card reveal">
  <div class="value">{_esc(item.get("value"))}</div>
  <div class="label">{_esc(item.get("label"))}</div>
</div>"""
            for item in slide.get("items", [])
        )
        parts.append(f'<div class="stats-row">{cards}</div>')
    elif layout == "quote":
        parts.append('<div class="quote-mark reveal">“</div>')
        parts.append(f'<blockquote class="reveal">{_esc(slide.get("text"))}</blockquote>')
        if slide.get("attribution"):
            parts.append(
                f'<div class="attribution reveal">— {_esc(slide["attribution"])}</div>'
            )
    elif layout == "table":
        parts.append(
            f'<h2 class="heading-font reveal">{_esc(slide.get("heading"))}</h2>'
        )
        head = "".join(f"<th>{_esc(c)}</th>" for c in slide.get("header", []))
        rows = "".join(
            "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>"
            for row in slide.get("rows", [])
        )
        parts.append(
            f'<div class="reveal"><table><thead><tr>{head}</tr></thead>'
            f"<tbody>{rows}</tbody></table></div>"
        )
    elif layout == "image":
        parts.append(
            f'<h2 class="heading-font reveal">{_esc(slide.get("heading"))}</h2>'
        )
        src = _image_src(slide.get("image"))
        if src:
            parts.append(
                f'<div class="figure reveal">'
                f'<img src="{src}" alt="{_esc(slide.get("heading"))}"></div>'
            )
    elif layout == "image_text":
        parts.append(
            f'<h2 class="heading-font reveal">{_esc(slide.get("heading"))}</h2>'
        )
        items = "".join(
            f'<li class="reveal">{_esc(item)}</li>' for item in slide.get("items", [])
        )
        copy = f'<div class="copy"><ul class="bullets">{items}</ul></div>'
        src = _image_src(slide.get("image"))
        art = (
            f'<div class="art reveal"><img src="{src}" '
            f'alt="{_esc(slide.get("heading"))}"></div>'
            if src
            else ""
        )
        parts.append(f'<div class="split">{copy}{art}</div>')
    elif layout == "closing":
        parts.append('<div class="accent-bar reveal"></div>')
        parts.append(
            f'<h1 class="heading-font reveal">{_esc(slide.get("heading"))}</h1>'
        )
        if slide.get("subheading"):
            parts.append(f'<p class="subtitle reveal">{_esc(slide["subheading"])}</p>')

    density = slide.get("density")
    density_class = f" density-{density}" if density else ""
    return (
        f'<div class="slide layout-{layout}{density_class}">'
        f'{"".join(parts)}</div>'
    )


_PRINT_CSS = """
/* Print mode: every slide becomes one 16:9 page, all visible, no chrome.
   Chromium prints this to a vector PDF with selectable text — better than
   screenshotting each slide into images. */
@page {
  size: 1920px 1080px;
  margin: 0;
}

html, body { height: auto; overflow: visible; background: var(--bg); }

.viewport { position: static; display: block; }

.stage {
  width: 1920px;
  height: auto;
  transform: none !important;
  box-shadow: none;
}

.slide {
  position: relative;
  inset: auto;
  width: 1920px;
  height: 1080px;
  visibility: visible;
  opacity: 1;
  pointer-events: auto;
  break-after: page;
  page-break-after: always;
}

.slide:last-child { break-after: auto; page-break-after: auto; }

/* No entrance animation in a static document. */
.slide .reveal, .slide.active .reveal {
  animation: none !important;
  opacity: 1;
  transform: none;
}

.hud, .progress { display: none !important; }
"""


FIT_REPORT_ID = "presenton-fit-report"

# Measures each slide's real content box against the usable area of the
# 1920x1080 stage and writes the result into the DOM, where `chromium
# --dump-dom` can retrieve it. Runs against the print layout (transform:
# none, all slides laid out) so the numbers are unscaled CSS pixels.
_MEASURE_JS = """
(() => {
  function measure() {
    const slides = [...document.querySelectorAll(".slide")];
    const report = slides.map((slide, index) => {
      const style = getComputedStyle(slide);
      const padTop = parseFloat(style.paddingTop);
      const padBottom = parseFloat(style.paddingBottom);
      const padLeft = parseFloat(style.paddingLeft);
      const padRight = parseFloat(style.paddingRight);
      const box = slide.getBoundingClientRect();
      const usableHeight = slide.clientHeight - padTop - padBottom;
      const usableWidth = slide.clientWidth - padLeft - padRight;

      let contentHeight = 0;
      let contentWidth = 0;
      for (const child of slide.children) {
        const rect = child.getBoundingClientRect();
        if (rect.height === 0 && rect.width === 0) continue;
        contentHeight = Math.max(contentHeight, rect.bottom - box.top - padTop);
        contentWidth = Math.max(contentWidth, rect.right - box.left - padLeft);
      }
      const layoutClass = [...slide.classList].find((c) =>
        c.startsWith("layout-")
      );
      return {
        index,
        layout: layoutClass ? layoutClass.slice("layout-".length) : null,
        usableHeight,
        usableWidth,
        contentHeight: Math.round(contentHeight),
        contentWidth: Math.round(contentWidth),
        overflowY: Math.max(0, Math.round(contentHeight - usableHeight)),
        overflowX: Math.max(0, Math.round(contentWidth - usableWidth)),
        fillRatio: usableHeight > 0 ? contentHeight / usableHeight : 0,
      };
    });
    const node = document.createElement("script");
    node.type = "application/json";
    node.id = "__FIT_REPORT_ID__";
    node.textContent = JSON.stringify(report);
    document.body.appendChild(node);
  }
  // Wait for webfonts: measuring against a fallback face gives wrong metrics.
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(measure).catch(measure);
  } else {
    measure();
  }
})();
""".replace("__FIT_REPORT_ID__", FIT_REPORT_ID)


def render_deck_html(
    deck: dict,
    theme: Theme,
    print_mode: bool = False,
    measure: bool = False,
) -> str:
    """Render the deck. With print_mode, emit the paged variant used to
    produce a PDF (all slides visible, one page each, no navigation chrome).
    With measure, emit that same layout plus the fit-measurement script."""
    print_mode = print_mode or measure
    slides = "".join(_render_slide(slide) for slide in deck.get("slides", []))
    return f"""<!doctype html>
<!-- Generated by Presenton doc-engine ({theme.template} theme).
     Fixed-stage technique after frontend-slides (MIT,
     github.com/zarazhangrui/frontend-slides). Self-contained: no runtime
     dependencies. Navigate with arrows/space, tap/swipe on touch. -->
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(deck.get("title"))}</title>
{google_fonts_links(theme, blocking=print_mode)}
<style>{_css(theme)}{_PRINT_CSS if print_mode else ""}</style>
</head>
<body>
<div class="viewport"><div class="stage">{slides}</div></div>
{"" if print_mode else '<div class="progress"></div><div class="hud"></div>'}
{"" if print_mode else f"<script>{_JS}</script>"}
{f"<script>{_MEASURE_JS}</script>" if measure else ""}
</body>
</html>"""
