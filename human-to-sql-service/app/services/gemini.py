"""Minimal Gemini REST client for SQL generation and schema embeddings.

Uses the Generative Language API directly over httpx rather than the vendor SDK,
so the Lambda bundle stays small and the request shape stays visible.
"""
from __future__ import annotations

import json
from typing import Any, Sequence

import httpx

from ..config import settings


class GeminiError(RuntimeError):
    """Raised when Gemini is unreachable, unconfigured, or returns no usable text."""


class GeminiNotConfigured(GeminiError):
    """Raised when no API key is present, so callers can return a clear 503."""


def is_configured() -> bool:
    return bool(settings.gemini_api_key)


def _require_key() -> str:
    if not settings.gemini_api_key:
        raise GeminiNotConfigured(
            "GEMINI_API_KEY is not set. Add it to human-to-sql-service/.env "
            "to enable generated SQL."
        )
    return settings.gemini_api_key


def _endpoint(model: str, action: str) -> str:
    return f"{settings.gemini_base_url.rstrip('/')}/models/{model}:{action}"


def _post(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    key = _require_key()
    try:
        response = httpx.post(
            url,
            json=payload,
            headers={"x-goog-api-key": key, "content-type": "application/json"},
            timeout=settings.gemini_timeout_seconds,
        )
    except httpx.HTTPError as error:
        raise GeminiError(f"Gemini request failed: {error}") from error
    if response.status_code >= 400:
        raise GeminiError(f"Gemini returned {response.status_code}: {response.text[:400]}")
    return response.json()


def generate_json(
    *,
    system_instruction: str,
    prompt: str,
    response_schema: dict[str, Any],
    model: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Ask Gemini for a JSON object matching ``response_schema``.

    Returns the parsed object plus call metadata for auditing.
    """
    chosen = model or settings.gemini_model
    payload = {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "candidateCount": 1,
            "maxOutputTokens": settings.gemini_max_output_tokens,
            "thinkingConfig": {"thinkingBudget": 0},
            "responseMimeType": "application/json",
            "responseSchema": response_schema,
        },
    }
    body = _post(_endpoint(chosen, "generateContent"), payload)

    candidates = body.get("candidates") or []
    if not candidates:
        raise GeminiError(f"Gemini returned no candidates: {json.dumps(body)[:400]}")
    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts).strip()
    if not text:
        finish = candidates[0].get("finishReason", "unknown")
        raise GeminiError(f"Gemini returned an empty response (finishReason={finish})")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise GeminiError(f"Gemini response was not valid JSON: {text[:400]}") from error

    usage = body.get("usageMetadata", {})
    meta = {
        "model": chosen,
        "finish_reason": candidates[0].get("finishReason"),
        "prompt_tokens": usage.get("promptTokenCount"),
        "output_tokens": usage.get("candidatesTokenCount"),
    }
    return parsed, meta


def embed(text: str, *, model: str | None = None, task_type: str = "RETRIEVAL_QUERY") -> list[float]:
    chosen = model or settings.gemini_embedding_model
    payload = {
        "model": f"models/{chosen}",
        "content": {"parts": [{"text": text}]},
        "taskType": task_type,
    }
    body = _post(_endpoint(chosen, "embedContent"), payload)
    values = body.get("embedding", {}).get("values")
    if not values:
        raise GeminiError("Gemini embedding response contained no values")
    return [float(value) for value in values]


def embed_batch(
    texts: Sequence[str], *, model: str | None = None, task_type: str = "RETRIEVAL_DOCUMENT"
) -> list[list[float]]:
    chosen = model or settings.gemini_embedding_model
    payload = {
        "requests": [
            {
                "model": f"models/{chosen}",
                "content": {"parts": [{"text": text}]},
                "taskType": task_type,
            }
            for text in texts
        ]
    }
    body = _post(_endpoint(chosen, "batchEmbedContents"), payload)
    embeddings = body.get("embeddings") or []
    if len(embeddings) != len(texts):
        raise GeminiError(f"Expected {len(texts)} embeddings, received {len(embeddings)}")
    return [[float(value) for value in item.get("values", [])] for item in embeddings]
