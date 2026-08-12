"""Modal worker for the Presenton platform.

Runs generation jobs inside Modal containers built from the official
Presenton Docker image, uploads the resulting files to Cloudflare R2, and
reports completion back to the Convex backend via a signed webhook.

Deploy:
    modal deploy platform/modal/worker.py

Requires a Modal secret named `presenton-worker` containing:
    LLM / OPENAI_API_KEY / IMAGE_PROVIDER / ... (engine config, same names
        as the repo root .env.example — the engine runs headless here, so
        CAN_CHANGE_KEYS is forced to false)
    R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
    R2_PUBLIC_BUCKET, R2_PUBLIC_BASE_URL (optional; enable `publish: true`)
    MODAL_CALLBACK_SECRET (same value as the Convex env var)

The submit endpoint is protected with Modal proxy auth: create a proxy auth
token in the Modal dashboard and give its id/secret to Convex as
MODAL_PROXY_TOKEN_ID / MODAL_PROXY_TOKEN_SECRET.
"""

import hashlib
import hmac
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import modal

REPO_ROOT = Path(__file__).parent.parent.parent

ENGINE_PORT = 80
ENGINE_URL = f"http://127.0.0.1:{ENGINE_PORT}"
ENGINE_BOOT_TIMEOUT_S = 240

# The official Presenton image carries the whole engine (FastAPI + Next.js +
# nginx + Chromium). We add python deps for R2 upload and the doc-engine, and
# bake in this repo's doc_engine package and templates (for theme tokens).
image = (
    modal.Image.from_registry(
        "ghcr.io/presenton/presenton:latest", add_python="3.11"
    )
    .pip_install(
        "boto3~=1.34",
        "fastapi[standard]",
        "python-docx",
        "python-pptx",
        "pillow",
        "pyyaml",
    )
    .add_local_dir(str(REPO_ROOT / "platform" / "doc_engine"), "/opt/doc_engine")
    .add_local_dir(str(REPO_ROOT / "templates"), "/opt/presenton-templates")
    .add_local_dir(
        str(REPO_ROOT / "platform" / "design-specs"), "/opt/presenton-design-specs"
    )
)

app = modal.App("presenton-worker")

worker_secret = modal.Secret.from_name("presenton-worker")


def _r2_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _upload_to_r2(local_path: Path, r2_key: str) -> int:
    client = _r2_client()
    size = local_path.stat().st_size
    extra = {}
    content_type = _CONTENT_TYPES.get(local_path.suffix.lower())
    if content_type:
        extra["ContentType"] = content_type
    client.upload_file(
        str(local_path), os.environ["R2_BUCKET"], r2_key, ExtraArgs=extra or None
    )
    return size


def _publish_to_r2(local_path: Path, r2_key: str) -> str | None:
    """Copy an artifact into the public R2 bucket and return its stable URL.

    Requires R2_PUBLIC_BUCKET (a bucket with public access / custom domain)
    and R2_PUBLIC_BASE_URL (e.g. https://pub-xxxx.r2.dev or your domain).
    Returns None when publishing is not configured.
    """
    bucket = os.environ.get("R2_PUBLIC_BUCKET")
    base_url = os.environ.get("R2_PUBLIC_BASE_URL", "").rstrip("/")
    if not bucket or not base_url:
        return None
    client = _r2_client()
    extra = {}
    content_type = _CONTENT_TYPES.get(local_path.suffix.lower())
    if content_type:
        extra["ContentType"] = content_type
    client.upload_file(str(local_path), bucket, r2_key, ExtraArgs=extra or None)
    return f"{base_url}/{r2_key}"


