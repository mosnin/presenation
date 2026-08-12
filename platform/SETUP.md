# Presenton Platform — Setup

Three free-tier accounts are needed: [Convex](https://convex.dev),
[Cloudflare R2](https://developers.cloudflare.com/r2/), and
[Modal](https://modal.com). Roughly 30 minutes end to end.

## 1. Cloudflare R2

1. Cloudflare dashboard → **R2** → create bucket `presenton-artifacts`
   (keep it private; free tier: 10 GB storage, zero egress fees).
2. *Optional, for `publish: true`* — create a second bucket
   `presenton-public`, open its **Settings → Public access**, and either
   enable the `r2.dev` development URL or connect a custom domain. Note the
   resulting base URL (e.g. `https://pub-xxxx.r2.dev`). Skip this and
   published jobs simply return no public URL.
3. **R2 → Manage API tokens → Create API token** with *Object Read & Write*
   on those buckets. Note the **Access Key ID**, **Secret Access Key**, and
   your account's S3 endpoint: `https://<account-id>.r2.cloudflarestorage.com`.

## 2. Convex + dashboard

```bash
cd platform/web
npm install
npx convex dev          # creates the deployment, generates convex/_generated
```

`npx convex dev` prints your deployment URL; put it in `.env.local`:

```
NEXT_PUBLIC_CONVEX_URL=https://<deployment>.convex.cloud
```

Initialize Convex Auth (generates JWT keys):

```bash
npx @convex-dev/auth
```

Set backend configuration:

```bash
npx convex env set SITE_URL http://localhost:3000
npx convex env set R2_ENDPOINT https://<account-id>.r2.cloudflarestorage.com
npx convex env set R2_ACCESS_KEY_ID <key-id>
npx convex env set R2_SECRET_ACCESS_KEY <secret>
npx convex env set R2_BUCKET presenton-artifacts
npx convex env set MODAL_CALLBACK_SECRET "$(openssl rand -hex 32)"
```

Run the dashboard:

```bash
npm run dev             # http://localhost:3000
```

## 3. Modal worker

```bash
pip install modal
modal setup             # authenticates your workspace
```

Create the worker secret (engine config uses the same names as the repo root
`.env.example`; R2 values are the ones from step 1; the callback secret must
match the Convex one):

```bash
modal secret create presenton-worker \
  LLM=openai \
  OPENAI_API_KEY=sk-... \
  IMAGE_PROVIDER=pexels \
  PEXELS_API_KEY=... \
  R2_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com \
  R2_ACCESS_KEY_ID=<key-id> \
  R2_SECRET_ACCESS_KEY=<secret> \
  R2_BUCKET=presenton-artifacts \
  MODAL_CALLBACK_SECRET=<same-value-as-convex>
```

Add these two as well if you created the public bucket in step 1.2:

```bash
  R2_PUBLIC_BUCKET=presenton-public \
  R2_PUBLIC_BASE_URL=https://pub-xxxx.r2.dev
```

Deploy (from the repo root, so the image can bundle `platform/doc_engine`
and `templates/`):

```bash
modal deploy platform/modal/worker.py
```

Note the printed URL of the `submit` endpoint. Then create a **proxy auth
token** (Modal dashboard → Settings → Proxy Auth Tokens) and hand everything
to Convex:

```bash
npx convex env set MODAL_SUBMIT_URL https://<workspace>--presenton-worker-submit.modal.run
npx convex env set MODAL_PROXY_TOKEN_ID wk-...
npx convex env set MODAL_PROXY_TOKEN_SECRET ws-...
```

## 4. Try it

1. Open the dashboard → sign up → **API keys** → create a key.
2. As an agent:

```bash
# Submit
curl -X POST https://<deployment>.convex.site/agent/v1/jobs \
  -H "Authorization: Bearer sk_pres_..." \
  -H "Content-Type: application/json" \
  -d '{"kind":"document","request":{"content":"One-page brief on X","template":"momentum","formats":["pdf","docx"]}}'

# Poll (returns presigned download URLs when finished)
curl "https://<deployment>.convex.site/agent/v1/jobs/status?id=<job_id>" \
  -H "Authorization: Bearer sk_pres_..."
```

Or run `python platform/examples/agent_client.py`.

To let a coding agent drive the API, point it at
[`platform/SKILL.md`](SKILL.md) — it documents auth, the four job kinds, the
themes, and the polling loop. For Claude Code, copying that file to
`~/.claude/skills/presenton-platform/SKILL.md` installs it as a skill.

Note the two Convex URLs: `*.convex.cloud` is the client API
(`NEXT_PUBLIC_CONVEX_URL`), while HTTP endpoints (`/agent/v1/*`) live on
`*.convex.site`.

## 5. Deploy the dashboard (optional)

Any Next.js host works; Vercel free tier is the shortest path:
set `NEXT_PUBLIC_CONVEX_URL`, run `npx convex deploy` for production, and
update `SITE_URL` in the production deployment's env.

## Tests

```bash
cd platform
pip install pyyaml python-docx python-pptx pillow
python tests/test_doc_engine.py
```

Covers theme resolution, all four artifact paths, PPTX import, and the error
paths. Rendering tests skip if no Chromium is found (set `CHROMIUM_PATH` to
point at one). CI runs the same suite on every push touching `platform/`.
See [`tests/README.md`](tests/README.md).

## Local development without Modal

The doc-engine runs standalone:

```bash
pip install python-docx python-pptx pyyaml
cd platform

# A4 document in a slide template's aesthetic
python -m doc_engine --template momentum \
  --content-file examples/brief.md --formats pdf,docx,html \
  --templates-dir ../templates --specs-dir design-specs \
  --out /tmp/doc-out --chromium /usr/bin/chromium

# Interactive HTML deck in a design-spec theme
python -m doc_engine --artifact deck --template midnight-gold \
  --content-file examples/brief.md \
  --templates-dir ../templates --specs-dir design-specs \
  --out /tmp/deck-out
open /tmp/deck-out/deck.html   # arrows/space to navigate

# Same deck as a static PDF (one 16:9 page per slide, selectable text)
python -m doc_engine --artifact deck --template midnight-gold \
  --content-file examples/brief.md --formats html,pdf \
  --templates-dir ../templates --specs-dir design-specs \
  --out /tmp/deck-out --chromium /usr/bin/chromium

# Style previews: one title-slide PNG per theme
python -m doc_engine --artifact previews --content "Q3 Sales Report" \
  --themes momentum,midnight-gold,swiss-crimson \
  --templates-dir ../templates --specs-dir design-specs \
  --out /tmp/previews --chromium /usr/bin/chromium

# Deck themed from a brand image (logo, screenshot) instead of a template
python -m doc_engine --artifact deck --brand-image ~/logo.png \
  --content-file examples/brief.md \
  --templates-dir ../templates --specs-dir design-specs --out /tmp/branded

# Convert an existing PowerPoint into a themed web deck
python -m doc_engine --artifact deck --from-pptx ~/existing.pptx \
  --template paper-zine --formats html \
  --templates-dir ../templates --specs-dir design-specs --out /tmp/converted
```
