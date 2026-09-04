"""Bullet selection + reorder (spec §10.2).

score_bullets(): tag/keyword overlap with the JD. select(): 2 experiences x 3-5
bullets, up to 3 projects x 2-3 bullets, 1-page cap. reorder(): most JD-relevant
project first, always keep one hard-number bullet in the top third.
"""
from __future__ import annotations

from typing import Any

from .bank import Bullet, all_bullets, load_bank

# Selection heuristics from §10.2 — which project leads which domain.
DOMAIN_LEAD = {
    "backend": ["everwell", "linx", "thunderbolts"],
    "ai-systems": ["linx", "everwell", "thunderbolts"],
    "fullstack-product": ["thunderbolts", "everwell", "resource-hub"],
    "frontend": ["resource-hub", "startup-club", "thunderbolts"],
}

# Bullets carrying a hard number (§10.2: keep one in the top third).
NUMBER_BULLETS = {"mechxcel-scale", "mechxcel-fundraising", "mechxcel-awards", "thunderbolts-db"}


def score_bullet(b: Bullet, reqs: dict[str, Any]) -> float:
    jd_terms = set(reqs["keywords"]) | set(w for kw in reqs["keywords"] for w in kw.split())
    tag_hits = len(set(b.tags) & jd_terms)
    stack_hits = len(set(b.stack) & set(reqs["keywords"]))
    domain_bonus = 1.5 if b.kind == reqs["domain"] else 0.0
    return tag_hits * 2 + stack_hits * 1.5 + domain_bonus


def select(reqs: dict[str, Any]) -> dict[str, Any]:
    bank = load_bank()
    bullets = all_bullets()
    scored = sorted(bullets, key=lambda b: score_bullet(b, reqs), reverse=True)

    # Group by source, preserving JD-relevance order.
    experiences_order = _order_sources(bank, "experiences", reqs)
    projects_order = _order_sources(bank, "projects", reqs)

    chosen_exp = _pick(scored, experiences_order[:2], per=4, reqs=reqs)
    chosen_proj = _pick(scored, projects_order[:3], per=3, reqs=reqs)

    selected_ids = {b.id for group in (chosen_exp, chosen_proj) for bl in group.values() for b in bl}

    # Ensure one hard-number bullet is present (top-third rule enforced at render).
    if not (selected_ids & NUMBER_BULLETS):
        for b in bullets:
            if b.id in NUMBER_BULLETS:
                src = b.source_id
                target = chosen_exp if any(b2.source_id == src for grp in chosen_exp.values() for b2 in grp) else None
                (chosen_exp if target is not None else chosen_exp).setdefault(src, []).insert(0, b)
                break

    return {
        "experiences": chosen_exp,
        "projects": chosen_proj,
        "skills_order": _reorder_skills(bank, reqs),
    }


def _order_sources(bank: dict[str, Any], section: str, reqs: dict[str, Any]) -> list[str]:
    items = bank.get(section, [])
    lead = DOMAIN_LEAD.get(reqs["domain"], [])
    ids = [it.get("id") for it in items if it.get("id")]
    original = {i: pos for pos, i in enumerate(ids)}  # stable pre-sort order
    return sorted(ids, key=lambda i: (lead.index(i) if i in lead else len(lead) + original[i]))


def _pick(scored: list[Bullet], source_ids: list[str], per: int, reqs: dict[str, Any]) -> dict[str, list[Bullet]]:
    out: dict[str, list[Bullet]] = {}
    for sid in source_ids:
        group = [b for b in scored if b.source_id == sid][:per]
        if group:
            out[sid] = group
    return out


def _reorder_skills(bank: dict[str, Any], reqs: dict[str, Any]) -> dict[str, list[str]]:
    """Lead each skill line with the JD's stack (§10.2)."""
    jd = set(reqs["keywords"])
    skills = bank.get("skills", {})
    ordered: dict[str, list[str]] = {}
    for group, items in skills.items():
        items_sorted = sorted(items, key=lambda s: (s.lower() not in jd, items.index(s)))
        ordered[group] = items_sorted
    return ordered
