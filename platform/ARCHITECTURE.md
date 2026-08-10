# Presenton Platform — Architecture

Turns self-hosted Presenton into a multi-tenant web service that **AI agents
can delegate presentation and document creation to**.

```
                 ┌────────────────────────────────────────────┐
  AI agent ──────►  Convex (backend of record)                │
  (HTTP+API key) │   • Convex Auth (users, sessions)          │
                 │   • apiKeys / jobs tables                  │
  Browser ───────►  • HTTP actions: /agent/v1/*, callback     │
  (dashboard)    │   • R2 component (presigned URLs)          │
                 └───────────────┬────────────────────────────┘
                                 │ submit (proxy-auth token)
                                 ▼
                 ┌────────────────────────────────────────────┐
                 │  Modal (compute)                           │
                 │   • container from ghcr.io/presenton image │
                 │   • kind=presentation → boots the full     │
                 │     Presenton engine, drives its API       │
                 │   • kind=deck → doc_engine renders a       │
                 │     self-contained interactive HTML deck   │
                 │   • kind=document → doc_engine renders     │
                 │     themed A4 PDF/DOCX/HTML                │
                 └───────────────┬────────────────────────────┘
                                 │ upload artifacts
                                 ▼
                 ┌────────────────────────────────────────────┐
                 │  Cloudflare R2 (S3-compatible storage)     │
                 │   private bucket → presigned download URLs │
                 │   public bucket  → stable shareable links  │
                 │   free tier: 10 GB storage, zero egress    │
                 └────────────────────────────────────────────┘
```

## Components

### `platform/web` — Convex backend + Next.js dashboard

- **Convex Auth** (`convex/auth.ts`) — email+password to start; OAuth
  providers can be added in one line each.
- **Schema** (`convex/schema.ts`) — `apiKeys` (SHA-256 hashed, shown once)
  and `jobs` (kind, status, request, artifacts).
- **Agent HTTP API** (`convex/http.ts`):
  - `POST /agent/v1/jobs` — `Authorization: Bearer sk_pres_…`, body
    `{ kind: "presentation"|"deck"|"document", request: {...} }` →
    `202 { job_id }`.
  - `GET /agent/v1/jobs/status?id=…` — status plus presigned R2 download
    URLs when finished.
  - `POST /modal/callback` — worker completion webhook, HMAC-SHA256 signed
    with `MODAL_CALLBACK_SECRET`.
- **Dispatch** (`convex/dispatch.ts`) — a job insert schedules an action that
  POSTs to the Modal submit endpoint (Modal proxy-auth token headers).
- **R2** via the official `@convex-dev/r2` component — Convex never proxies
  file bytes; it only signs download URLs.
- **Dashboard** (`app/`) — sign in, create/revoke API keys, submit test jobs,
  watch job status live (Convex reactivity — no polling), download results.

### `platform/modal` — compute worker

One Modal app (`worker.py`), two functions:

- `submit` — `@modal.fastapi_endpoint(requires_proxy_auth=True)`; spawns the
  job and immediately returns the call id (Convex marks the job `running`).
- `generate` — runs in a container built **from the official Presenton Docker
  image**, so the entire engine (FastAPI + Next.js renderer + Chromium +
  nginx) is present:
  - `kind=presentation`: boots `node /app/start.js`, waits for health, calls
    the engine's own `POST /api/v1/ppt/presentation/generate`, collects the
    PPTX/PDF.
  - `kind=deck`: runs the doc-engine's deck renderer — no engine boot, so
    these jobs are fast and cheap.
  - `kind=document`: runs `doc_engine` (Chromium only) to render themed
    PDF/DOCX/HTML.
  - Uploads results to R2 with boto3 (plus a public-bucket copy when the job
    set `publish: true`), then POSTs the signed callback.

Jobs are ephemeral and isolated per container invocation — this is the
"sandbox" property: user-supplied content never touches shared state, and the
container is discarded after the job.

### `platform/doc_engine` — decks and documents in the template's aesthetic

The product extension beyond PPTX. Key idea: **a Presenton slide template
already encodes its design system** in `templates/<name>/template.json`
(font files, families, sizes, and every color used). `doc_engine/theme.py`
extracts theme tokens from it:

| Token | Derivation |
| --- | --- |
| heading font | family used at the largest size in the template |
| body font | most frequently used other family |
| accent | most-used saturated, mid-lightness color |
| ink | most-used near-black |
| font files | the template's own bundled TTFs |

`render.py` renders a structured document (sections, paragraphs, bullets,
quotes, stat cards, tables) into print-ready A4 HTML using those tokens;
`export.py` prints it to PDF via headless Chromium (the same rendering
approach the engine uses for slides) and to native DOCX via python-docx.
Content comes either from an LLM step (`llm.py`, any OpenAI-compatible
endpoint) or deterministically from markdown (`structure.py`).

