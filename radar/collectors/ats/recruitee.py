"""Recruitee collector (spec §5.1).

GET https://{company}.recruitee.com/api/offers/
"""
from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any

import httpx

from ...http import get_json
from ...models import RawPosting

BASE = "https://{token}.recruitee.com/api/offers/"


def _strip_html(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


async def collect(client: httpx.AsyncClient, company: dict[str, Any]) -> list[RawPosting]:
    token = company.get("board_token") or company.get("slug")
    data = await get_json(client, BASE.format(token=token))
    if not data or "offers" not in data:
        return []
    out: list[RawPosting] = []
    for job in data["offers"]:
        loc = ", ".join(p for p in [job.get("city"), job.get("country")] if p)
        out.append(
            RawPosting(
                company_slug=company["slug"],
                company_name=company["name"],
                title=job.get("title", ""),
                apply_url=job.get("careers_url") or job.get("careers_apply_url", ""),
                ats_job_id=str(job.get("id")) if job.get("id") else None,
                location_text=loc or job.get("location", ""),
                description=_strip_html(job.get("description", "")),
                posted_at=_parse_dt(job.get("published_at")),
                source_type="recruitee",
                source_url=job.get("careers_url"),
                raw=job,
            )
        )
    return out
