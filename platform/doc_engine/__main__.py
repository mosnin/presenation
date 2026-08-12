"""CLI for local testing:

    python -m doc_engine --template momentum --formats pdf,docx \
        --content-file brief.md --out out/
    python -m doc_engine --artifact deck --template midnight-gold \
        --content-file brief.md --out out/
"""

import argparse
import json
import sys
from pathlib import Path

from .pipeline import generate_deck, generate_document, generate_style_previews


def main() -> None:
    parser = argparse.ArgumentParser(description="Presenton doc-engine")
    parser.add_argument(
        "--artifact",
        choices=["document", "deck", "previews"],
        default="document",
    )
    parser.add_argument("--from-pptx", default=None, help="convert an existing .pptx")
    parser.add_argument(
        "--brand-image",
        default=None,
        help="derive the theme from a logo/screenshot instead of --template",
    )
    parser.add_argument("--themes", default=None, help="comma-separated, for previews")
    parser.add_argument(
        "--no-fit",
        action="store_true",
        help="skip the measure-and-repair layout pass (decks only)",
    )
    parser.add_argument("--template", default="general")
    parser.add_argument("--content", default=None)
    parser.add_argument("--content-file", default=None)
    parser.add_argument("--instructions", default=None)
    # Defaults differ by artifact: pdf for documents, html for decks.
    parser.add_argument("--formats", default=None)
    parser.add_argument("--templates-dir", default="templates")
    parser.add_argument("--specs-dir", default=None)
    parser.add_argument("--out", default="out")
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    args = parser.parse_args()

    if args.content_file:
        content = Path(args.content_file).read_text()
    elif args.content:
        content = args.content
    elif args.from_pptx:
        content = ""  # content comes from the source deck
    else:
        print("Provide --content, --content-file, or --from-pptx", file=sys.stderr)
        sys.exit(2)

    if args.artifact == "previews":
        # A preview needs one title line; take the first line of the content
        # (dropping a leading markdown heading marker).
        lines = [line for line in content.strip().splitlines() if line.strip()]
        outputs = generate_style_previews(
            title=lines[0].lstrip("# ").strip() if lines else "Untitled",
            themes=args.themes.split(",") if args.themes else None,
            templates_dir=args.templates_dir,
            specs_dir=args.specs_dir,
            out_dir=args.out,
            chromium=args.chromium,
        )
    elif args.artifact == "deck":
        outputs = generate_deck(
            content=content,
            instructions=args.instructions,
            template=args.template,
            templates_dir=args.templates_dir,
            specs_dir=args.specs_dir,
            out_dir=args.out,
            formats=args.formats.split(",") if args.formats else ["html"],
            source_pptx=args.from_pptx,
            chromium=args.chromium,
            fit=not args.no_fit,
            brand_image=args.brand_image,
        )
    else:
        outputs = generate_document(
            content=content,
            instructions=args.instructions,
            template=args.template,
            formats=args.formats.split(",") if args.formats else ["pdf"],
            templates_dir=args.templates_dir,
            specs_dir=args.specs_dir,
            out_dir=args.out,
            chromium=args.chromium,
            brand_image=args.brand_image,
        )
    print(json.dumps(outputs, indent=2))


if __name__ == "__main__":
    main()
