"""Honest readiness assessment for a posting.

Answers: "can I even judge this, and is it a genuine match?" — deliberately
conservative so the UI never over-claims "ready". Nothing here marks a posting
Ready; that word is now reserved for résumés YOU have approved. This produces the
state auto-prepare and the drawer use to explain WHY.

States:
  strong           enough JD text, no missing must-have skills -> worth tailoring
  needs_improvement missing must-have skills -> hold, list the gaps
  thin_jd          too little JD text to judge -> tailor only a generic pass, flag it
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import Posting
from .score import _your_stack, extract_jd_stack
from .tailor.extract import extract_requirements

# A JD shorter than this can't be honestly assessed (most list-only postings).
MIN_JD_CHARS = 300


@dataclass
class Assessment:
    state: str                      # strong | needs_improvement | thin_jd
    missing_must: list[str] = field(default_factory=list)
    missing_nice: list[str] = field(default_factory=list)
    matched: list[str] = field(default_factory=list)
    jd_chars: int = 0
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "missing_must": self.missing_must,
            "missing_nice": self.missing_nice,
            "matched": self.matched,
            "jd_chars": self.jd_chars,
            "note": self.note,
        }


def assess(posting: Posting) -> Assessment:
    desc = posting.description or ""
    yours = _your_stack()
    reqs = extract_requirements(f"{posting.title}\n{desc}")

    must = set(reqs["must_have"])
    nice = set(reqs["nice_to_have"])
    all_jd = set(reqs["keywords"])
    missing_must = sorted(must - yours)
    missing_nice = sorted(nice - yours)
    matched = sorted(all_jd & yours)

    # Not enough JD text to judge — be honest rather than optimistic.
    if len(desc.strip()) < MIN_JD_CHARS:
        return Assessment(
            state="thin_jd",
            missing_must=missing_must,
            missing_nice=missing_nice,
            matched=matched,
            jd_chars=len(desc.strip()),
            note="Limited job-description text — can't fully assess fit. Open the posting to read the full JD, then regenerate.",
        )

    if missing_must:
        return Assessment(
            state="needs_improvement",
            missing_must=missing_must,
            missing_nice=missing_nice,
            matched=matched,
            jd_chars=len(desc.strip()),
            note="Missing must-have skills for this role: " + ", ".join(missing_must) + ".",
        )

    return Assessment(
        state="strong",
        missing_must=[],
        missing_nice=missing_nice,
        matched=matched,
        jd_chars=len(desc.strip()),
        note="Your background covers this JD's must-haves"
        + (f"; nice-to-haves you're missing: {', '.join(missing_nice)}." if missing_nice else "."),
    )