def _callback(callback_url: str, payload: dict) -> None:
    body = json.dumps(payload).encode()
    signature = hmac.new(
        os.environ["MODAL_CALLBACK_SECRET"].encode(), body, hashlib.sha256
    ).hexdigest()
    req = urllib.request.Request(
        callback_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Presenton-Signature": signature,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        res.read()


def _boot_engine() -> subprocess.Popen:
    """Start the Presenton engine exactly as the Docker image would."""
    env = dict(os.environ)
    env.setdefault("APP_DATA_DIRECTORY", "/app_data")
    env["CAN_CHANGE_KEYS"] = "false"
    env.setdefault("MIGRATE_DATABASE_ON_STARTUP", "true")
    env.setdefault("DISABLE_ANONYMOUS_TRACKING", "true")
    # Engine auth is unnecessary inside the worker sandbox; the platform
    # authenticates callers before a job ever reaches this container.
    env.setdefault("DISABLE_AUTH", "true")
    proc = subprocess.Popen(
        ["node", "/app/start.js"],
        env=env,
        cwd="/app",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    deadline = time.time() + ENGINE_BOOT_TIMEOUT_S
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("Presenton engine exited during boot")
        try:
            with urllib.request.urlopen(ENGINE_URL, timeout=3):
                return proc
        except (urllib.error.URLError, OSError):
            time.sleep(2)
    raise RuntimeError("Presenton engine did not become healthy in time")


def _engine_generate(request: dict) -> Path:
    """Drive the engine's synchronous generate endpoint; return the artifact."""
    body = json.dumps(request).encode()
    req = urllib.request.Request(
        f"{ENGINE_URL}/api/v1/ppt/presentation/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=1800) as res:
        result = json.loads(res.read())
    # result.path is a URL path served by nginx, e.g. /app_data/exports/x.pptx
    url_path = result["path"]
    local = Path(url_path if url_path.startswith("/app_data") else f"/app_data/{url_path.lstrip('/')}")
    if not local.exists():
        # Fall back to fetching through nginx.
        local = Path("/tmp/artifact" + Path(url_path).suffix)
        with urllib.request.urlopen(f"{ENGINE_URL}{url_path}", timeout=120) as res:
            local.write_bytes(res.read())
    return local


def _store(
    job_id: str, local_path: Path, name: str, fmt: str, publish: bool
) -> dict:
    """Upload one artifact to the private bucket, optionally publish a public
    copy, and return the artifact record sent back to Convex."""
    r2_key = f"jobs/{job_id}/{name}.{fmt}"
    size = _upload_to_r2(local_path, r2_key)
    record = {"format": fmt, "r2_key": r2_key, "bytes": size}
    if publish:
        public_url = _publish_to_r2(local_path, r2_key)
        if public_url:
            record["public_url"] = public_url
    return record


def _doc_engine_kwargs() -> dict:
    return {
        "templates_dir": "/opt/presenton-templates",
        "specs_dir": "/opt/presenton-design-specs",
    }


def _run_presentation_job(job_id: str, request: dict) -> list[dict]:
    # The Presenton engine exports PPTX/PDF. An HTML deck is produced by the
    # doc-engine's deck renderer instead, so route that here.
    if request.get("export_as") == "html":
        return _run_deck_job(job_id, request)

    engine_request = {
        "content": request.get("content", ""),
        "instructions": request.get("instructions"),
        "template": request.get("template", "general"),
        "export_as": request.get("export_as", "pptx"),
        "trigger_webhook": False,
    }
    if request.get("n_slides"):
        engine_request["n_slides"] = request["n_slides"]
    if request.get("language"):
        engine_request["language"] = request["language"]
    if request.get("tone"):
        engine_request["tone"] = request["tone"]

    publish = bool(request.get("publish"))
    proc = _boot_engine()
    try:
        artifact = _engine_generate(engine_request)
        fmt = artifact.suffix.lstrip(".") or engine_request["export_as"]
        return [_store(job_id, artifact, "presentation", fmt, publish)]
    finally:
        proc.terminate()


def _run_document_job(job_id: str, request: dict) -> list[dict]:
    import sys

    sys.path.insert(0, "/opt")
    from doc_engine.pipeline import generate_document

    publish = bool(request.get("publish"))
    brand_url = request.get("brand_image_url")
    brand_image = _fetch_source_file(brand_url, ".img") if brand_url else None
    outputs = generate_document(
        content=request.get("content", ""),
        instructions=request.get("instructions"),
        template=request.get("template", "general"),
        formats=request.get("formats", ["pdf"]),
        out_dir="/tmp/doc-out",
        chromium="/usr/bin/chromium",
        brand_image=brand_image,
        **_doc_engine_kwargs(),
    )
    return [
        _store(job_id, Path(path), "document", fmt, publish)
        for fmt, path in outputs.items()
    ]


def _fetch_source_file(url: str, suffix: str) -> Path:
    """Download a caller-supplied source file (e.g. a .pptx to convert)."""
    local = Path(f"/tmp/source{suffix}")
    with urllib.request.urlopen(url, timeout=300) as res:
        local.write_bytes(res.read())
    return local


def _run_deck_job(job_id: str, request: dict) -> list[dict]:
    """Self-contained interactive HTML presentation (no engine boot needed).

    With `source_pptx_url`, an existing deck is converted instead of
    generated: its text, bullets, tables, and notes are re-typeset in the
    requested theme.
    """
    import sys

    sys.path.insert(0, "/opt")
    from doc_engine.pipeline import generate_deck

    publish = bool(request.get("publish"))
    source_url = request.get("source_pptx_url")
    source_pptx = _fetch_source_file(source_url, ".pptx") if source_url else None
    brand_url = request.get("brand_image_url")
    brand_image = _fetch_source_file(brand_url, ".img") if brand_url else None

    outputs = generate_deck(
        content=request.get("content", ""),
        instructions=request.get("instructions"),
        template=request.get("template", "general"),
        formats=request.get("formats", ["html"]),
        source_pptx=source_pptx,
        # An existing deck model, optionally with edits applied, so callers
        # can fix one slide instead of regenerating everything.
        source_deck=request.get("deck"),
        patch=request.get("patch"),
        out_dir="/tmp/deck-out",
        chromium="/usr/bin/chromium",
        # Measure the rendered deck and repair overflowing slides before
        # export. Callers can opt out with fit: false.
        fit=request.get("fit", True) is not False,
        brand_image=brand_image,
        **_doc_engine_kwargs(),
    )
    artifacts = [
        _store(job_id, Path(path), "deck", fmt, publish)
        for fmt, path in outputs.items()
    ]
    # Ship the deck model alongside the rendering: it is what a caller edits
    # and sends back as `deck` + `patch`.
    deck_json = Path("/tmp/deck-out/deck.json")
    if deck_json.exists():
        artifacts.append(_store(job_id, deck_json, "deck", "json", publish))
    return artifacts


def _run_style_preview_job(job_id: str, request: dict) -> list[dict]:
    """Render one title-slide PNG per candidate theme so the caller can pick
    a direction before paying for a full generation."""
    import sys

    sys.path.insert(0, "/opt")
    from doc_engine.pipeline import generate_style_previews

    publish = bool(request.get("publish"))
    # Callers may pass a whole prompt as `content`; a title slide needs one
    # short line, so take the first and cap it.
    raw_title = request.get("title") or request.get("content") or "Untitled"
    title = str(raw_title).strip().splitlines()[0][:90] or "Untitled"

    previews = generate_style_previews(
        title=title,
        subtitle=request.get("subtitle"),
        meta=request.get("meta"),
        themes=request.get("themes"),
        out_dir="/tmp/preview-out",
        chromium="/usr/bin/chromium",
        **_doc_engine_kwargs(),
    )
    artifacts = []
    for theme_name, path in previews.items():
        record = _store(job_id, Path(path), f"preview-{theme_name}", "png", publish)
        record["theme"] = theme_name
        artifacts.append(record)
    return artifacts


@app.function(
    image=image,
    secrets=[worker_secret],
    timeout=1800,
    memory=6144,
    cpu=4,
)
def generate(payload: dict) -> None:
    """payload: { job_id, kind, request, callback_url }"""
    job_id = payload["job_id"]
    callback_url = payload["callback_url"]
    kind = payload["kind"]
    try:
        if kind == "presentation":
            artifacts = _run_presentation_job(job_id, payload["request"])
        elif kind == "deck":
            artifacts = _run_deck_job(job_id, payload["request"])
        elif kind == "style_preview":
            artifacts = _run_style_preview_job(job_id, payload["request"])
        else:
            artifacts = _run_document_job(job_id, payload["request"])
        _callback(
            callback_url,
            {"job_id": job_id, "status": "succeeded", "artifacts": artifacts},
        )
    except Exception as exc:  # noqa: BLE001 - report all failures upstream
        _callback(
            callback_url,
            {"job_id": job_id, "status": "failed", "error": str(exc)[:2000]},
        )
        raise


@app.function(image=image, secrets=[worker_secret])
@modal.fastapi_endpoint(method="POST", requires_proxy_auth=True)
def submit(payload: dict) -> dict:
    """Called by Convex (dispatch.ts). Spawns the generation job and returns
    the Modal call id immediately."""
    call = generate.spawn(payload)
    return {"call_id": call.object_id}