Verified locally: the same markdown brief rendered with `momentum`,
`executive`, `modern`, and `general` correctly picks up each template's
fonts and palette (e.g. Momentum → Anton headings, Lato body, #1A3DB3).

**Themes can also come from design specs** (`platform/design-specs/*.md`) —
~40 lines of YAML declaring colors, semantic aliases, typography roles, and
Google Fonts. A spec is far cheaper to author than a coordinate-based
`template.json`, and can define dark stages that slide templates don't cover.
`resolve_theme()` checks specs first, then falls back to template extraction,
so `momentum` and `midnight-gold` are both just theme names to callers. Specs
cannot drive PPTX export (that needs the engine's layout geometry), so they
apply to `deck` and `document` jobs.

**Interactive HTML decks** (`deck.py` + `deck_render.py`) are a third output.
A deck model (title / section / bullets / prose / stats / quote / table /
closing slides) is rendered into **one self-contained HTML file**: inline CSS
and JS, template fonts embedded as data URIs, no network dependency unless
the theme uses Google Fonts. The canvas is a fixed 1920×1080 stage scaled
uniformly to the viewport — it letterboxes rather than reflowing, so a deck
looks identical on a laptop and a phone. Keyboard, click, and swipe
navigation; staggered entrance animations; a progress bar; deep links via
`#4`; and full `prefers-reduced-motion` support.

Both the fixed-stage technique and the design-spec theme format are adapted
from the MIT-licensed
[frontend-slides](https://github.com/zarazhangrui/frontend-slides) project,
which demonstrated that a declarative spec plus a scaled fixed canvas is
enough to produce distinctive decks without a layout engine.

## Job lifecycle

1. Agent POSTs to `/agent/v1/jobs` with an API key → job `queued`.
2. Convex scheduler runs `dispatch.dispatchToModal` → Modal `submit` →
   job `running` (with `modalCallId`).
3. Modal `generate` produces artifacts, uploads to
   `r2://<bucket>/jobs/<job_id>/…`, POSTs signed callback.
4. Convex verifies the HMAC, marks `succeeded`/`failed`; the dashboard
   updates in real time; agents polling `/agent/v1/jobs/status` receive
   presigned URLs (1-hour TTL).

## Security model

- Agent keys: `sk_pres_` + 40 random chars; only SHA-256 stored; revocable;
  `lastUsedAt` tracked.
- Modal submit endpoint: Modal proxy-auth token (id+secret held in Convex).
- Callback: HMAC-SHA256 over the raw body with a shared secret;
  constant-time comparison.
- Files: private R2 bucket; access only through short-lived presigned URLs
  scoped per job; job ownership checked on every read. `publish: true` is
  opt-in per job and copies that artifact into a separate **public** bucket —
  anything published is world-readable to anyone with the URL, so the API
  never publishes by default.
- Engine containers run with `CAN_CHANGE_KEYS=false` and `DISABLE_AUTH=true`
  (the platform authenticates before Modal is ever invoked; the engine is
  never internet-reachable).

## Why these choices

- **Convex** — auth + database + reactive queries + HTTP endpoints + cron in
  one free-tier service; the dashboard gets live job status without any
  websocket code.
- **Cloudflare R2** — S3-compatible, 10 GB free, and **zero egress fees**,
  which matters for a service whose output is file downloads.
- **Modal** — per-second billed containers with a generous free tier; the
  Presenton image (~heavy: Chromium, LibreOffice, fonts) boots on demand and
  scales to zero; `modal deploy` is the whole CI story.

## Known gaps / next steps

- Modal cold boot of the full engine is slow (image pull + engine start).
  Mitigations: `modal.Volume` for app_data, `min_containers=1` when traffic
  justifies it, or slimming the engine image to FastAPI+renderer only.
  `deck` and `document` jobs skip the engine entirely and are much faster.
- The engine's LLM keys currently come from the Modal secret (platform-wide).
  Per-tenant BYO keys would be passed through the job request instead.
- `GET /agent/v1/jobs/status` polling works everywhere; a webhook-out option
  for agents (platform → agent callback URL) is a natural addition.
- Doc-engine phase 2 (see `doc_engine/DESIGN.md`): move document layouts into
  the Next.js renderer as React components so documents become editable in
  the Presenton UI exactly like slides.
- Style previews ("show, don't tell"): a cheap job kind that renders 3 title
  slides in different themes so a human or agent can pick before committing
  to a full generation. Not built yet.
- Deck → PDF: screenshot each slide via Chromium and combine, for users who
  want a static copy of an HTML deck.
