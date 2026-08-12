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


try:
    from PIL import Image  # noqa: F401

    HAS_PIL = True
except ImportError:
    HAS_PIL = False


@unittest.skipUnless(HAS_PIL, "Pillow not installed")
class BrandThemeTests(TempDirTest):
    """Deriving a theme from a logo or screenshot."""

    def _logo(self, background: str, mark: str, name: str = "logo.png") -> Path:
        from PIL import Image, ImageDraw

        path = self.tmp / name
        img = Image.new("RGB", (800, 400), background)
        draw = ImageDraw.Draw(img)
        draw.ellipse([80, 80, 320, 320], fill=mark)
        img.save(path)
        return path

    def test_light_logo_gives_light_stage_and_brand_accent(self):
        from doc_engine.brand import theme_from_image

        theme = theme_from_image(self._logo("#FFFFFF", "#0E7C7B"))
        self.assertEqual(theme.bg, "#ffffff")
        self.assertEqual(theme.accent, "#0e7c7b")

    def test_dark_source_gives_dark_stage(self):
        from doc_engine.brand import theme_from_image

        theme = theme_from_image(self._logo("#12141C", "#FF6B2C"))
        self.assertEqual(theme.bg, "#12141c")
        self.assertEqual(theme.accent, "#ff6b2c")

    def test_text_always_readable_on_the_stage(self):
        """The whole point: never emit a theme whose body text is unreadable."""
        from doc_engine.brand import contrast_ratio, theme_from_image

        for background, mark in [
            ("#FFFFFF", "#0E7C7B"),
            ("#12141C", "#FF6B2C"),
            ("#7A4F9E", "#D62E7A"),  # mid-tone dominant
            ("#FAFAFA", "#111111"),  # near-monochrome
        ]:
            theme = theme_from_image(self._logo(background, mark))

            def rgb(value: str):
                return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))

            ratio = contrast_ratio(rgb(theme.text_color), rgb(theme.bg))
            self.assertGreaterEqual(
                ratio, 4.0, f"{background}/{mark} produced unreadable text"
            )

    def test_near_duplicate_colors_are_merged(self):
        from PIL import Image

        from doc_engine.brand import extract_palette

        # A gradient of near-identical blues should collapse, not flood the
        # palette with 30 shades.
        path = self.tmp / "gradient.png"
        img = Image.new("RGB", (200, 200))
        for x in range(200):
            for y in range(200):
                img.putpixel((x, y), (20, 60, 200 + (x % 4)))
        img.save(path)
        self.assertLessEqual(len(extract_palette(path)), 2)

    def test_spec_round_trips_through_the_normal_loader(self):
        """A synthesized theme must be an ordinary design spec — editable and
        loadable like any hand-written one."""
        from doc_engine.brand import theme_from_image, theme_to_spec
        from doc_engine.theme import load_theme_spec

        original = theme_from_image(self._logo("#FFFFFF", "#0E7C7B"), name="Acme")
        spec_path = self.tmp / "acme.md"
        spec_path.write_text(theme_to_spec(original))

        reloaded = load_theme_spec(spec_path)
        self.assertEqual(reloaded.template, "Acme")
        self.assertEqual(reloaded.accent, original.accent)
        self.assertEqual(reloaded.bg, original.bg)
        self.assertEqual(reloaded.heading_font, original.heading_font)

    def test_unreadable_image_raises(self):
        bogus = self.tmp / "bogus.png"
        bogus.write_bytes(b"not an image")
        from doc_engine.brand import theme_from_image

        with self.assertRaises(Exception):
            theme_from_image(bogus)


class WebfontLoadingTests(unittest.TestCase):
    def test_interactive_decks_do_not_block_paint_on_fonts(self):
        """An external stylesheet blocks first paint; a slow font host must
        not leave a viewer looking at a blank deck."""
        from doc_engine import deck_render

        theme = resolve_theme(DESIGN_SPEC, templates_dir=TEMPLATES, specs_dir=SPECS)
        deck = {"title": "T", "slides": [{"layout": "title", "title": "T"}]}

        interactive = deck_render.render_deck_html(deck, theme)
        self.assertIn('media="print"', interactive)
        self.assertIn("<noscript>", interactive)

        # Printing and measuring must still block, or layout is measured
        # against a fallback face.
        printed = deck_render.render_deck_html(deck, theme, print_mode=True)
        self.assertNotIn('media="print" onload', printed)


def overstuffed_deck() -> dict:
    """A deck built to overflow: a long bullet list, an unsplittable quote,
    and a tall table."""
    return {
        "title": "Overstuffed",
        "slides": [
            {"layout": "title", "title": "Fits fine"},
            {
                "layout": "bullets",
                "heading": "Way too much",
                "items": [
                    "Every one of these bullets is deliberately long so that "
                    f"the list runs past the bottom edge of the canvas {i}"
                    for i in range(12)
                ],
            },
            {
                "layout": "quote",
                "text": "A single enormous quotation that cannot be split "
                "into two slides because it is one continuous sentence, " * 6,
            },
            {
                "layout": "table",
                "heading": "Big table",
                "header": ["A", "B"],
                "rows": [[f"row {i}", f"value {i}"] for i in range(14)],
            },
        ],
    }


