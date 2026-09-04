"""Workable collector (spec §5.1).

GET https://apply.workable.com/api/v1/widget/accounts/{id}?details=true
"""
from __future__ import annotations

import html
import re
from typing import Any

import httpx

from ...http import get_json
from ...models import RawPosting

BASE = "https://apply.workable.com/api/v1/widget/accounts/{token}?details=true"


def _strip_html(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


async def collect(client: httpx.AsyncClient, company: dict[str, Any]) -> list[RawPosting]:
    token = company.get("board_token") or company.get("slug")
    data = await get_json(client, BASE.format(token=token))
    if not data or "jobs" not in data:
        return []
    out: list[RawPosting] = []
    for job in data["jobs"]:
        loc_parts = [job.get("city"), job.get("state"), job.get("country")]
        loc = ", ".join(p for p in loc_parts if p) or ("Remote" if job.get("telecommuting") else "")
        out.append(
            RawPosting(
                company_slug=company["slug"],
                company_name=company["name"],
                title=job.get("title", ""),
                apply_url=job.get("url") or job.get("application_url", ""),
                ats_job_id=job.get("shortcode") or job.get("id"),
                location_text=loc,
                description=_strip_html(job.get("description", "")),
                source_type="workable",
                source_url=job.get("url"),
                raw=job,
            )
        )
    return out
