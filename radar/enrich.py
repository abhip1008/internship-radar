"""Job-description enrichment.

Community-list postings usually arrive with no description, which makes honest
assessment impossible (they show as "thin JD"). This module fetches the full JD
from the posting's own apply link so those become properly assessable.

Strategy (cheapest/cleanest first):
  1. ATS detail APIs when the apply URL is a known board — Greenhouse, Lever, Ashby.
  2. Generic schema.org JobPosting JSON-LD embedded in the page (covers Microsoft
     careers and most company career pages).
  3. Fallback: the page's <meta name="description">.
Hosts we can't parse (e.g. amazon.jobs hides its text) just return None and the
posting stays honestly flagged as thin.
"""
from __future__ import annotations

import html as _html
import json
import logging
import re
from typing import Any, Optional

import httpx

from . import deadlines, filters, normalize, score
from .db import DB
from .http import get_client, request

log = logging.getLogger("radar.enrich")

GH_DETAIL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{jid}?questions=false"
LEVER_DETAIL = "https://api.lever.co/v0/postings/{company}/{jid}?mode=json"
ASHBY_LIST = "https://api.ashbyhq.com/posting-api/job-board/{org}"

RE_GREENHOUSE = re.compile(r"greenhouse\.io/([\w-]+)/jobs/(\d+)")
RE_LEVER = re.compile(r"lever\.co/([\w-]+)/([\w-]+)")
RE_ASHBY = re.compile(r"ashbyhq\.com/([\w-]+)/([0-9a-fA-F-]{36})")
RE_JSONLD = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S
)
RE_META_DESC = re.compile(
    r'<meta[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\']', re.S | re.I
)


def _strip(text: str) -> str:
    text = _html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _jsonld_jobposting(html: str) -> Optional[str]:
    """Walk every JSON-LD block for a JobPosting.description (handles @graph/nesting)."""
    for block in RE_JSONLD.findall(html):
        try:
            data = json.loads(block)
        except (json.JSONDecodeError, ValueError):
            continue
        stack: list[Any] = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                t = node.get("@type")
                if (t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t)) and node.get("description"):
                    return _strip(str(node["description"]))
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    return None


async def fetch_description(client: httpx.AsyncClient, apply_url: str) -> Optional[str]:
    """Return the full JD text for a posting's apply URL, or None if unreachable."""
    if not apply_url:
        return None

    m = RE_GREENHOUSE.search(apply_url)
    if m:
        data = await _json(client, GH_DETAIL.format(token=m.group(1), jid=m.group(2)))
        if data and data.get("content"):
            return _strip(data["content"])

    m = RE_LEVER.search(apply_url)
    if m:
        data = await _json(client, LEVER_DETAIL.format(company=m.group(1), jid=m.group(2)))
        if isinstance(data, dict):
            return data.get("descriptionPlain") or _strip(data.get("description", "")) or None

    m = RE_ASHBY.search(apply_url)
    if m:
        data = await _json(client, ASHBY_LIST.format(org=m.group(1)))
        if data and data.get("jobs"):
            jid = m.group(2).lower()
            for job in data["jobs"]:
                if str(job.get("id", "")).lower() == jid:
                    return job.get("descriptionPlain") or _strip(job.get("descriptionHtml", "")) or None

    # Generic: fetch the page and read schema.org JobPosting / meta description.
    resp = await request(client, "GET", apply_url, conditional=False, max_retries=1)
    if resp is None or resp.status_code != 200:
        return None
    text = resp.text
    jd = _jsonld_jobposting(text)
    if jd and len(jd) >= 200:
        return jd
    meta = RE_META_DESC.search(text)
    if meta:
        m2 = _strip(meta.group(1))
        return m2 if len(m2) >= 200 else None
    return None


async def _json(client: httpx.AsyncClient, url: str) -> Optional[Any]:
    resp = await request(client, "GET", url, conditional=False, max_retries=1)
    if resp is None or resp.status_code != 200:
        return None
    try:
        return resp.json()
    except (ValueError, httpx.DecodingError):
        return None


def _recompute(db: DB, row: dict[str, Any], description: str, companies: dict[str, dict]) -> None:
    """Re-derive term/eligibility/fit/closes from the new description and store it."""
    import json as _json_mod

    from .models import Posting

    p = Posting(
        id=row["id"], company_slug=row["company_slug"], company_name=row["company_name"],
        title=row["title"], apply_url=row["apply_url"],
        locations=_json_mod.loads(row.get("locations") or "[]"),
        is_seattle_metro=bool(row.get("is_seattle_metro")),
        is_remote_us=bool(row.get("is_remote_us")), is_wa=bool(row.get("is_wa")),
        term=row.get("term", "unspecified"), description=description,
        first_seen_at=None,
    )
    # Term can now be classified from the real JD; keep the stronger signal.
    new_term = normalize.classify_term(p.title, description)
    if new_term != "unspecified":
        p.term = new_term
    p.eligibility_flags = filters.eligibility_flags(description)
    fit, breakdown = score.score(p, companies.get(p.company_slug))
    dl = deadlines.resolve(p, company_lifetimes=db.company_lifetimes(p.company_slug))

    db.update_posting_fields(row["id"], {
        "description": description,
        "term": p.term,
        "eligibility_flags": p.eligibility_flags,
        "fit_score": fit,
        "fit_breakdown": breakdown,
        "closes_at": dl["closes_at"],
        "closes_kind": dl["closes_kind"],
        "closes_evidence": dl["closes_evidence"],
    })
    # Force a re-assessment on the next auto-prepare.
    db.set_prep_state(row["id"], None)


async def enrich_rows(db: DB, rows: list[dict[str, Any]], min_chars: int = 300) -> dict[str, Any]:
    """Enrich the given posting rows that have thin descriptions. Returns a summary."""
    companies = {c["slug"]: c for c in db.get_companies()}
    targets = [r for r in rows if len((r.get("description") or "").strip()) < min_chars]
    enriched, failed = 0, 0
    async with get_client() as client:
        for row in targets:
            try:
                jd = await fetch_description(client, row["apply_url"])
            except Exception as exc:  # a single bad page must not stop the batch
                log.debug("enrich failed for %s: %s", row["apply_url"], exc)
                jd = None
            if jd and len(jd.strip()) >= min_chars:
                _recompute(db, row, jd.strip(), companies)
                enriched += 1
            else:
                failed += 1
    return {"targets": len(targets), "enriched": enriched, "unresolved": failed}
