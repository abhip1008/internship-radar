"""Auto-prepare (a.k.a. "auto apply") — spec §10 boundary preserved.

This NEVER submits an application (spec §1 non-goals: auto-submit breaks and gets
accounts flagged). It auto-*prepares* strong-match postings so they're one click
from submitting:

  1. Pick candidates by scope (default: Seattle-metro, fit >= threshold, status new).
  2. Generate the notes for each (this computes the gap list deterministically).
  3. GATE — if the posting has any real gap (a JD skill you don't have), DO NOT
     auto-tailor. Mark it `needs_improvement` and leave the gaps for you to act on.
  4. Otherwise it's a clean match: auto-tailor the resume and mark it `ready`.

The gate direction matches the user's rule: "auto-tailor, but unless there are
notes on things I can improve, then it doesn't."
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from . import notes as notes_mod
from .config import load_config
from .db import DB
from .models import Posting

log = logging.getLogger("radar.autoapply")


def _row_to_posting(row: dict[str, Any]) -> Posting:
    import json

    return Posting(
        id=row["id"], company_slug=row["company_slug"], company_name=row["company_name"],
        title=row["title"], apply_url=row["apply_url"], ats_job_id=row.get("ats_job_id"),
        locations=json.loads(row.get("locations") or "[]"),
        is_seattle_metro=bool(row.get("is_seattle_metro")),
        is_remote_us=bool(row.get("is_remote_us")), is_wa=bool(row.get("is_wa")),
        term=row.get("term", "unspecified"), description=row.get("description", ""),
        eligibility_flags=json.loads(row.get("eligibility_flags") or "[]"),
        fit_score=row.get("fit_score", 0),
    )


def select_candidates(db: DB, scope: str, min_fit: int) -> list[dict[str, Any]]:
    """Return open postings matching the chosen scope (spec §8 alert-rule style)."""
    rows = db.open_postings(seattle_only=(scope == "seattle"))
    out = []
    for r in rows:
        app = db.get_application(r["id"]) or {}
        status = app.get("status", "new")
        if scope == "reviewing":
            if status != "reviewing":
                continue
        else:
            if status != "new":
                continue
            if r.get("fit_score", 0) < min_fit:
                continue
        out.append(r)
    return out


def prepare_one(db: DB, row: dict[str, Any], use_llm: bool = True) -> dict[str, Any]:
    """Prepare a single posting. Returns {id, company, title, state, ...}.

    Nothing is marked Ready here — Ready means YOU approved the resume. This only
    decides: hold (real gaps), tailor + await review (strong), or tailor a generic
    pass and flag it (thin JD).
    """
    from .assess import assess

    posting = _row_to_posting(row)

    # Notes first — powers the drawer's three blocks and the /gaps rollup.
    note = notes_mod.generate(posting, use_llm=use_llm)
    db.set_notes(posting.id, note)
    for kw in note["keyword_coverage"]["present"]:
        db.bump_keyword(kw, covered=True)
    for kw in note["keyword_coverage"]["missing"]:
        db.bump_keyword(kw, covered=False)

    a = assess(posting)
    base = {"id": posting.id, "company": posting.company_name, "title": posting.title,
            "gaps": a.missing_must, "note": a.note}

    # GATE: missing must-have skills -> hold, do not tailor.
    if a.state == "needs_improvement":
        db.set_prep_state(posting.id, "needs_improvement", meta={"assessment": a.to_dict()})
        return {**base, "state": "needs_improvement"}

    # strong or thin_jd -> tailor (so there is a file), but await your approval.
    from .tailor import tailor

    try:
        result = tailor(posting, use_llm=use_llm)
        db.set_resume(posting.id, result["tex_path"], result["pdf_path"])
        meta = {
            "assessment": a.to_dict(),
            "diff": result["diff"],
            "changed_count": result["changed_count"],
            "coverage": result["keyword_coverage"],
        }
        db.set_prep_state(posting.id, a.state if a.state == "thin_jd" else "tailored", meta=meta)
        return {**base, "state": a.state if a.state == "thin_jd" else "tailored",
                "changed_count": result["changed_count"],
                "resume_tex": result["tex_path"], "resume_pdf": result["pdf_path"]}
    except Exception as exc:  # tailoring must never crash the batch
        log.warning("tailor failed for %s: %s", posting.id, exc)
        db.set_prep_state(posting.id, "needs_improvement", meta={"assessment": a.to_dict()})
        return {**base, "state": "error", "error": str(exc)}


def run(
    db: Optional[DB] = None,
    scope: Optional[str] = None,
    min_fit: Optional[int] = None,
    limit: Optional[int] = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Run auto-prepare over the selected candidates and return a summary."""
    cfg = load_config()
    aa = cfg.get("autoapply", {})
    scope = scope or aa.get("scope", "seattle")
    min_fit = min_fit if min_fit is not None else aa.get("min_fit", cfg["scoring"]["alert_threshold"])
    limit = limit if limit is not None else aa.get("limit", 25)

    own_db = db is None
    db = db or DB()
    candidates = select_candidates(db, scope, min_fit)[:limit]

    results = [prepare_one(db, row, use_llm=use_llm) for row in candidates]

    summary = {
        "scope": scope,
        "min_fit": min_fit,
        "considered": len(candidates),
        "tailored": sum(1 for r in results if r["state"] == "tailored"),
        "thin_jd": sum(1 for r in results if r["state"] == "thin_jd"),
        "needs_improvement": sum(1 for r in results if r["state"] == "needs_improvement"),
        "results": results,
    }
    if own_db:
        db.close()
    return summary
