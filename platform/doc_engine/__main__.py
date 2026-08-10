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

from .pipeline import generate_deck, generate_document


def main() -> None:
    parser = argparse.ArgumentParser(description="Presenton doc-engine")
    parser.add_argument("--artifact", choices=["document", "deck"], default="document")
    parser.add_argument("--template", default="general")
    parser.add_argument("--content", default=None)
    parser.add_argument("--content-file", default=None)
    parser.add_argument("--instructions", default=None)
    parser.add_argument("--formats", default="pdf")
    parser.add_argument("--templates-dir", default="templates")
    parser.add_argument("--specs-dir", default=None)
    parser.add_argument("--out", default="out")
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    args = parser.parse_args()

    if args.content_file:
        content = Path(args.content_file).read_text()
    elif args.content:
        content = args.content
    else:
        print("Provide --content or --content-file", file=sys.stderr)
        sys.exit(2)

    if args.artifact == "deck":
        outputs = generate_deck(
            content=content,
            instructions=args.instructions,
            template=args.template,
            templates_dir=args.templates_dir,
            specs_dir=args.specs_dir,
            out_dir=args.out,
        )
    else:
        outputs = generate_document(
            content=content,
            instructions=args.instructions,
            template=args.template,
            formats=args.formats.split(","),
            templates_dir=args.templates_dir,
            specs_dir=args.specs_dir,
            out_dir=args.out,
            chromium=args.chromium,
        )
    print(json.dumps(outputs, indent=2))


if __name__ == "__main__":
    main()
