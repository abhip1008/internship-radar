"""Filtering: what counts as a CS internship (spec §6).

Run cheapest first, tune permissive. A false negative is expensive; a false
positive costs three seconds of scrolling. Every rejection is returned with a
reason so the caller can log it and audit for silently-dropped real postings.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .models import Posting

TITLE_INCLUDE = [
    "intern", "internship", "co-op", "coop", "summer analyst", "apprentice",
    "university", "new grad", "new graduate", "early career", "entry level",
    "student", "campus", "2027", "2026", "trainee", "residency",
]

CS_INCLUDE_CORE = [
    "software", "swe", "sde", "developer", "computer science", "computer engineering",
    "data scientist", "data analyst", "research scientist", "quantitative developer",
    "technical program manager", "solutions architect", "applied scientist",
]
# "engineer" only counts as CS when paired with a technical qualifier.
ENGINEER_QUALIFIERS = [
    "software", "platform", "backend", "frontend", "full stack", "fullstack",
    "systems", "infrastructure", "cloud", "data", "ml", "machine learning", "ai",
    "security", "devops", "site reliability", "sre", "embedded", "firmware",
    "mobile", "ios", "android", "qa", "test", "automation",
]

CS_EXCLUDE = [
    "sales", "marketing", "recruiting", "recruiter", "hr ", "human resources",
    "legal", "nursing", "warehouse", "driver", "retail associate", "cashier",
    "barista", "custodian", "accounting",
]

TERM_INCLUDE_DEFAULT = {"summer-2027", "summer-2026", "fall-2026", "off-cycle", "unspecified"}

ELIGIBILITY_FLAGS = {
    "PhD required": r"ph\.?d\.?\s*(required|preferred|candidate)",
    "Master's required": r"master'?s?\s*(degree\s*)?(required|preferred)",
    "Graduating by": r"must be graduating by|graduat\w* (in|by)\s*20\d\d",
    "US citizenship required": r"u\.?s\.?\s*citizen(ship)?\s*(required|only)",
    "Security clearance": r"(active\s*)?security clearance|ts/sci|secret clearance",
    "No visa sponsorship": r"no\s*(visa\s*)?sponsorship|not able to sponsor|without sponsorship",
}


@dataclass
class FilterResult:
    passed: bool
    reason: Optional[str] = None
    eligibility_flags: list[str] = None

    def __post_init__(self):
        if self.eligibility_flags is None:
            self.eligibility_flags = []


from functools import lru_cache


@lru_cache(maxsize=None)
def _compiled(needles: tuple[str, ...]) -> "re.Pattern":
    """Word-boundary regex for a needle list so `intern` doesn't match `internal`
    and `it` doesn't match `audit` (§6 — avoid silent false positives/negatives)."""
    parts = [r"\b" + re.escape(n.strip()) + r"\b" for n in needles]
    return re.compile("|".join(parts))


def _any(text: str, needles: list[str]) -> bool:
    return bool(_compiled(tuple(needles)).search(text))


def is_early_career(title: str) -> bool:
    return _any(title.lower(), TITLE_INCLUDE)


# Standalone technical tokens that make a title CS on their own (permissive by
# design — a false negative is expensive; §6).
CS_STANDALONE = [
    "software", "developer", "swe", "sde", "ml", "machine learning", "ai",
    "data", "research", "systems", "cloud", "security", "devops", "sre",
    "embedded", "firmware", "ios", "android", "mobile", "qa", "test", "it",
    "technical", "programmer", "computer",
]


def is_cs(title: str, description: str = "") -> bool:
    t = f" {title.lower()} "
    if _any(t, CS_INCLUDE_CORE):
        return True
    if "engineer" in t and _any(t, ENGINEER_QUALIFIERS):
        return True
    if _any(t, CS_STANDALONE):
        return True
    # Fall back to description for thinly-titled reqs (e.g. "Technical Intern").
    if "engineer" in t or "technical" in t:
        d = description.lower()
        if _any(d, ENGINEER_QUALIFIERS) or _any(d, CS_INCLUDE_CORE):
            return True
    return False


def eligibility_flags(description: str) -> list[str]:
    text = description.lower()
    return [label for label, pat in ELIGIBILITY_FLAGS.items() if re.search(pat, text)]


def evaluate(posting: Posting, target_terms: Optional[set[str]] = None) -> FilterResult:
    """Apply the §6 filter chain. Geography never filters out — it only ranks."""
    title = posting.title
    terms = target_terms or TERM_INCLUDE_DEFAULT

    if _any(title.lower(), CS_EXCLUDE):
        return FilterResult(False, "cs_exclude_title")
    if not is_early_career(title):
        return FilterResult(False, "not_early_career")
    if not is_cs(title, posting.description):
        return FilterResult(False, "not_cs")
    if posting.term not in terms:
        return FilterResult(False, f"term_excluded:{posting.term}")

    flags = eligibility_flags(posting.description)
    return FilterResult(True, None, flags)
