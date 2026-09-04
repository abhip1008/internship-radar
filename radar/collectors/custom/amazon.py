"""Amazon collector (spec §4 Tier 2).

Uses the public amazon.jobs search JSON endpoint, filtered to internship roles.
No auth. Paginates via result_limit/offset.
"""
from __future__ import annotations

import html
import re
from typing import Any

import httpx

from ...http import get_json
from ...models import RawPosting

SEARCH = "https://www.amazon.jobs/en/search.json"
PAGE = 100


def _strip_html(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


async def collect(client: httpx.AsyncClient, company: dict[str, Any]) -> list[RawPosting]:
    out: list[RawPosting] = []
    offset = 0
    while True:
        params = {
            "normalized_country_code[]": "USA",
            "radius": "100mi",
            "facets[]": "normalized_country_code",
            "offset": offset,
            "result_limit": PAGE,
            "sort": "recent",
            "category[]": "internship",
            "query_options": "",
            "base_query": "software intern",
        }
        data = await get_json(client, SEARCH, params=params)
        if not data or not data.get("jobs"):
            break
        for job in data["jobs"]:
            path = job.get("job_path", "")
            out.append(
                RawPosting(
                    company_slug=company["slug"],
                    company_name=company["name"],
                    title=job.get("title", ""),
                    apply_url=f"https://www.amazon.jobs{path}" if path else "https://www.amazon.jobs",
                    ats_job_id=job.get("id_icims") or job.get("id"),
                    location_text=job.get("normalized_location") or job.get("location", ""),
                    description=_strip_html(job.get("description", "")),
                    source_type="amazon",
                    source_url=f"https://www.amazon.jobs{path}" if path else None,
                    raw=job,
                )
            )
        total = data.get("hits", 0)
        offset += PAGE
        if offset >= total or offset > 1000:
            break
    return out
