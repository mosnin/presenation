---
name: presenton-platform
description: Delegate presentation and document creation to a Presenton Platform instance. Use when the user asks for a slide deck, PPTX, pitch deck, report, brief, one-pager, or PDF/DOCX/HTML document, wants an existing PowerPoint converted to a web deck, or wants to compare visual styles — and a PRESENTON_API_KEY is available. The platform generates the file remotely and returns a download URL — no local rendering, no PowerPoint install.
---

# Presenton Platform

Generate presentations and documents by calling a hosted API. You submit a
job, poll until it finishes, and hand the user a URL.

## Configuration

Two values must be available in the environment:

- `PRESENTON_PLATFORM_URL` — the deployment's HTTP endpoint, ending in
  `.convex.site` (note: **not** the `.convex.cloud` client URL).
- `PRESENTON_API_KEY` — an `sk_pres_…` key from the dashboard's **API keys**
  page.

If either is missing, stop and tell the user how to get them rather than
guessing a URL. Never print the key back to the user or write it into files.

## Workflow

1. **Pick the artifact kind** (see the table below). If the user's intent is
   ambiguous between a deck and a document, ask — the outputs are very
   different.
2. **Pick a theme.** Ask if the user has a preference; otherwise choose one
   that fits the content and say which you picked.
3. **Submit the job**, then **poll** until `status` is `succeeded` or
   `failed`.
4. **Give the user the URL.** Presigned download URLs expire after one hour;
   mention that. If the job was published, give the public URL instead — it
   is stable.

## Choosing the kind

| Kind | Produces | Use for |
| --- | --- | --- |
| `presentation` | `.pptx` or `.pdf` | Anything the user will open in PowerPoint/Keynote or needs to edit later. The default for "slide deck". |
| `deck` | self-contained `.html` and/or `.pdf` | Something to present in a browser or share as a link. Keyboard/touch navigation, animated. Also converts an existing `.pptx`. Not editable in PowerPoint. |
| `document` | `.pdf`, `.docx`, `.html` | Reports, briefs, one-pagers, memos — prose in A4, not slides. |
| `style_preview` | one `.png` per theme | Deciding what it should look like, before generating anything real. |

### Style previews first, when the look matters

If the user cares about the design and hasn't named a theme, submit a
`style_preview` job before the real one. It returns a title-slide PNG per
theme, each tagged with `theme`. Show those to the user, let them pick, then
submit the real job with that `template`. This is much cheaper than
generating three full decks. Skip it when the user already named a theme or
just wants the file.

## Themes

Slide templates (work with every kind, and the only ones that support PPTX):
`general`, `momentum`, `modern`, `executive`, `dynamic`, `standard`, `swift`.

Design specs (for `deck` and `document` only):
`midnight-gold` (dark, gold italic serif — scholarly),
`paper-zine` (cream paper, red accent — informal),
`swiss-crimson` (off-white, grotesk, crimson — institutional).

Passing a design spec to `kind: "presentation"` fails; use `deck` instead.

**On-brand without a theme:** for `deck` and `document`, pass
`brand_image_url` (a public https URL to a logo, screenshot, or product
image) instead of `template`. The palette is derived from the image — stage,
accent, and a text color checked for readable contrast. Use this when the
user wants it to match their brand and hasn't named a template. It does not
apply to `presentation` (PPTX needs a real slide template).

## Submitting a job

```bash
curl -sS -X POST "$PRESENTON_PLATFORM_URL/agent/v1/jobs" \
  -H "Authorization: Bearer $PRESENTON_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
        "kind": "presentation",
        "request": {
          "content": "Series A pitch for an AI logistics startup",
          "template": "momentum",
          "n_slides": 8,
          "export_as": "pptx"
        }
      }'
```

Returns `202 {"job_id": "...", "status": "queued"}`.

### Request fields by kind

All kinds take `content` (the prompt or the source material), optional
`instructions` (tone, audience, emphasis), optional `template`, and optional
`publish: true` (also place the file at a stable public URL — only do this
when the user wants a shareable link, since the file becomes world-readable
to anyone with the URL).

- `presentation`: `export_as` (`"pptx"` | `"pdf"`, default `pptx`),
  `n_slides` (omit to let the model choose), `language`, `tone`.
- `deck`: `formats` (array of `"html"`, `"pdf"`; default `["html"]`),
  `fit` (default true — every slide is measured in a real browser and
  overflowing content is split across slides or tightened, so decks never
  ship with clipped text; set false only if you need the slide count to
  match your input exactly), and
  `source_pptx_url` — a URL to an existing `.pptx` to convert instead of
  generating. Conversion keeps text, bullets, tables, speaker notes, and
  embedded images; exact positioning is not carried over, since the point is
  to re-typeset the content in a coherent design system.
