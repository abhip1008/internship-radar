"""Microsoft collector (spec §4 Tier 2).

Uses the careers search API at gcsservices.careers.microsoft.com, filtered to
internship employment type. No auth. Paginates via pg (1-based).
"""
from __future__ import annotations

import html
import re
from typing import Any

import httpx

from ...http import get_json
from ...models import RawPosting

SEARCH = "https://gcsservices.careers.microsoft.com/search/api/v1/search"
JOB_URL = "https://jobs.careers.microsoft.com/global/en/job/{jid}"
PAGE = 20


def _strip_html(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


async def collect(client: httpx.AsyncClient, company: dict[str, Any]) -> list[RawPosting]:
    out: list[RawPosting] = []
    page = 1
    while True:
        params = {
            "q": "software intern",
            "l": "en_us",
            "pg": page,
            "pgSz": PAGE,
            "o": "Recent",
            "flt": "true",
            "et": "Internship",
        }
        data = await get_json(client, SEARCH, params=params)
        result = (data or {}).get("operationResult", {}).get("result", {})
        jobs = result.get("jobs", [])
        if not jobs:
            break
        for job in jobs:
            jid = job.get("jobId")
            props = job.get("properties", {}) or {}
            locs = props.get("locations") or ([props.get("primaryLocation")] if props.get("primaryLocation") else [])
            out.append(
                RawPosting(
                    company_slug=company["slug"],
                    company_name=company["name"],
                    title=job.get("title", ""),
                    apply_url=JOB_URL.format(jid=jid) if jid else "https://jobs.careers.microsoft.com",
                    ats_job_id=str(jid) if jid else None,
                    location_text="; ".join(str(x) for x in locs if x),
                    description=_strip_html(props.get("description", "")),
                    source_type="microsoft",
                    source_url=JOB_URL.format(jid=jid) if jid else None,
                    raw=job,
                )
            )
        total = result.get("totalJobs", 0)
        page += 1
        if page * PAGE > total or page > 50:
            break
    return out
