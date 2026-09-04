"""SmartRecruiters collector (spec §5.1).

GET https://api.smartrecruiters.com/v1/companies/{id}/postings?limit=100&offset=0
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from ...http import get_json
from ...models import RawPosting

LIST = "https://api.smartrecruiters.com/v1/companies/{token}/postings?limit=100&offset={offset}"


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _location(job: dict[str, Any]) -> str:
    loc = job.get("location") or {}
    parts = [loc.get("city"), loc.get("region"), loc.get("country")]
    return ", ".join(p for p in parts if p)


async def collect(client: httpx.AsyncClient, company: dict[str, Any]) -> list[RawPosting]:
    token = company.get("board_token") or company.get("slug")
    out: list[RawPosting] = []
    offset = 0
    while True:
        data = await get_json(client, LIST.format(token=token, offset=offset))
        if not data or not data.get("content"):
            break
        for job in data["content"]:
            ref = job.get("ref") or ""
            out.append(
                RawPosting(
                    company_slug=company["slug"],
                    company_name=company["name"],
                    title=job.get("name", ""),
                    apply_url=ref or f"https://jobs.smartrecruiters.com/{token}/{job.get('id')}",
                    ats_job_id=str(job.get("id")) if job.get("id") else None,
                    location_text=_location(job),
                    description=job.get("jobAd", {}).get("sections", {}).get("jobDescription", {}).get("text", "") if isinstance(job.get("jobAd"), dict) else "",
                    posted_at=_parse_dt(job.get("releasedDate")),
                    source_type="smartrecruiters",
                    source_url=ref,
                    raw=job,
                )
            )
        total = data.get("totalFound", 0)
        offset += 100
        if offset >= total:
            break
    return out
