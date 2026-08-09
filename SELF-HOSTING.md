# Self-Hosting Presenton

> **Looking for the hosted multi-tenant platform?** The agent-facing web
> service built on Convex + Cloudflare R2 + Modal — including document
> generation in the template aesthetics — lives in [`platform/`](platform/README.md).

Presenton is an open-source (Apache 2.0) AI presentation generator — a
self-hosted alternative to Gamma / Canva / Beautiful.ai. It generates fully
editable PPTX and PDF decks from a prompt or an uploaded document, using
whichever LLM provider you configure (OpenAI, Anthropic, Google, Ollama,
LM Studio, or any OpenAI-compatible endpoint), and exposes a generation API
and an MCP server on top.

This file is the shortest path to running it on your own machine or server.
The full reference (every variable, every provider) is in [README.md](README.md)
under **Deployment Configurations**.

## Quick start (prebuilt image — recommended)

Requirements: Docker with the compose plugin.

```bash
# 1. Configure
cp .env.example .env
# Edit .env: set at minimum LLM + its API key, IMAGE_PROVIDER + its key,
# and AUTH_USERNAME / AUTH_PASSWORD for the admin account.

# 2. Run the official prebuilt image
docker run -d --name presenton \
  -p 5001:80 \
  --env-file .env \
  -v "./app_data:/app_data" \
  ghcr.io/presenton/presenton:latest

# 3. Open the app
# http://localhost:5001
```

All state (database, uploads, generated decks, config) lives in `./app_data`,
so back that directory up and you can recreate the container freely.

## Build and run from this repository

To run the code in this repo instead of the published image:

```bash
cp .env.example .env   # then edit it
docker compose up -d production
```

The first build takes a while (it builds the Next.js frontend and FastAPI
backend and installs Chromium for PPTX/PDF export). Other compose services:

- `production-gpu` — same, with GPU access for local models
- `development` / `development-gpu` — hot-reload dev servers

Change the port with `PRESENTON_HTTP_HOST_PORT` in `.env`.

## Minimal configuration

Only three things are genuinely required:

| Setting | Why |
| --- | --- |
| `LLM` + that provider's API key | Text generation (e.g. `LLM=openai` + `OPENAI_API_KEY`) |
| `IMAGE_PROVIDER` + its key | Slide images — `pexels` or `pixabay` are free stock-photo APIs; or set `DISABLE_IMAGE_GENERATION=true` |
| `AUTH_USERNAME` / `AUTH_PASSWORD` | Creates the primary admin on first boot (or use the in-browser setup screen) |

Free/local setup with no paid APIs: `LLM=ollama` with `OLLAMA_URL` pointing at
an Ollama instance (`http://host.docker.internal:11434` from inside Docker) and
`IMAGE_PROVIDER=pexels` (free key) or `DISABLE_IMAGE_GENERATION=true`.

## Exposing it on the internet

- Put a reverse proxy (Caddy, nginx, Traefik) with HTTPS in front of port 5001.
- Set `CAN_CHANGE_KEYS=false` so visitors can't read or change your API keys.
- Keep auth enabled; the first account is the administrator and can manage
  other users under **Admin → Users**.
- API/MCP access uses admin-generated `sk-presenton-...` keys
  (**Admin → API keys**), not browser sessions.

## API and MCP

- Presentation generation API: `POST /api/v1/ppt/presentation/generate`
  (see docs at https://docs.presenton.ai)
- MCP endpoint: `http://localhost:5001/mcp` with an
  `Authorization: Bearer sk-presenton-...` header.

## Updating

```bash
docker pull ghcr.io/presenton/presenton:latest   # prebuilt image
# or: git pull && docker compose build production
docker compose up -d production
```

Database migrations run automatically on startup
(`MIGRATE_DATABASE_ON_STARTUP=true`).
