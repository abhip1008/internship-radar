"""Close-date resolution — the honest version (spec §9).

Three states: explicit (parsed from text), rolling (stated or known-rolling big
tech), estimated (per-company historical median with a global fallback). Never
fabricate a hard deadline; estimates are labelled low-confidence.
"""
from __future__ import annotations

import re
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from dateutil import parser as dtparser

from .models import Posting

EXPLICIT_PATTERNS = [
    r"applications?\s+close[sd]?\s+(?:on\s+)?([A-Z][a-z]+ \d{1,2},? \d{4})",
    r"apply\s+by\s+([A-Z][a-z]+ \d{1,2},? \d{4})",
    r"deadline[:\s]+([A-Z][a-z]+ \d{1,2},? \d{4})",
    r"open until\s+([A-Z][a-z]+ \d{1,2},? \d{4})",
    r"priority deadline[:\s]+([A-Z][a-z]+ \d{1,2},? \d{4})",
    r"will close on\s+([A-Z][a-z]+ \d{1,2},? \d{4})",
]

ROLLING_PATTERNS = [
    r"\brolling\b", r"until filled", r"as we receive applications",
    r"reviewed on a rolling basis",
]

# Big-tech that is effectively always rolling for interns.
KNOWN_ROLLING = {"amazon", "microsoft", "google", "meta", "apple", "nvidia"}


def _find_explicit(description: str) -> Optional[tuple[str, str]]:
    for pat in EXPLICIT_PATTERNS:
        m = re.search(pat, description, re.IGNORECASE)
        if m:
            try:
                parsed = dtparser.parse(m.group(1))
                # Grab the source sentence for the hover tooltip.
                start = description.rfind(".", 0, m.start()) + 1
                end = description.find(".", m.end())
                sentence = description[start : end if end != -1 else m.end() + 40].strip()
                return parsed.date().isoformat(), sentence[:200]
            except (ValueError, OverflowError):
                continue
    return None


def resolve(
    posting: Posting,
    company_lifetimes: Optional[list[float]] = None,
    global_fallback_days: int = 21,
) -> dict[str, Any]:
    """Return {closes_at, closes_kind, closes_evidence}."""
    desc = posting.description or ""

    explicit = _find_explicit(desc)
    if explicit:
        return {"closes_at": explicit[0], "closes_kind": "explicit", "closes_evidence": explicit[1]}

    if posting.company_slug in KNOWN_ROLLING or any(re.search(p, desc, re.IGNORECASE) for p in ROLLING_PATTERNS):
        return {"closes_at": None, "closes_kind": "rolling", "closes_evidence": "Rolling — apply now"}

    # Estimated: per-company median lifetime, else global fallback.
    days = global_fallback_days
    if company_lifetimes:
        try:
            days = int(statistics.median(company_lifetimes))
        except statistics.StatisticsError:
            days = global_fallback_days
    base = posting.first_seen_at or datetime.now(timezone.utc)
    if isinstance(base, datetime):
        base = base.date()
    est = base + timedelta(days=max(days, 3))
    return {
        "closes_at": est.isoformat(),
        "closes_kind": "estimated",
        "closes_evidence": f"~est: {days}d median lifetime",
    }


def days_remaining(closes_at: Optional[str]) -> Optional[int]:
    if not closes_at:
        return None
    try:
        d = date.fromisoformat(closes_at)
        return (d - datetime.now(timezone.utc).date()).days
    except ValueError:
        return None
