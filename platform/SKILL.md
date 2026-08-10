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
- `deck`: `formats` (array of `"html"`, `"pdf"`; default `["html"]`) and
  `source_pptx_url` — a URL to an existing `.pptx` to convert instead of
  generating. Conversion keeps text, bullets, tables, and speaker notes;
  original images and exact positioning are not carried over, since the
  point is to re-typeset the content in a coherent design system.
- `document`: `formats` (array of `"pdf"`, `"docx"`, `"html"`; default
  `["pdf"]`).
- `style_preview`: `title` (required), `subtitle`, `meta`, and `themes` (an
  array; omit for a spread across light/dark and serif/sans). Ignores
  `template` — it renders every candidate.

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

## Notes

- One job produces one artifact set; to make three decks, submit three jobs
  (they run concurrently).
- `content` can be a long document — paste the source material in rather than
  summarizing it first, and let the platform do the summarizing.
- Do not fabricate a download URL or claim a file exists before a job reports
  `succeeded`.
- A ready-made polling client is in `examples/agent_client.py`.
