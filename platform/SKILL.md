---
name: presenton-platform
description: Delegate presentation and document creation to a Presenton Platform instance. Use when the user asks for a slide deck, PPTX, pitch deck, report, brief, one-pager, or PDF/DOCX/HTML document and a PRESENTON_API_KEY is available. The platform generates the file remotely and returns a download URL — no local rendering, no PowerPoint install.
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
| `deck` | one self-contained `.html` file | Something to present in a browser or share as a link. Keyboard/touch navigation, animated. Not editable in PowerPoint. |
| `document` | `.pdf`, `.docx`, `.html` | Reports, briefs, one-pagers, memos — prose in A4, not slides. |

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
- `deck`: no extra fields.
- `document`: `formats` (array of `"pdf"`, `"docx"`, `"html"`; default
  `["pdf"]`).

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
