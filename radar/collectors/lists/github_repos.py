"""GitHub community-list collectors (spec §4 Tier 3).

These repos publish machine-readable listings. We parse the JSON where available
rather than the README. High recall, slightly stale — and the best registry
growth engine: every new company here that isn't in the registry is a candidate
for ATS detection.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from ...http import get_json
from ...models import RawPosting

# Machine-readable listing sources. Each is a raw githubusercontent JSON URL.
SOURCES = [
    {
        "name": "SimplifyJobs/Summer2027-Internships",
        "url": "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/.github/scripts/listings.json",
    },
    {
        "name": "vanshb03/Summer2027-Internships",
        "url": "https://raw.githubusercontent.com/vanshb03/Summer2027-Internships/dev/.github/scripts/listings.json",
    },
    {
        "name": "SimplifyJobs/New-Grad-Positions",
        "url": "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json",
    },
]


def _slugify(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def _location_text(item: dict[str, Any]) -> str:
    locs = item.get("locations") or item.get("location") or []
    if isinstance(locs, str):
        return locs
    return "; ".join(str(x) for x in locs if x)


async def collect(client: httpx.AsyncClient, company: dict[str, Any] | None = None) -> list[RawPosting]:
    """company is ignored — this collector sweeps whole lists at once."""
    out: list[RawPosting] = []
    for src in SOURCES:
        data = await get_json(client, src["url"])
        if not isinstance(data, list):
            continue
        for item in data:
            # The Simplify schema uses `active`, `company_name`, `title`, `url`.
            if item.get("active") is False:
                continue
            company_name = item.get("company_name") or item.get("company") or ""
            url = item.get("url") or item.get("apply_link") or ""
            if not (company_name and url):
                continue
            posted = None
            if item.get("date_posted"):
                try:
                    posted = datetime.fromtimestamp(int(item["date_posted"]), tz=timezone.utc)
                except (ValueError, OSError, TypeError):
                    posted = None
            out.append(
                RawPosting(
                    company_slug=_slugify(company_name),
                    company_name=company_name,
                    title=item.get("title", ""),
                    apply_url=url,
                    ats_job_id=item.get("id"),
                    location_text=_location_text(item),
                    description=item.get("description", "") or "",
                    posted_at=posted,
                    source_type="github-list",
                    source_url=src["name"],
                    raw=item,
                )
            )
    return out
