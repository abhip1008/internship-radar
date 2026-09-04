"""The core batch pipeline (spec §3).

collect -> normalize -> filter -> dedupe -> score/deadlines -> DB, plus
disappearance tracking (§9) and new-posting alerts (§8). Kept separate from the
CLI (run.py) so it can be imported and tested.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from . import deadlines, dedupe, filters, normalize, notify, score
from .collectors import custom
from .collectors.ats import get_collector as ats_collector
from .collectors.feeds import rss
from .collectors.lists import github_repos
from .config import load_config
from .db import DB
from .http import get_client
from .models import Posting, RawPosting

log = logging.getLogger("radar")
rejection_log = logging.getLogger("radar.rejections")


async def _collect_company(client, company: dict[str, Any]) -> list[RawPosting]:
    ats = company.get("ats")
    try:
        if ats == "custom":
            fn = custom.get_collector(company.get("collector", ""))
            return await fn(client, company) if fn else []
        if company.get("feed_url"):
            return await rss.collect(client, company)
        fn = ats_collector(ats)
        return await fn(client, company) if fn else []
    except Exception as exc:  # a broken collector must not kill the sweep
        log.warning("collector failed for %s (%s): %s", company.get("slug"), ats, exc)
        return []


def _process(raws: list[RawPosting], companies_by_slug: dict[str, dict], target_terms: set[str]) -> list[Posting]:
    """normalize -> filter -> score/deadlines. Returns kept postings (pre-dedupe)."""
    cfg = load_config()
    fallback_days = cfg["deadlines"]["global_fallback_days"]
    kept: list[Posting] = []
    for raw in raws:
        p = normalize.normalize(raw)
        verdict = filters.evaluate(p, target_terms)
        if not verdict.passed:
            rejection_log.info("REJECT %s | %s | %s", p.company_name, p.title, verdict.reason)
            continue
        p.eligibility_flags = verdict.eligibility_flags
        company = companies_by_slug.get(p.company_slug)
        p.fit_score, p.fit_breakdown = score.score(p, company)
        dl = deadlines.resolve(p, global_fallback_days=fallback_days)
        p.closes_at, p.closes_kind, p.closes_evidence = dl["closes_at"], dl["closes_kind"], dl["closes_evidence"]
        kept.append(p)
    return kept


async def run_sweep(
    companies: list[dict[str, Any]],
    include_lists: bool = False,
    db: Optional[DB] = None,
    do_notify: bool = True,
) -> dict[str, Any]:
    """Run one collection sweep over the given companies (+ optional community lists)."""
    cfg = load_config()
    target_terms = set(cfg["profile"]["target_terms"])
    own_db = db is None
    db = db or DB()
    companies_by_slug = {c["slug"]: c for c in companies}

    raws: list[RawPosting] = []
    async with get_client() as client:
        tasks = [_collect_company(client, c) for c in companies]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for c, res in zip(companies, results):
            if isinstance(res, Exception):
                db.mark_polled(c["slug"], ok=False)
                continue
            db.mark_polled(c["slug"], ok=True)
            raws.extend(res)
        if include_lists:
            try:
                raws.extend(await github_repos.collect(client))
            except Exception as exc:
                log.warning("github list collector failed: %s", exc)

    kept = _process(raws, companies_by_slug, target_terms)
    deduped = dedupe.dedupe_batch(kept)

    # Disappearance tracking (§9): postings previously seen for a registry company
    # that no longer appear get marked closed.
    seen_ids_by_company: dict[str, set[str]] = {}
    for p in deduped:
        seen_ids_by_company.setdefault(p.company_slug, set()).add(p.id)

    new_postings: list[Posting] = []
    for p in deduped:
        outcome = db.upsert_posting(p)
        if outcome == "new":
            new_postings.append(p)

    closed = 0
    for slug in companies_by_slug:
        previously_open = db.all_posting_ids_for_company(slug)
        vanished = previously_open - seen_ids_by_company.get(slug, set())
        for pid in vanished:
            db.mark_closed(pid)
            closed += 1

    summary = {
        "collected": len(raws),
        "kept": len(kept),
        "deduped": len(deduped),
        "new": len(new_postings),
        "closed": closed,
    }

    if do_notify and new_postings:
        result = notify.send(new_postings, companies_by_slug)
        summary["notified"] = result

    if own_db:
        db.close()
    return summary
