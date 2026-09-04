"""Dedupe (spec §7).

Three keys, cheapest first. On collision the caller MERGES rather than drops
(handled in db.upsert_posting). This module just computes the canonical id and
provides a fuzzy in-batch matcher so duplicates arriving in the same sweep
collapse to one row before hitting the DB.
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit, urlunsplit

from rapidfuzz import fuzz

from .models import Posting

FUZZY_THRESHOLD = 92


def normalize_url(url: str) -> str:
    """Strip query/fragment and trailing slash for the exact-match key."""
    try:
        parts = urlsplit(url)
        path = parts.path.rstrip("/")
        return urlunsplit((parts.scheme, parts.netloc.lower(), path, "", ""))
    except ValueError:
        return url


def normalize_title(title: str) -> str:
    """Strip seniority noise, years, and req IDs for the fuzzy key."""
    t = title.lower()
    t = re.sub(r"\b(20\d\d)\b", "", t)
    t = re.sub(r"\b(req|job|id|#)\s*[:#]?\s*\w*\d+\w*", "", t)
    t = re.sub(r"\b(i{1,3}|iv|v|senior|sr|junior|jr|lead|staff|principal)\b", "", t)
    t = re.sub(r"[^a-z ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def location_bucket(posting: Posting) -> str:
    if posting.is_seattle_metro:
        return "seattle"
    if posting.is_remote_us:
        return "remote"
    if posting.is_wa:
        return "wa"
    return "other"


def compute_id(posting: Posting) -> str:
    """Exact key: sha1 of the normalized apply URL (spec §7.1)."""
    return hashlib.sha1(normalize_url(posting.apply_url).encode("utf-8")).hexdigest()


def strong_key(posting: Posting) -> str | None:
    if posting.ats_job_id:
        return f"{posting.company_slug}:{posting.ats_job_id}"
    return None


def fuzzy_key(posting: Posting) -> str:
    return f"{posting.company_slug}|{normalize_title(posting.title)}|{location_bucket(posting)}|{posting.term}"


def dedupe_batch(postings: list[Posting]) -> list[Posting]:
    """Collapse duplicates within a single sweep before writing to the DB.

    Merges locations and sources; keeps the longest description.
    """
    by_id: dict[str, Posting] = {}
    by_strong: dict[str, str] = {}      # strong_key -> id
    fuzzy_seen: list[tuple[str, str]] = []  # (fuzzy_key, id)

    for p in postings:
        p.id = compute_id(p)
        target_id: str | None = None

        if p.id in by_id:
            target_id = p.id
        else:
            sk = strong_key(p)
            if sk and sk in by_strong:
                target_id = by_strong[sk]
            else:
                fk = fuzzy_key(p)
                for seen_fk, seen_id in fuzzy_seen:
                    if seen_fk.split("|")[0] == fk.split("|")[0] and fuzz.token_set_ratio(fk, seen_fk) >= FUZZY_THRESHOLD:
                        target_id = seen_id
                        break

        if target_id is None:
            by_id[p.id] = p
            sk = strong_key(p)
            if sk:
                by_strong[sk] = p.id
            fuzzy_seen.append((fuzzy_key(p), p.id))
        else:
            _merge_into(by_id[target_id], p)

    return list(by_id.values())


def _merge_into(keep: Posting, other: Posting) -> None:
    keep.locations = sorted(set(keep.locations) | set(other.locations))
    keys = {(s.get("type"), s.get("url")) for s in keep.sources}
    keep.sources += [s for s in other.sources if (s.get("type"), s.get("url")) not in keys]
    if len(other.description) > len(keep.description):
        keep.description = other.description
    keep.is_seattle_metro = keep.is_seattle_metro or other.is_seattle_metro
    keep.is_remote_us = keep.is_remote_us or other.is_remote_us
    keep.is_wa = keep.is_wa or other.is_wa
    # Prefer an ATS-direct apply URL over an aggregator's.
    if not keep.ats_job_id and other.ats_job_id:
        keep.ats_job_id = other.ats_job_id
        keep.apply_url = other.apply_url
