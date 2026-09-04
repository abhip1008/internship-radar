"""Thin LLM client with a graceful no-key fallback.

The spec targets Gemini's free tier for rephrasing (§10) and notes (§11). When
no API key is present, `complete()` returns None and every caller falls back to
a deterministic path, so the whole pipeline still produces useful output offline.
"""
from __future__ import annotations

import json
import os
from typing import Optional

import httpx

from .config import load_config

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"


def available() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def complete(prompt: str, *, max_tokens: int = 800, temperature: float = 0.4) -> Optional[str]:
    """Return the model's text, or None if no key / the call fails.

    Synchronous by design — it's called once per posting from the batch pipeline,
    never in a hot loop.
    """
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    cfg = load_config().get("llm", {})
    model = cfg.get("model", "gemini-2.0-flash")
    url = GEMINI_URL.format(model=model, key=key)
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
    }
    try:
        resp = httpx.post(url, json=body, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError):
        return None
