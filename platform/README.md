# Presenton Platform

A hosted, multi-tenant layer on top of [Presenton](../README.md) that lets
**AI agents delegate presentation and document creation** over a simple HTTP
API — and extends the product beyond slides to **documents rendered in the
same template aesthetics** (PDF, DOCX, HTML).

| Piece | Tech | Directory |
| --- | --- | --- |
| Backend of record, auth, agent API | Convex + Convex Auth | [`web/convex`](web/convex) |
| Dashboard (keys, jobs, downloads) | Next.js | [`web/app`](web/app) |
| Artifact storage | Cloudflare R2 (free tier, zero egress) | — |
| Compute (Presenton engine + doc-engine) | Modal | [`modal/`](modal) |
| Themed document generation | Python + Chromium | [`doc_engine/`](doc_engine) |

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — how it fits together and why
- **[SETUP.md](SETUP.md)** — step-by-step deployment (~30 min, all free tiers)
- **[doc_engine/DESIGN.md](doc_engine/DESIGN.md)** — the documents roadmap
- **[examples/](examples)** — agent client + sample content

Agent API in two calls:

```bash
POST /agent/v1/jobs        {"kind":"presentation"|"document", "request":{...}}
GET  /agent/v1/jobs/status?id=...   → { status, artifacts:[{format,url}] }
```
