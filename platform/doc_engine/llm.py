"""Optional LLM step: expand a prompt into a document structure.

Uses any OpenAI-compatible chat endpoint. Configuration (env):
    DOC_ENGINE_LLM_BASE_URL   default https://api.openai.com/v1, or falls back
                              to CUSTOM_LLM_URL when set
    DOC_ENGINE_LLM_API_KEY    falls back to OPENAI_API_KEY / CUSTOM_LLM_API_KEY
    DOC_ENGINE_LLM_MODEL      default gpt-4.1 (or CUSTOM_MODEL)

When no key is configured, callers should fall back to
structure.parse_markdown (deterministic, no network).
"""

from __future__ import annotations

import json
import os
import urllib.request

from .structure import DOCUMENT_JSON_SPEC


def llm_configured() -> bool:
    return bool(
        os.environ.get("DOC_ENGINE_LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("CUSTOM_LLM_API_KEY")
    )


def generate_structure(content: str, instructions: str | None) -> dict:
    base_url = (
        os.environ.get("DOC_ENGINE_LLM_BASE_URL")
        or os.environ.get("CUSTOM_LLM_URL")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    api_key = (
        os.environ.get("DOC_ENGINE_LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("CUSTOM_LLM_API_KEY")
    )
    model = (
        os.environ.get("DOC_ENGINE_LLM_MODEL")
        or os.environ.get("CUSTOM_MODEL")
        or "gpt-4.1"
    )

    system = (
        "You write professional business documents (reports, briefs, one-pagers). "
        + DOCUMENT_JSON_SPEC
    )
    user = f"Write a document based on:\n\n{content}"
    if instructions:
        user += f"\n\nAdditional instructions: {instructions}"

    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
    ).encode()
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as res:
        payload = json.loads(res.read())
    return json.loads(payload["choices"][0]["message"]["content"])