- `document`: `formats` (array of `"pdf"`, `"docx"`, `"html"`; default
  `["pdf"]`).
- `style_preview`: `title` (required), `subtitle`, `meta`, and `themes` (an
  array; omit for a spread across light/dark and serif/sans). Ignores
  `template` — it renders every candidate.

### Editing a deck instead of regenerating it

Every `deck` job also returns its model as a `json` artifact (`deck.json`).
To change something, fetch that, then submit a new `deck` job with `deck`
set to the model and `patch` set to a list of edits — the untouched slides
come back byte-identical, and it costs no model call.

```json
{"kind": "deck", "request": {
  "deck": { ...deck.json... },
  "patch": [
    {"op": "set_item", "slide": 3, "index": 1, "value": "Margin 43%"},
    {"op": "delete", "slide": 6},
    {"op": "insert", "index": 7, "value": {"layout": "section", "heading": "Outlook"}}
  ],
  "template": "momentum"
}}
```

Operations: `set` (slide, field, value), `set_item` (slide, index, value),
`replace` (slide, value), `insert` (index, value), `delete` (slide), `move`
(from, to), `set_meta` (field, value). Slide indexes are 0-based and always
refer to the deck **as you read it** — a batch of edits doesn't shift its own
indexes. Any invalid operation rejects the whole patch, so a partial edit
never lands.

Prefer this over regenerating whenever the user asks for a specific change
("fix the number on slide 4", "drop the pricing slide", "move the summary to
the front"). Regenerate only when they want different content.

## Polling

```bash
curl -sS "$PRESENTON_PLATFORM_URL/agent/v1/jobs/status?id=$JOB_ID" \
  -H "Authorization: Bearer $PRESENTON_API_KEY"
```

`status` is `queued`, `running`, `succeeded`, or `failed`. On success:

```json
{
  "job_id": "...",
  "kind": "presentation",
  "status": "succeeded",
  "artifacts": [
    { "format": "pptx", "url": "https://…", "public_url": "https://…" }
  ]
}
```

`style_preview` results carry a `theme` on each artifact:

```json
{ "artifacts": [
  { "format": "png", "theme": "momentum", "url": "https://…" },
  { "format": "png", "theme": "midnight-gold", "url": "https://…" }
] }
```

Poll about every 5 seconds. Generation normally takes 30-90 seconds, and the
first job after an idle period is slower because the worker container has to
cold-start — wait at least 5 minutes before treating a `running` job as
stuck. On `failed`, report the `error` field to the user; do not silently
retry more than once.

A job that never reports back is failed automatically after 45 minutes, so
`running` is never permanent.

## Cancelling and retrying

```bash
POST /agent/v1/jobs/cancel   {"job_id": "..."}   # 409 if already finished
POST /agent/v1/jobs/retry    {"job_id": "..."}   # 202, returns a NEW job_id
```

Cancelling does not interrupt a worker that is already running; it discards
the result. Retry resubmits the same request as a new job — use it after a
timeout, not after a validation error (that will fail the same way).

## Error responses

| Status | Meaning | What to do |
| --- | --- | --- |
| 400 | The request is malformed; the `error` field names the problem | Fix and resubmit — do not retry unchanged |
| 401 | Bad or missing API key | Stop and tell the user |
| 404 | No such job for this key | Stop |
| 429 | Rate limited (12/minute, 60/hour per account) | Wait `retry_after_seconds`, then continue |

Submissions are validated up front, so mistakes come back immediately rather
than as a failed job minutes later. Common 400s: `content` missing, a design
spec passed to `kind: "presentation"` (use `deck`), an unsupported `formats`
entry, or a `source_pptx_url` that isn't a public https URL.

## Notes

- One job produces one artifact set; to make three decks, submit three jobs
  (they run concurrently).
- `content` can be a long document — paste the source material in rather than
  summarizing it first, and let the platform do the summarizing.
- Writing `content` as markdown pays off: `- Revenue: $4.2M` style lines
  become stat cards, `- Q1 2026: Launch` runs become a timeline, and a `>`
  quote ending in `— Name` keeps its attribution. Plain sentences stay
  bullets.
- Do not fabricate a download URL or claim a file exists before a job reports
  `succeeded`.
- A ready-made polling client is in `examples/agent_client.py`.
