"""Canonical data schema shared across the pipeline.

`RawPosting` is what a collector emits — messy, source-specific fields already
mapped onto a common shape. `Posting` is the normalized, filtered, scored row
that lands in SQLite and drives the UI.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class RawPosting(BaseModel):
    """One posting as a collector first sees it, before normalize/filter/dedupe."""

    company_slug: str
    company_name: str
    title: str
    apply_url: str
    ats_job_id: Optional[str] = None
    location_text: str = ""
    description: str = ""
    posted_at: Optional[datetime] = None
    source_type: str = "unknown"       # greenhouse | lever | github-list | rss | ...
    source_url: Optional[str] = None
    raw: dict[str, Any] = Field(default_factory=dict)


class Posting(BaseModel):
    """Normalized posting written to the DB."""

    id: str                             # dedupe hash / primary key
    company_slug: str
    company_name: str
    title: str
    apply_url: str
    ats_job_id: Optional[str] = None

    locations: list[str] = Field(default_factory=list)
    is_seattle_metro: bool = False
    is_remote_us: bool = False
    is_wa: bool = False

    term: str = "unspecified"           # summer-2027 | fall-2026 | off-cycle | unspecified
    description: str = ""

    posted_at: Optional[datetime] = None       # company-claimed, untrusted
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None

    closes_at: Optional[str] = None            # ISO date string
    closes_kind: str = "unknown"               # explicit | rolling | estimated | unknown
    closes_evidence: Optional[str] = None
    is_closed: bool = False

    fit_score: int = 0
    fit_breakdown: dict[str, Any] = Field(default_factory=dict)
    eligibility_flags: list[str] = Field(default_factory=list)

    sources: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
