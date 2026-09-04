"""Workday collector (spec §5.1).

POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
Paginate 20 at a time until offset >= total. tenant/N/site come from the
registry `workday:` block.
"""
from __future__ import annotations

from typing import Any

import httpx

from ...http import request
from ...models import RawPosting

LIST = "https://{tenant}.wd{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
HOST = "https://{tenant}.wd{wd}.myworkdayjobs.com"
PAGE = 20


async def collect(client: httpx.AsyncClient, company: dict[str, Any]) -> list[RawPosting]:
    wd = company.get("workday") or {}
    tenant, n, site = wd.get("tenant"), wd.get("wd"), wd.get("site")
    if not (tenant and n and site):
        return []
    url = LIST.format(tenant=tenant, wd=n, site=site)
    base_host = HOST.format(tenant=tenant, wd=n)
    out: list[RawPosting] = []
    offset = 0
    while True:
        body = {"appliedFacets": {}, "limit": PAGE, "offset": offset, "searchText": "intern"}
        resp = await request(
            client, "POST", url, json=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            conditional=False,
        )
        if resp is None or resp.status_code != 200:
            break
        try:
            data = resp.json()
        except ValueError:
            break
        postings = data.get("jobPostings", [])
        if not postings:
            break
        for job in postings:
            path = job.get("externalPath", "")
            out.append(
                RawPosting(
                    company_slug=company["slug"],
                    company_name=company["name"],
                    title=job.get("title", ""),
                    apply_url=f"{base_host}/{site}{path}" if path else base_host,
                    ats_job_id=job.get("bulletFields", [None])[0] if job.get("bulletFields") else None,
                    location_text=job.get("locationsText", ""),
                    description="",  # detail fetch omitted to keep the sweep cheap
                    source_type="workday",
                    source_url=f"{base_host}/{site}{path}" if path else None,
                    raw=job,
                )
            )
        total = data.get("total", 0)
        offset += PAGE
        if offset >= total:
            break
    return out
