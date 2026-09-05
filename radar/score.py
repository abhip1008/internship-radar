"""Fit score — explainable, five components, no ML (spec §15).

Every score carries its breakdown so the UI can show why. A score you can't
interrogate is a score you stop trusting by week two.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

import yaml

from .config import data_path, load_config
from .models import Posting

@lru_cache(maxsize=1)
def _vocab() -> dict[str, str]:
    """alias -> canonical skill name (data/skills_vocab.yaml)."""
    with open(data_path("skills_vocab.yaml"), "r", encoding="utf-8") as fh:
        return {str(k).lower(): str(v).lower() for k, v in yaml.safe_load(fh).items()}


@lru_cache(maxsize=1)
def _your_stack() -> set[str]:
    """The candidate's real skills: declared skills + every tag/stack token in the
    experience bank, all mapped through the vocab to canonical names. This is the
    honest 'what you actually have' set used for gap detection."""
    with open(data_path("experience.yaml"), "r", encoding="utf-8") as fh:
        bank = yaml.safe_load(fh)
    vocab = _vocab()
    out: set[str] = set()

    def add(token: str) -> None:
        t = token.lower().strip()
        out.add(t)
        if t in vocab:
            out.add(vocab[t])

    for group in bank.get("skills", {}).values():
        for item in group:
            add(item)
    for item in bank.get("demonstrated", []):
        add(item)
    for course in bank.get("identity", {}).get("education", {}).get("coursework", []):
        add(course)
    for section in ("experiences", "projects"):
        for item in bank.get(section, []):
            for s in item.get("stack", []):
                add(s)
            for b in item.get("bullets", []):
                for tag in b.get("tags", []):
                    add(tag)
    return out


def extract_jd_stack(text: str) -> set[str]:
    """Canonical skills mentioned in a JD (word-boundary matched against vocab)."""
    t = text.lower()
    vocab = _vocab()
    found: set[str] = set()
    for alias, canonical in vocab.items():
        if re.search(r"(?<![\w+#.])" + re.escape(alias) + r"(?![\w+#])", t):
            found.add(canonical)
    return found


def score(posting: Posting, company: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    cfg = load_config()
    weights = cfg["scoring"]["weights"]
    breakdown: dict[str, Any] = {}

    # Location (30)
    if posting.is_seattle_metro:
        loc_pts, loc_why = weights["location"], "Seattle metro"
    elif posting.is_remote_us:
        loc_pts, loc_why = round(weights["location"] * 0.73), "Remote (US)"
    elif posting.is_wa:
        loc_pts, loc_why = round(weights["location"] * 0.67), "Washington"
    else:
        loc_pts, loc_why = round(weights["location"] * 0.17), "elsewhere"
    breakdown["location"] = {"points": loc_pts, "max": weights["location"], "why": loc_why}

    # Term (20)
    targets = set(cfg["profile"]["target_terms"])
    if posting.term in {"summer-2027", "fall-2026"} and posting.term in targets:
        term_pts, term_why = weights["term"], f"target term ({posting.term})"
    elif posting.term == "off-cycle":
        term_pts, term_why = round(weights["term"] * 0.7), "off-cycle"
    elif posting.term == "unspecified":
        term_pts, term_why = round(weights["term"] * 0.5), "unspecified term"
    elif posting.term in targets:
        term_pts, term_why = round(weights["term"] * 0.7), posting.term
    else:
        term_pts, term_why = 0, f"wrong term ({posting.term})"
    breakdown["term"] = {"points": term_pts, "max": weights["term"], "why": term_why}

    # Stack overlap (25)
    jd_stack = extract_jd_stack(f"{posting.title} {posting.description}")
    yours = _your_stack()
    if jd_stack:
        overlap = jd_stack & yours
        frac = len(overlap) / len(jd_stack)
        stack_pts = round(frac * weights["stack_overlap"])
        stack_why = f"{len(overlap)}/{len(jd_stack)} JD techs matched"
    else:
        stack_pts = round(weights["stack_overlap"] * 0.5)
        stack_why = "no explicit stack in JD"
    breakdown["stack_overlap"] = {
        "points": stack_pts, "max": weights["stack_overlap"], "why": stack_why,
        "matched": sorted(jd_stack & yours), "missing": sorted(jd_stack - yours),
    }

    # Level fit (15)
    hard_mismatch = any(f in posting.eligibility_flags for f in ("PhD required", "Master's required"))
    if hard_mismatch:
        level_pts, level_why = 0, "PhD/Master's required"
    elif re.search(r"rising senior|graduating (in|by) 202[567]", posting.description, re.IGNORECASE):
        level_pts, level_why = round(weights["level_fit"] * 0.53), "prefers rising senior"
    else:
        level_pts, level_why = weights["level_fit"], "eligible"
    breakdown["level_fit"] = {"points": level_pts, "max": weights["level_fit"], "why": level_why}

    # Company tier (10)
    watchlist = bool(company and company.get("watchlist"))
    tier = (company or {}).get("tier", 2)
    if watchlist:
        comp_pts, comp_why = weights["company_tier"], "watchlist"
    elif tier == 0:
        comp_pts, comp_why = round(weights["company_tier"] * 0.7), "known-good (Tier 0)"
    else:
        comp_pts, comp_why = round(weights["company_tier"] * 0.5), "unknown"
    breakdown["company_tier"] = {"points": comp_pts, "max": weights["company_tier"], "why": comp_why}

    total = sum(c["points"] for c in breakdown.values())
    return min(total, 100), breakdown
