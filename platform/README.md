# Presenton Platform

A hosted, multi-tenant layer on top of [Presenton](../README.md) that lets
**AI agents delegate presentation and document creation** over a simple HTTP
API — and extends the product beyond PPTX to **interactive HTML decks** and
**A4 documents**, all rendered in the same template aesthetics.

| Piece | Tech | Directory |
| --- | --- | --- |
| Backend of record, auth, agent API | Convex + Convex Auth | [`web/convex`](web/convex) |
| Dashboard (keys, jobs, downloads) | Next.js | [`web/app`](web/app) |
| Artifact storage + public publishing | Cloudflare R2 (free tier, zero egress) | — |
| Compute (Presenton engine + doc-engine) | Modal | [`modal/`](modal) |
| Themed document & deck generation | Python + Chromium | [`doc_engine/`](doc_engine) |
| Theme definitions | YAML design specs | [`design-specs/`](design-specs) |

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — how it fits together and why
- **[SETUP.md](SETUP.md)** — step-by-step deployment (~30 min, all free tiers)
- **[SKILL.md](SKILL.md)** — drop-in instructions so any coding agent can use the API
- **[doc_engine/DESIGN.md](doc_engine/DESIGN.md)** — the documents/decks roadmap
- **[examples/](examples)** — agent client + sample content

Three artifact kinds:

| Kind | Output | Engine |
| --- | --- | --- |
| `presentation` | editable `.pptx` / `.pdf` | Presenton engine on Modal |
| `deck` | one self-contained interactive `.html` | doc-engine deck renderer |
| `document` | A4 `.pdf` / `.docx` / `.html` | doc-engine |

Agent API in two calls:

```bash
POST /agent/v1/jobs   {"kind":"deck","request":{"content":"…","template":"midnight-gold"}}
GET  /agent/v1/jobs/status?id=…  → { status, artifacts:[{format,url,public_url?}] }
```

Add `"publish": true` to any request to also place the artifact at a stable
public URL.

## Credits

The interactive deck renderer's fixed-stage approach (a 1920×1080 canvas
scaled uniformly to the viewport rather than reflowed) and the YAML design-spec
theme format are adapted from
[frontend-slides](https://github.com/zarazhangrui/frontend-slides) by
[@zarazhangrui](https://github.com/zarazhangrui), MIT licensed. The design
specs in `design-specs/` and all code here are original to this repository.
