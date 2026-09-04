"""Shared view assembly — turns DB rows into the shape the UI consumes.

Used by both the JSON export (static snapshot) and the live API server.
"""
from __future__ import annotations

import json
from typing import Any

from .db import DB
from .deadlines import days_remaining


def _loads(value: Any, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def posting_row(db: DB, row: dict[str, Any], detail: bool = False) -> dict[str, Any]:
    app = db.get_application(row["id"]) or {}
    notes = _loads(app.get("notes_json"), {})
    dr = days_remaining(row.get("closes_at"))
    out: dict[str, Any] = {
        "id": row["id"],
        "company": row["company_name"],
        "company_slug": row["company_slug"],
        "title": row["title"],
        "apply_url": row["apply_url"],
        "locations": _loads(row.get("locations"), []),
        "is_seattle_metro": bool(row.get("is_seattle_metro")),
        "is_remote_us": bool(row.get("is_remote_us")),
        "term": row.get("term"),
        "posted_at": row.get("posted_at"),
        "first_seen_at": row.get("first_seen_at"),
        "closes_at": row.get("closes_at"),
        "closes_kind": row.get("closes_kind"),
        "closes_evidence": row.get("closes_evidence"),
        "days_remaining": dr,
        "is_closed": bool(row.get("is_closed")),
        "fit": row.get("fit_score", 0),
        "fit_breakdown": _loads(row.get("fit_breakdown"), {}),
        "eligibility_flags": _loads(row.get("eligibility_flags"), []),
        "status": app.get("status", "new"),
        "resume_pdf": app.get("resume_pdf_path"),
        "resume_tex": app.get("resume_tex_path"),
        "resume_approved": bool(app.get("resume_approved")),
        "notes_preview": (notes.get("gaps", "") or "")[:160],
        "has_notes": bool(notes),
    }
    if detail:
        out["notes"] = notes
        out["sources"] = _loads(row.get("sources"), [])
        out["description"] = row.get("description", "")
        out["user_notes"] = app.get("user_notes", "")
    return out


def snapshot(db: DB, seattle_only: bool = False) -> dict[str, Any]:
    rows = db.open_postings(seattle_only=seattle_only)
    postings = [posting_row(db, r) for r in rows]
    new_today = sum(1 for p in postings if _is_today(p.get("first_seen_at")))
    seattle = sum(1 for p in postings if p["is_seattle_metro"])
    gaps = [g for g in db.keyword_rollup() if not g["covered"]]
    return {
        "postings": postings,
        "stats": {
            "open": len(postings),
            "seattle": seattle,
            "new_today": new_today,
            "gaps_top": gaps[:20],
        },
    }


def _is_today(iso: str | None) -> bool:
    if not iso:
        return False
    from datetime import datetime, timezone
    try:
        d = datetime.fromisoformat(iso)
        return d.date() == datetime.now(timezone.utc).date()
    except ValueError:
        return False
