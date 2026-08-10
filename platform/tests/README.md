# Tests

Integration tests for the doc-engine — the part of the platform that can be
exercised without deploying Convex, Modal, or R2. They cover theme resolution
from both sources (slide templates and design specs), all four artifact
paths, PPTX import, and the error paths.

```bash
cd platform
python tests/test_doc_engine.py     # stdlib unittest, no pytest needed
python -m pytest tests -q           # or via pytest
```

Requirements: `pyyaml` (design specs), and optionally `python-docx`,
`python-pptx`, and `pillow`. Tests for a missing dependency skip rather than
fail.

Rendering tests need a Chromium binary. They are skipped when none is found,
so the suite still runs on a machine without one. Resolution order:

1. `CHROMIUM_PATH` environment variable
2. `chromium` / `chromium-browser` / `google-chrome` / `chrome` on `PATH`
3. A Playwright install under `PLAYWRIGHT_BROWSERS_PATH` (default
   `/opt/pw-browsers`)

What is **not** covered here: the Convex functions, the Modal worker, and R2
upload. Those need live services; `../SETUP.md` walks through wiring them up,
and the worker's job routing is thin enough to verify by running one real job
through the dashboard after deploying.
