"""The Notes engine — the differentiator (spec §11).

Deterministic layer first, LLM second. For each posting produce three blocks:
gaps, do-this, standout. Diff the JD keywords against the experience bank's tags
to find gaps (no model needed), map gaps through remediation.yaml for consistent
advice, then optionally compose the prose with one LLM call. Also feeds the
`/gaps` cross-posting rollup via keyword_stats.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from .config import data_path
from .llm import complete
from .models import Posting
from .score import extract_jd_stack, _your_stack


@lru_cache(maxsize=1)
def _remediation() -> dict[str, Any]:
    with open(data_path("remediation.yaml"), "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@lru_cache(maxsize=1)
def _bank_tags() -> set[str]:
    with open(data_path("experience.yaml"), "r", encoding="utf-8") as fh:
        bank = yaml.safe_load(fh)
    tags: set[str] = set()
    for section in ("experiences", "projects"):
        for item in bank.get(section, []):
            for b in item.get("bullets", []):
                for t in b.get("tags", []):
                    tags.add(t.lower())
            for s in item.get("stack", []):
                tags.add(s.lower())
    for group in bank.get("skills", {}).values():
        for s in group:
            tags.add(s.lower())
    return tags


def compute_gaps(posting: Posting) -> dict[str, Any]:
    """Return {jd_stack, matched, missing} for a posting."""
    jd_stack = extract_jd_stack(f"{posting.title} {posting.description}")
    yours = _your_stack() | _bank_tags()
    matched = sorted(jd_stack & yours)
    missing = sorted(jd_stack - yours)
    return {"jd_stack": sorted(jd_stack), "matched": matched, "missing": missing}


def _remediation_for(missing: list[str]) -> list[dict[str, Any]]:
    rem = _remediation()
    actions = []
    for gap in missing:
        entry = rem.get(gap)
        if entry:
            actions.append({"gap": gap, **entry})
    # Rank by a rough effort-to-impact heuristic: shorter effort first.
    order = {"none": 0, "1 evening": 1, "1 weekend": 2}
    actions.sort(key=lambda a: order.get(a.get("effort", ""), 3))
    return actions


def _deterministic_blocks(posting: Posting, gaps: dict[str, Any], actions: list[dict[str, Any]]) -> dict[str, str]:
    missing = gaps["missing"]
    matched = gaps["matched"]

    if missing:
        gap_block = "Missing: " + ", ".join(missing) + "."
        if matched:
            gap_block += f" You do have {', '.join(matched[:4])} on the page."
    else:
        gap_block = "No hard skill gaps against this JD — your stack covers what it lists."

    if actions:
        top = actions[0]
        do_block = f"Highest leverage: {top['action']} ({top.get('effort', '')})."
        if len(actions) > 1:
            do_block += f" Then: {actions[1]['action']}"
    else:
        do_block = "Nothing blocking. Tailor the resume to lead with the matched stack and apply early."

    # Standout: company-tier aware.
    slug = posting.company_slug
    if slug == "amazon":
        standout = ("Amazon screens on Leadership Principles. Your MechXcel $20k fundraise + 120 students is a "
                    "stronger Ownership story than most interns' — lead behavioral prep with it and keep the number "
                    "in the resume's top third.")
    elif any(t in posting.description.lower() for t in ("backend", "distributed", "api", "database")):
        standout = ("Lead with the Thunderbolts row-level security + booking-concurrency rule — that's production "
                    "reasoning at an intern level and most applicants have nothing like it.")
    elif any(t in posting.description.lower() for t in ("ai", "ml", "machine learning", "llm")):
        standout = ("Lead with Linx's Nemoclaw deterministic-override layer — knowing when NOT to trust a model is "
                    "genuine systems judgment and it placed 4th at BeaverHacks.")
    else:
        standout = ("Foreground one bullet with a hard number in the top third, and lead with the project whose stack "
                    "overlaps this JD most.")
    return {"gaps": gap_block, "actions": do_block, "standout": standout}


def _llm_blocks(posting: Posting, gaps: dict[str, Any], actions: list[dict[str, Any]]) -> dict[str, str] | None:
    prompt = (
        "You are advising a CS undergrad on a specific internship. Write THREE short blocks, "
        "under 120 words TOTAL, plain prose, no markdown headers. Block 1 'gaps': requirements in "
        "the JD with no evidence in the candidate's background. Block 2 'actions': the smallest concrete "
        "action that closes the biggest gap, ranked by effort-to-impact. Block 3 'standout': what would "
        "make THIS reviewer stop. Return strict JSON {\"gaps\":\"\",\"actions\":\"\",\"standout\":\"\"}.\n\n"
        f"Company: {posting.company_name}\nTitle: {posting.title}\n"
        f"Missing skills: {', '.join(gaps['missing']) or 'none'}\n"
        f"Matched skills: {', '.join(gaps['matched']) or 'none'}\n"
        f"Suggested actions: {'; '.join(a['action'] for a in actions[:2]) or 'none'}\n"
        f"JD excerpt: {posting.description[:1200]}"
    )
    out = complete(prompt, max_tokens=400)
    if not out:
        return None
    import json
    import re
    m = re.search(r"\{.*\}", out, re.DOTALL)
    if not m:
        return None
    try:
        parsed = json.loads(m.group(0))
        if all(k in parsed for k in ("gaps", "actions", "standout")):
            return {k: str(parsed[k]) for k in ("gaps", "actions", "standout")}
    except json.JSONDecodeError:
        return None
    return None


def generate(posting: Posting, use_llm: bool = True) -> dict[str, Any]:
    """Produce the notes payload stored on the application row."""
    gaps = compute_gaps(posting)
    actions = _remediation_for(gaps["missing"])
    blocks = None
    if use_llm:
        blocks = _llm_blocks(posting, gaps, actions)
    if blocks is None:
        blocks = _deterministic_blocks(posting, gaps, actions)
    return {
        "gaps": blocks["gaps"],
        "actions": blocks["actions"],
        "standout": blocks["standout"],
        "keyword_coverage": {"present": gaps["matched"], "missing": gaps["missing"]},
        "remediation": actions,
    }
