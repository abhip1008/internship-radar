"""Lever collector (spec §5.1).

GET https://api.lever.co/v0/postings/{company}?mode=json
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from ...http import get_json
from ...models import RawPosting

BASE = "https://api.lever.co/v0/postings/{token}?mode=json"


async def collect(client: httpx.AsyncClient, company: dict[str, Any]) -> list[RawPosting]:
    token = company.get("board_token") or company.get("slug")
    data = await get_json(client, BASE.format(token=token))
    if not isinstance(data, list):
        return []
    out: list[RawPosting] = []
    for job in data:
        cats = job.get("categories") or {}
        posted = None
        if job.get("createdAt"):
            try:
                posted = datetime.fromtimestamp(job["createdAt"] / 1000, tz=timezone.utc)
            except (ValueError, OSError, TypeError):
                posted = None
        out.append(
            RawPosting(
                company_slug=company["slug"],
                company_name=company["name"],
                title=job.get("text", ""),
                apply_url=job.get("hostedUrl", ""),
                ats_job_id=job.get("id"),
                location_text=cats.get("location", ""),
                description=job.get("descriptionPlain", ""),
                posted_at=posted,
                source_type="lever",
                source_url=job.get("hostedUrl"),
                raw=job,
            )
        )
    return out
