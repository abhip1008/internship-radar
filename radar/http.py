"""Polite HTTP client (spec §17).

Descriptive User-Agent with a contact address, per-host rate limiting,
conditional requests via ETag/Last-Modified, and exponential backoff that
respects Retry-After. Import `get_client()` for a shared async client.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import httpx

from .config import load_config

# In-memory conditional-request cache: url -> (etag, last_modified).
_COND_CACHE: dict[str, tuple[Optional[str], Optional[str]]] = {}
# Per-host last-request timestamps for rate limiting.
_HOST_LAST: dict[str, float] = {}
_HOST_LOCK = asyncio.Lock()


def _cfg() -> dict[str, Any]:
    return load_config().get("http", {})


def get_client() -> httpx.AsyncClient:
    cfg = _cfg()
    return httpx.AsyncClient(
        headers={"User-Agent": cfg.get("user_agent", "internship-radar/0.1")},
        timeout=cfg.get("timeout_seconds", 20),
        follow_redirects=True,
    )


async def _throttle(host: str) -> None:
    """Cap requests per host at http.per_host_rps."""
    rps = max(_cfg().get("per_host_rps", 3), 1)
    min_gap = 1.0 / rps
    async with _HOST_LOCK:
        last = _HOST_LAST.get(host, 0.0)
        wait = min_gap - (time.monotonic() - last)
        if wait > 0:
            await asyncio.sleep(wait)
        _HOST_LAST[host] = time.monotonic()


async def request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_retries: int = 3,
    conditional: bool = True,
    **kwargs: Any,
) -> Optional[httpx.Response]:
    """Make a rate-limited, retrying request.

    Returns None on a 304 (not modified) or after exhausting retries.
    """
    host = httpx.URL(url).host or url
    headers = dict(kwargs.pop("headers", {}))
    if conditional and url in _COND_CACHE:
        etag, last_mod = _COND_CACHE[url]
        if etag:
            headers["If-None-Match"] = etag
        if last_mod:
            headers["If-Modified-Since"] = last_mod

    backoff = 1.0
    for attempt in range(max_retries):
        await _throttle(host)
        try:
            resp = await client.request(method, url, headers=headers, **kwargs)
        except (httpx.TransportError, httpx.TimeoutException):
            await asyncio.sleep(backoff)
            backoff *= 2
            continue

        if resp.status_code == 304:
            return None
        if resp.status_code == 429 or resp.status_code >= 500:
            retry_after = resp.headers.get("Retry-After")
            delay = float(retry_after) if (retry_after and retry_after.isdigit()) else backoff
            await asyncio.sleep(delay)
            backoff *= 2
            continue

        if conditional and resp.status_code == 200:
            _COND_CACHE[url] = (resp.headers.get("ETag"), resp.headers.get("Last-Modified"))
        return resp
    return None


async def get_json(client: httpx.AsyncClient, url: str, **kwargs: Any) -> Optional[Any]:
    resp = await request(client, "GET", url, **kwargs)
    if resp is None or resp.status_code != 200:
        return None
    try:
        return resp.json()
    except (ValueError, httpx.DecodingError):
        return None