class FitSplitTests(unittest.TestCase):
    """Splitting logic — pure functions, no browser needed."""

    def test_split_is_even(self):
        from doc_engine.fit import _split_items

        chunks = _split_items(list(range(12)), 1.84)
        self.assertEqual([len(c) for c in chunks], [6, 6])
        self.assertEqual([item for c in chunks for item in c], list(range(12)))

    def test_split_scales_with_overflow(self):
        from doc_engine.fit import _split_items

        # Three times too tall should divide into three, not two.
        chunks = _split_items(list(range(12)), 2.9)
        self.assertEqual(len(chunks), 3)

    def test_single_item_cannot_split(self):
        from doc_engine.fit import _split_items

        self.assertEqual(_split_items(["only"], 3.0), [["only"]])

    def test_unsplittable_slide_tightens_by_one_step(self):
        from doc_engine.fit import DENSITY_STEPS, _repair_slide

        slide = {"layout": "quote", "text": "x"}
        metrics = {"fillRatio": 1.4}
        first = _repair_slide(slide, metrics)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["density"], DENSITY_STEPS[0])
        second = _repair_slide(first[0], metrics)
        self.assertEqual(second[0]["density"], DENSITY_STEPS[1])

    def test_density_escalation_terminates(self):
        from doc_engine.fit import DENSITY_STEPS, _repair_slide

        slide = {"layout": "quote", "text": "x", "density": DENSITY_STEPS[-1]}
        result = _repair_slide(slide, {"fillRatio": 2.0})
        # Returning the slide unchanged is what stops the outer loop.
        self.assertEqual(result, [slide])

    def test_image_text_splits_into_text_and_image(self):
        from doc_engine.fit import _repair_slide

        slide = {
            "layout": "image_text",
            "heading": "H",
            "image": "/tmp/x.png",
            "items": ["a", "b"],
        }
        result = _repair_slide(slide, {"fillRatio": 1.5})
        self.assertEqual([s["layout"] for s in result], ["bullets", "image"])

    def test_notes_stay_with_the_first_part(self):
        from doc_engine.fit import _repair_slide

        slide = {
            "layout": "bullets",
            "heading": "H",
            "items": [f"item {i}" for i in range(8)],
            "notes": "say this",
        }
        parts = _repair_slide(slide, {"fillRatio": 2.0})
        self.assertGreater(len(parts), 1)
        self.assertEqual(parts[0]["notes"], "say this")
        self.assertTrue(all("notes" not in p for p in parts[1:]))


@needs_chromium
class FitMeasureTests(unittest.TestCase):
    """The measure-and-repair loop against a real browser."""

    def setUp(self) -> None:
        self.theme = resolve_theme(
            SLIDE_TEMPLATE, templates_dir=TEMPLATES, specs_dir=SPECS
        )

    def test_measurement_reports_overflow(self):
        from doc_engine.fit import measure_deck

        metrics = measure_deck(overstuffed_deck(), self.theme, CHROMIUM)
        self.assertEqual(len(metrics), 4)
        self.assertEqual(metrics[0]["overflowY"], 0, "title slide should fit")
        self.assertGreater(metrics[1]["overflowY"], 100, "bullets should overflow")
        self.assertGreater(metrics[3]["overflowY"], 0, "table should overflow")
        for entry in metrics:
            self.assertIn("fillRatio", entry)
            self.assertGreater(entry["usableHeight"], 0)

    def test_repair_makes_every_slide_fit(self):
        from doc_engine.fit import fit_deck, measure_deck

        fixed, report = fit_deck(overstuffed_deck(), self.theme, CHROMIUM)
        self.assertTrue(report["fitted"], f"still overflowing: {report}")
        self.assertGreater(report["slides_after"], report["slides_before"])
        # Verify independently rather than trusting the loop's own report.
        for entry in measure_deck(fixed, self.theme, CHROMIUM):
            self.assertLessEqual(entry["overflowY"], 8)
            self.assertLessEqual(entry["overflowX"], 8)

    def test_content_is_preserved_across_repairs(self):
        from doc_engine.fit import fit_deck

        original = overstuffed_deck()
        fixed, _ = fit_deck(original, self.theme, CHROMIUM)

        def bullets_of(deck):
            return [
                item
                for slide in deck["slides"]
                if slide["layout"] == "bullets"
                for item in slide["items"]
            ]

        self.assertEqual(bullets_of(fixed), bullets_of(original))

    def test_a_deck_that_fits_is_left_alone(self):
        from doc_engine.fit import fit_deck

        deck = {
            "title": "T",
            "slides": [
                {"layout": "title", "title": "Short"},
                {"layout": "bullets", "heading": "Few", "items": ["a", "b"]},
            ],
        }
        fixed, report = fit_deck(deck, self.theme, CHROMIUM)
        self.assertTrue(report["fitted"])
        self.assertEqual(report["repaired"], 0)
        self.assertEqual(report["passes"], 1)
        self.assertEqual(fixed["slides"], deck["slides"])

    def test_measurement_failure_returns_the_original_deck(self):
        """A broken browser must not lose the deck."""
        from doc_engine.fit import fit_deck

        deck = overstuffed_deck()
        fixed, report = fit_deck(deck, self.theme, "/nonexistent/chromium")
        self.assertFalse(report["fitted"])
        self.assertIn("error", report)
        self.assertEqual(fixed["slides"], deck["slides"])


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
