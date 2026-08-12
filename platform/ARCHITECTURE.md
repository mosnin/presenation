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
                 │     self-contained HTML deck (+PDF), or    │
                 │     converts an uploaded .pptx             │
                 │   • kind=style_preview → title-slide PNGs  │
                 │     across themes, for picking a look      │
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
    `{ kind: "presentation"|"deck"|"document"|"style_preview",
    request: {...} }` →
    `202 { job_id }`.
  - `GET /agent/v1/jobs/status?id=…` — status plus presigned R2 download
    URLs when finished.
  - `POST /agent/v1/jobs/cancel` / `…/retry` — cancel a queued or running
    job (its late callback is then ignored), or resubmit a request as a new
    job.
  - `POST /modal/callback` — worker completion webhook, HMAC-SHA256 signed
    with `MODAL_CALLBACK_SECRET`.
- **Validation** (`convex/validate.ts`) — per-kind request checks run at
  submit time, so a bad field returns an immediate 400 naming it rather than
  failing inside the worker minutes later. Also rejects design-spec themes
  for `presentation` (they cannot produce PPTX) and non-public
  `source_pptx_url` values, since the worker fetches that URL server-side.
- **Rate limiting** (`jobs.checkRateLimit`) — 12 jobs/minute and 60/hour per
  account, counted from recent job rows rather than a counter table, so
  there are no extra writes and no window to reset.
- **Stale-job reaper** (`convex/crons.ts` → `jobs.reapStale`) — every 10
  minutes, jobs stuck in `queued`/`running` for 45 minutes are failed with an
  explanatory error. Without it a lost Modal callback would leave a job
  running forever.
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
    these jobs are fast and cheap. `formats` may include `pdf` (a paged
    16:9 print of the same deck, text still selectable), and
    `source_pptx_url` converts an existing deck instead of generating one.
  - `kind=style_preview`: screenshots one title slide per candidate theme.
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
`#4`; and full `prefers-reduced-motion` support. A print variant of the same
renderer emits one 16:9 page per slide, so `formats: ["pdf"]` produces a
static deck with selectable text rather than screenshots.

**Existing decks convert in** (`pptx_import.py`): python-pptx pulls titles,
bullet structure, tables, speaker notes, and embedded images out of a
`.pptx` and maps them onto the deck model, so a deck someone already has can
be re-typeset in any theme. Pictures are downscaled and inlined as data URIs
(the deck stays one file); images under 80px are skipped as icons or
spacers. Original positioning is deliberately dropped — the value is a
coherent design system, not a photocopy.

**Style previews** (`preview.py`) render the same title slide across
candidate themes as PNGs, so the choice of look is made by looking rather
than by guessing from a theme name.

Both the fixed-stage technique and the design-spec theme format are adapted
from the MIT-licensed
[frontend-slides](https://github.com/zarazhangrui/frontend-slides) project,
which demonstrated that a declarative spec plus a scaled fixed canvas is
enough to produce distinctive decks without a layout engine.

### `platform/tests` — what is actually verified

`web/convex/validate.test.ts` covers the agent-API request validation
(19 tests, including the SSRF host rules); it compiles and runs standalone
because `validate.ts` has no Convex imports — `cd platform/web && npm test`.

`tests/test_doc_engine.py` covers the layer that runs without live services:
theme resolution from both sources (including the print-safety rules), the
markdown and deck models, HTML/PDF/DOCX rendering, style previews, PPTX
import with images, and the error paths (unknown theme, empty deck, corrupt
file, missing image, HTML escaping). Rendering tests skip when no Chromium is
present, so the suite still runs on a machine without one. CI runs it on
every push touching `platform/` or `templates/`.

Not covered by tests: the Convex functions, the Modal worker, and R2 upload —
those need live services. The worker's job routing is thin, so the practical
check is running one real job per kind through the dashboard after deploying.

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
- Inlining images keeps decks self-contained but inflates them; an
  image-heavy conversion can reach several MB. Serving images from R2 and
  referencing them would trade portability for size.
- Style previews render the title slide only; a second preview slide (a
  content layout) would show more of each theme's personality.
- Converted decks map source formatting onto bullets; inferring stats and
  quote layouts from the original would read better.
