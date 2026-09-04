"""Normalize a RawPosting into a canonical Posting (spec §6.3, §6.4).

Handles geo resolution against the static gazetteer and term classification.
Filtering and scoring happen downstream; this step only shapes the data.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import yaml

from .config import data_path
from .models import Posting, RawPosting


@lru_cache(maxsize=1)
def _gazetteer() -> dict[str, Any]:
    with open(data_path("gazetteer.yaml"), "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _clean(text: str) -> str:
    return re.sub(r"[^a-z0-9 ,()/-]+", " ", (text or "").lower()).strip()


def resolve_geo(location_text: str, description: str = "") -> dict[str, Any]:
    """Return {locations, is_seattle_metro, is_remote_us, is_wa} for a location string."""
    gaz = _gazetteer()
    cleaned = _clean(location_text)
    haystack = cleaned + " " + _clean(description[:400])

    is_metro = any(city in haystack for city in gaz["seattle_metro"])
    is_remote = any(r in cleaned for r in gaz["remote_us"]) or (
        "remote" in cleaned and ("us" in cleaned or "united states" in cleaned or not cleaned.replace("remote", "").strip())
    )
    is_wa = is_metro or any(w in haystack for w in gaz["washington"])

    # Build a normalized display list.
    locations: list[str] = []
    canonical = gaz.get("canonical", {})
    for city, disp in canonical.items():
        if city in haystack and disp not in locations:
            locations.append(disp)
    if is_remote and "Remote (US)" not in locations:
        locations.append("Remote (US)")
    if not locations and location_text.strip():
        locations.append(location_text.strip())
    return {
        "locations": locations,
        "is_seattle_metro": is_metro,
        "is_remote_us": is_remote,
        "is_wa": is_wa,
    }


TERM_PATTERNS = [
    ("summer-2027", r"summer\s*20?27"),
    ("summer-2026", r"summer\s*20?26"),
    ("fall-2026", r"fall\s*20?26"),
    ("fall-2027", r"fall\s*20?27"),
    ("winter-2027", r"winter\s*20?27"),
    ("spring-2027", r"spring\s*20?27"),
    ("off-cycle", r"\b(co-?op|year-?round|off-?cycle)\b"),
]


def classify_term(title: str, description: str) -> str:
    text = f"{title} {description}".lower()
    for term, pat in TERM_PATTERNS:
        if re.search(pat, text):
            return term
    return "unspecified"


def normalize(raw: RawPosting) -> Posting:
    geo = resolve_geo(raw.location_text, raw.description)
    term = classify_term(raw.title, raw.description)
    now = datetime.now(timezone.utc)
    return Posting(
        id="",  # assigned by dedupe
        company_slug=raw.company_slug,
        company_name=raw.company_name,
        title=raw.title.strip(),
        apply_url=raw.apply_url.strip(),
        ats_job_id=raw.ats_job_id,
        locations=geo["locations"],
        is_seattle_metro=geo["is_seattle_metro"],
        is_remote_us=geo["is_remote_us"],
        is_wa=geo["is_wa"],
        term=term,
        description=raw.description,
        posted_at=raw.posted_at,
        first_seen_at=now,
        last_seen_at=now,
        sources=[{"type": raw.source_type, "url": raw.source_url}],
        raw=raw.raw,
    )
