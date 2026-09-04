"""ATS auto-detection — the bootstrap script (spec §5.2).

Given a company name and optional homepage, find its board without you looking
anything up. Probe the candidate platforms; fall back to regexing the homepage
and common careers paths for board hosts. Cache the result; only re-run when a
collector 404s twice.
"""
from __future__ import annotations

import re
from typing import Any, Optional

import httpx

from .http import get_client, request

CANDIDATE_PROBES = [
    ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"),
    ("lever", "https://api.lever.co/v0/postings/{slug}?mode=json"),
    ("ashby", "https://api.ashbyhq.com/posting-api/job-board/{slug}"),
    ("recruitee", "https://{slug}.recruitee.com/api/offers/"),
    ("smartrecruiters", "https://api.smartrecruiters.com/v1/companies/{slug}/postings"),
]

HOST_REGEXES = [
    ("greenhouse", r"(?:boards|job-boards)\.greenhouse\.io/([\w-]+)"),
    ("lever", r"jobs\.lever\.co/([\w-]+)"),
    ("ashby", r"jobs\.ashbyhq\.com/([\w-]+)"),
    ("workday", r"([\w-]+)\.wd(\d)\.myworkdayjobs\.com/([\w-]+)"),
    ("workable", r"apply\.workable\.com/([\w-]+)"),
    ("recruitee", r"([\w-]+)\.recruitee\.com"),
]


def slug_guesses(company_name: str) -> list[str]:
    base = company_name.lower().strip()
    stripped = re.sub(r"\b(inc|llc|labs|technologies|technology|corp|co)\b\.?", "", base).strip()
    guesses = {
        re.sub(r"[^a-z0-9]", "", base),
        re.sub(r"[^a-z0-9]", "", stripped),
        re.sub(r"[^a-z0-9]+", "-", stripped).strip("-"),
        re.sub(r"\s+", "", stripped),
    }
    return [g for g in guesses if g]


def _payload_nonempty(ats: str, data: Any) -> bool:
    if data is None:
        return False
    if ats == "greenhouse":
        return bool(data.get("jobs"))
    if ats == "lever":
        return isinstance(data, list) and len(data) > 0
    if ats == "ashby":
        return bool(data.get("jobs"))
    if ats == "recruitee":
        return bool(data.get("offers"))
    if ats == "smartrecruiters":
        return "content" in data
    return False


async def _probe(client: httpx.AsyncClient, ats: str, url_tmpl: str, slug: str) -> Optional[dict[str, Any]]:
    resp = await request(client, "GET", url_tmpl.format(slug=slug), conditional=False, max_retries=1)
    if resp is None or resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    if _payload_nonempty(ats, data):
        return {"ats": ats, "board_token": slug}
    return None


async def _scan_html(client: httpx.AsyncClient, url: str) -> Optional[dict[str, Any]]:
    resp = await request(client, "GET", url, conditional=False, max_retries=1)
    if resp is None or resp.status_code != 200:
        return None
    text = resp.text
    for ats, rx in HOST_REGEXES:
        m = re.search(rx, text)
        if not m:
            continue
        if ats == "workday":
            return {"ats": "workday", "workday": {"tenant": m.group(1), "wd": int(m.group(2)), "site": m.group(3)}}
        return {"ats": ats, "board_token": m.group(1)}
    return None


async def detect(company_name: str, homepage: Optional[str] = None) -> dict[str, Any]:
    """Return {ats, board_token|workday, ...} or {ats: 'manual'} if unresolved."""
    async with get_client() as client:
        # 1-2. probe candidate platforms with slug guesses
        for slug in slug_guesses(company_name):
            for ats, tmpl in CANDIDATE_PROBES:
                hit = await _probe(client, ats, tmpl, slug)
                if hit:
                    return hit
        # 3-4. fall back to scraping the homepage and common careers paths
        candidates = []
        if homepage:
            candidates.append(homepage)
            base = homepage.rstrip("/")
            candidates += [f"{base}/careers", f"{base}/jobs", f"{base}/company/careers"]
        for url in candidates:
            found = await _scan_html(client, url)
            if found:
                return found
    # 5. unresolved
    return {"ats": "manual"}
