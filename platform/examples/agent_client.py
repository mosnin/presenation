"""Example: how an AI agent delegates document creation to the platform.

Usage:
    export PRESENTON_PLATFORM_URL=https://your-deployment.convex.site
    export PRESENTON_API_KEY=sk_pres_...
    python agent_client.py
"""

import json
import os
import time
import urllib.request

BASE = os.environ["PRESENTON_PLATFORM_URL"].rstrip("/")
KEY = os.environ["PRESENTON_API_KEY"]


def _request(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode() if body else None,
        headers={
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read())


def create_artifact(kind: str, request: dict, poll_seconds: int = 5) -> dict:
    """Submit a job and block until it finishes. Returns the final status
    payload, whose `artifacts` list holds presigned download URLs."""
    job = _request("POST", "/agent/v1/jobs", {"kind": kind, "request": request})
    job_id = job["job_id"]
    while True:
        status = _request("GET", f"/agent/v1/jobs/status?id={job_id}")
        if status["status"] in ("succeeded", "failed"):
            return status
        time.sleep(poll_seconds)


if __name__ == "__main__":
    # A presentation, rendered by the Presenton engine on Modal:
    result = create_artifact(
        "presentation",
        {
            "content": "Series A pitch for an AI-powered logistics startup",
            "template": "momentum",
            "n_slides": 8,
            "export_as": "pptx",
        },
    )
    print(json.dumps(result, indent=2))

    # A document in the same Momentum aesthetic, rendered by the doc-engine:
    result = create_artifact(
        "document",
        {
            "content": "One-page investor update for the same startup: "
            "$1.2M ARR, 14 enterprise customers, 9 months runway.",
            "template": "momentum",
            "formats": ["pdf", "docx"],
        },
    )
    print(json.dumps(result, indent=2))
