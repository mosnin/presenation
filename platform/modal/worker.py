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
    .pip_install("boto3~=1.34", "fastapi[standard]")
    .add_local_dir(str(REPO_ROOT / "platform" / "doc_engine"), "/opt/doc_engine")
    .add_local_dir(str(REPO_ROOT / "templates"), "/opt/presenton-templates")
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


def _upload_to_r2(local_path: Path, r2_key: str) -> int:
    client = _r2_client()
    size = local_path.stat().st_size
    client.upload_file(str(local_path), os.environ["R2_BUCKET"], r2_key)
    return size


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


def _run_presentation_job(job_id: str, request: dict) -> list[dict]:
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

    proc = _boot_engine()
    try:
        artifact = _engine_generate(engine_request)
        fmt = artifact.suffix.lstrip(".") or engine_request["export_as"]
        r2_key = f"jobs/{job_id}/presentation.{fmt}"
        size = _upload_to_r2(artifact, r2_key)
        return [{"format": fmt, "r2_key": r2_key, "bytes": size}]
    finally:
        proc.terminate()


def _run_document_job(job_id: str, request: dict) -> list[dict]:
    import sys

    sys.path.insert(0, "/opt")
    from doc_engine.pipeline import generate_document

    outputs = generate_document(
        content=request.get("content", ""),
        instructions=request.get("instructions"),
        template=request.get("template", "general"),
        formats=request.get("formats", ["pdf"]),
        templates_dir="/opt/presenton-templates",
        out_dir="/tmp/doc-out",
        chromium="/usr/bin/chromium",
    )
    artifacts = []
    for fmt, path in outputs.items():
        r2_key = f"jobs/{job_id}/document.{fmt}"
        size = _upload_to_r2(Path(path), r2_key)
        artifacts.append({"format": fmt, "r2_key": r2_key, "bytes": size})
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
    try:
        if payload["kind"] == "presentation":
            artifacts = _run_presentation_job(job_id, payload["request"])
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
