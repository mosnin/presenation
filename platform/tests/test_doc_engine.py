"""Integration tests for the doc-engine.

Covers everything the platform depends on without deploying Convex or Modal:
theme resolution from both sources, all four artifact paths, PPTX import, and
the error paths. Chromium-dependent tests are skipped when no browser is
found, so the suite still runs somewhere without one.

Run:
    cd platform && python -m pytest tests -q
    cd platform && python tests/test_doc_engine.py     # no pytest needed
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from doc_engine import deck as deck_mod  # noqa: E402
from doc_engine import deck_render, pipeline, structure  # noqa: E402
from doc_engine.theme import resolve_theme  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT.parent / "templates"
SPECS = ROOT / "design-specs"
SAMPLE = ROOT / "examples" / "brief.md"

SLIDE_TEMPLATE = "momentum"
DESIGN_SPEC = "swiss-crimson"
DARK_SPEC = "midnight-gold"


def find_chromium() -> str | None:
    """Locate a Chromium binary: env override, PATH, or a Playwright install."""
    if os.environ.get("CHROMIUM_PATH"):
        return os.environ["CHROMIUM_PATH"]
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    pw_root = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers"))
    if pw_root.is_dir():
        for pattern in ("chromium*/chrome-linux/chrome", "chromium*/chrome-linux/headless_shell"):
            matches = sorted(pw_root.glob(pattern))
            if matches:
                return str(matches[-1])
    return None


CHROMIUM = find_chromium()
needs_chromium = unittest.skipIf(CHROMIUM is None, "no Chromium binary found")

try:
    import pptx  # noqa: F401

    HAS_PPTX = True
except ImportError:
    HAS_PPTX = False


class TempDirTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()


class ThemeTests(unittest.TestCase):
    def test_slide_template_tokens(self):
        theme = resolve_theme(SLIDE_TEMPLATE, templates_dir=TEMPLATES, specs_dir=SPECS)
        self.assertEqual(theme.heading_font, "Anton")
        self.assertEqual(theme.body_font, "Lato")
        self.assertTrue(theme.accent.startswith("#"))
        self.assertTrue(theme.fonts, "slide templates should bundle font files")

    def test_design_spec_tokens(self):
        theme = resolve_theme(DESIGN_SPEC, templates_dir=TEMPLATES, specs_dir=SPECS)
        self.assertEqual(theme.heading_font, "Archivo")
        self.assertEqual(theme.accent, "#C41E2F")
        self.assertTrue(theme.webfonts, "specs should declare webfonts")

    def test_spec_wins_over_template(self):
        # Both lookups must resolve; a spec name must not fall through to a
        # template of the same name (there is none, but the order matters).
        spec = resolve_theme(DARK_SPEC, templates_dir=TEMPLATES, specs_dir=SPECS)
        self.assertEqual(spec.bg, "#171B33")

    def test_unknown_theme_raises_with_both_paths(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            resolve_theme("no-such-theme", templates_dir=TEMPLATES, specs_dir=SPECS)
        message = str(ctx.exception)
        self.assertIn("no-such-theme.md", message)
        self.assertIn("template.json", message)

    def test_print_theme_is_legible_on_white(self):
        """A dark stage must not print light type on white paper."""
        dark = resolve_theme(DARK_SPEC, templates_dir=TEMPLATES, specs_dir=SPECS)
        printed = dark.for_print()
        self.assertEqual(printed.bg, "#ffffff")
        self.assertEqual(printed.text_color, "#16181d")
        # The accent is also used as a fill behind reversed-out text.
        r, g, b = (int(printed.accent[i : i + 2], 16) for i in (1, 3, 5))
        self.assertLess((r + g + b) / 3, 200, "print accent should not be pale")

    def test_print_theme_preserves_light_theme_ink(self):
        light = resolve_theme(SLIDE_TEMPLATE, templates_dir=TEMPLATES, specs_dir=SPECS)
        self.assertEqual(light.for_print().text_color, light.text_color)


class StructureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.doc = structure.parse_markdown(SAMPLE.read_text())

    def test_markdown_parses_into_document(self):
        self.assertEqual(self.doc["title"], "Q3 Sales Report")
        self.assertIsNotNone(self.doc["subtitle"])
        self.assertIsNotNone(self.doc["meta"])
        headings = [s["heading"] for s in self.doc["sections"]]
        self.assertIn("Key metrics", headings)

    def test_block_types_detected(self):
        kinds = {
            block["type"]
            for section in self.doc["sections"]
            for block in section["blocks"]
        }
        self.assertTrue({"paragraph", "bullets", "quote", "table"} <= kinds)

    def test_table_header_separated_from_rows(self):
        tables = [
            block
            for section in self.doc["sections"]
            for block in section["blocks"]
            if block["type"] == "table"
        ]
        self.assertTrue(tables)
        self.assertEqual(tables[0]["header"][0], "Region")
        self.assertTrue(all(len(r) == 3 for r in tables[0]["rows"]))

    def test_empty_content_still_yields_a_document(self):
        doc = structure.parse_markdown("")
        self.assertEqual(doc["title"], "Untitled document")
        self.assertEqual(doc["sections"], [])


class DeckModelTests(unittest.TestCase):
    def test_markdown_maps_to_slide_layouts(self):
        deck = deck_mod.markdown_to_deck(SAMPLE.read_text())
        layouts = [s["layout"] for s in deck["slides"]]
        self.assertEqual(layouts[0], "title")
        self.assertEqual(layouts[-1], "closing")
        self.assertIn("bullets", layouts)
        self.assertIn("table", layouts)

    def test_long_bullet_lists_split_across_slides(self):
        doc = {
            "title": "T",
            "sections": [
                {
                    "heading": "Many",
                    "blocks": [{"type": "bullets", "items": [f"item {i}" for i in range(14)]}],
                }
            ],
        }
        bullets = [s for s in deck_mod.doc_to_deck(doc)["slides"] if s["layout"] == "bullets"]
        self.assertGreater(len(bullets), 1)
        self.assertTrue(all(len(s["items"]) <= 6 for s in bullets))


class DeckRenderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.deck = deck_mod.markdown_to_deck(SAMPLE.read_text())

    def render(self, theme_name: str, **kwargs) -> str:
        theme = resolve_theme(theme_name, templates_dir=TEMPLATES, specs_dir=SPECS)
        return deck_render.render_deck_html(self.deck, theme, **kwargs)

    def test_interactive_deck_is_self_contained(self):
        html = self.render(SLIDE_TEMPLATE)
        self.assertIn('<div class="stage">', html)
        self.assertIn("prefers-reduced-motion", html)
        self.assertIn("data:font/ttf;base64,", html)  # fonts embedded
        self.assertNotIn("<script src=", html)  # no external JS
        self.assertNotIn('link rel="stylesheet" href="http', html)

    def test_spec_theme_uses_webfonts(self):
        html = self.render(DESIGN_SPEC)
        self.assertIn("fonts.googleapis.com", html)

    def test_print_mode_drops_chrome_and_paginates(self):
        html = self.render(SLIDE_TEMPLATE, print_mode=True)
        self.assertIn("size: 1920px 1080px", html)
        self.assertIn("page-break-after", html)
        self.assertNotIn('<div class="hud">', html)
        self.assertNotIn("addEventListener", html)  # navigation JS omitted

    def test_content_is_escaped(self):
        deck = {
            "title": "<script>alert(1)</script>",
            "slides": [{"layout": "title", "title": "<script>alert(1)</script>"}],
        }
        theme = resolve_theme(SLIDE_TEMPLATE, templates_dir=TEMPLATES, specs_dir=SPECS)
        html = deck_render.render_deck_html(deck, theme)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_missing_image_is_skipped_not_broken(self):
        deck = {
            "title": "T",
            "slides": [
                {"layout": "image", "heading": "H", "image": "/nonexistent/x.png"}
            ],
        }
        theme = resolve_theme(SLIDE_TEMPLATE, templates_dir=TEMPLATES, specs_dir=SPECS)
        html = deck_render.render_deck_html(deck, theme)
        self.assertNotIn("<img", html)
        self.assertIn("layout-image", html)


@needs_chromium
class DocumentPipelineTests(TempDirTest):
    def test_document_pdf_and_docx(self):
        out = pipeline.generate_document(
            content=SAMPLE.read_text(),
            template=SLIDE_TEMPLATE,
            formats=["pdf", "docx", "html"],
            templates_dir=TEMPLATES,
            specs_dir=SPECS,
            out_dir=self.tmp,
            chromium=CHROMIUM,
        )
        self.assertEqual(set(out), {"pdf", "docx", "html"})
        for path in out.values():
            self.assertGreater(Path(path).stat().st_size, 1000)
        self.assertTrue(Path(out["pdf"]).read_bytes().startswith(b"%PDF"))

    def test_document_with_design_spec(self):
        out = pipeline.generate_document(
            content=SAMPLE.read_text(),
            template=DARK_SPEC,
            formats=["pdf"],
            templates_dir=TEMPLATES,
            specs_dir=SPECS,
            out_dir=self.tmp,
            chromium=CHROMIUM,
        )
        self.assertTrue(Path(out["pdf"]).exists())


@needs_chromium
class DeckPipelineTests(TempDirTest):
    def test_deck_html_and_pdf(self):
        out = pipeline.generate_deck(
            content=SAMPLE.read_text(),
            template=DESIGN_SPEC,
            formats=["html", "pdf"],
            templates_dir=TEMPLATES,
            specs_dir=SPECS,
            out_dir=self.tmp,
            chromium=CHROMIUM,
        )
        self.assertEqual(set(out), {"html", "pdf"})
        self.assertTrue(Path(out["pdf"]).read_bytes().startswith(b"%PDF"))
        # The deck model is written alongside, for downstream reuse.
        saved = json.loads((self.tmp / "deck.json").read_text())
        self.assertEqual(saved["slides"][0]["layout"], "title")

    def test_style_previews_render_one_png_per_theme(self):
        out = pipeline.generate_style_previews(
            title="Quarterly Review",
            themes=[SLIDE_TEMPLATE, DARK_SPEC],
            templates_dir=TEMPLATES,
            specs_dir=SPECS,
            out_dir=self.tmp,
            chromium=CHROMIUM,
        )
        self.assertEqual(set(out), {SLIDE_TEMPLATE, DARK_SPEC})
        for path in out.values():
            self.assertTrue(Path(path).read_bytes().startswith(b"\x89PNG"))

    def test_unknown_preview_theme_is_skipped(self):
        out = pipeline.generate_style_previews(
            title="T",
            themes=[SLIDE_TEMPLATE, "no-such-theme"],
            templates_dir=TEMPLATES,
            specs_dir=SPECS,
            out_dir=self.tmp,
            chromium=CHROMIUM,
        )
        self.assertEqual(set(out), {SLIDE_TEMPLATE})


def build_sample_pptx(path: Path, with_images: bool = False) -> Path:
    """A small .pptx exercising titles, bullets, tables, notes, and images."""
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = "Fleet Program Review"
    slide.placeholders[1].text = "Operations team"

    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "What changed"
    frame = slide.placeholders[1].text_frame
    frame.text = "Onboarding cut to 4 days"
    frame.add_paragraph().text = "Tickets down 31%"
    slide.notes_slide.notes_text_frame.text = "Mention the depots."

    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "Depots"
    table = slide.shapes.add_table(
        3, 2, Inches(0.6), Inches(2.0), Inches(8.0), Inches(2.0)
    ).table
    for r, row in enumerate([["Depot", "Riders"], ["North", "3,100"], ["South", "2,400"]]):
        for c, value in enumerate(row):
            table.cell(r, c).text = value

    if with_images:
        from PIL import Image

        big = path.parent / "big.png"
        tiny = path.parent / "tiny.png"
        Image.new("RGB", (1000, 700), "#3355aa").save(big)
        Image.new("RGB", (40, 40), "#000000").save(tiny)
        slide = prs.slides.add_slide(prs.slide_layouts[5])
        slide.shapes.title.text = "The depot"
        slide.shapes.add_picture(str(big), Inches(1), Inches(2), width=Inches(6))
        slide.shapes.add_picture(str(tiny), Inches(0.2), Inches(0.2), width=Inches(0.3))

    prs.save(str(path))
    return path


@unittest.skipUnless(HAS_PPTX, "python-pptx not installed")
class PptxImportTests(TempDirTest):
    def test_text_tables_and_notes_are_preserved(self):
        from doc_engine.pptx_import import pptx_to_deck

        source = build_sample_pptx(self.tmp / "source.pptx")
        deck = pptx_to_deck(source, images_dir=self.tmp / "images")

        self.assertEqual(deck["title"], "Fleet Program Review")
        layouts = [s["layout"] for s in deck["slides"]]
        self.assertEqual(layouts[0], "title")
        self.assertIn("bullets", layouts)
        self.assertIn("table", layouts)

        table = next(s for s in deck["slides"] if s["layout"] == "table")
        self.assertEqual(table["header"], ["Depot", "Riders"])
        self.assertEqual(len(table["rows"]), 2)

        notes = [s.get("notes") for s in deck["slides"] if s.get("notes")]
        self.assertEqual(notes, ["Mention the depots."])

    def test_images_carried_through_and_icons_skipped(self):
        from doc_engine.pptx_import import pptx_to_deck

        source = build_sample_pptx(self.tmp / "source.pptx", with_images=True)
        deck = pptx_to_deck(source, images_dir=self.tmp / "images")

        image_slides = [s for s in deck["slides"] if s.get("image")]
        self.assertEqual(len(image_slides), 1, "the 40px icon should be skipped")
        self.assertTrue(Path(image_slides[0]["image"]).exists())

    def test_converted_deck_inlines_images(self):
        from doc_engine.pptx_import import pptx_to_deck

        source = build_sample_pptx(self.tmp / "source.pptx", with_images=True)
        deck = pptx_to_deck(source, images_dir=self.tmp / "images")
        theme = resolve_theme(SLIDE_TEMPLATE, templates_dir=TEMPLATES, specs_dir=SPECS)
        html = deck_render.render_deck_html(deck, theme)
        self.assertIn("data:image/png;base64,", html)

    def test_empty_presentation_raises(self):
        from pptx import Presentation

        from doc_engine.pptx_import import pptx_to_deck

        empty = self.tmp / "empty.pptx"
        Presentation().save(str(empty))
        with self.assertRaises(ValueError):
            pptx_to_deck(empty)

    def test_corrupt_file_raises_a_clear_error(self):
        """A bad upload should surface as a readable job error, not a
        python-pptx internal."""
        from doc_engine.pptx_import import pptx_to_deck

        bogus = self.tmp / "bogus.pptx"
        bogus.write_bytes(b"not a pptx")
        with self.assertRaises(ValueError) as ctx:
            pptx_to_deck(bogus)
        self.assertIn("bogus.pptx", str(ctx.exception))


if __name__ == "__main__":
    if CHROMIUM is None:
        print("note: no Chromium found — rendering tests will be skipped\n")
    unittest.main(verbosity=2)
