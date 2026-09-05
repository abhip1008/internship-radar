"""Tailoring orchestrator (spec §10.2).

Ties the stages together: extract -> select -> rephrase (guarded) -> render.
Also produces the keyword-coverage report (§10) that flows into Notes.
"""
from __future__ import annotations

from typing import Any

from ..models import Posting
from .extract import extract_requirements
from .rewrite import rephrase
from .select import select


def keyword_coverage(reqs: dict[str, Any], selected_texts: list[str]) -> dict[str, list[str]]:
    """Which JD keywords made it into the resume text vs. which are missing (§10)."""
    blob = " ".join(selected_texts).lower()
    present, missing = [], []
    for kw in reqs["keywords"]:
        (present if kw in blob else missing).append(kw)
    return {"present": present, "missing": missing}


def tailor(posting: Posting, use_llm: bool = True) -> dict[str, Any]:
    """Run the full tailoring pipeline for one posting.

    Returns paths + the coverage report. Rendering is imported lazily so the
    selection logic stays testable without a LaTeX toolchain.
    """
    jd = f"{posting.title}\n\n{posting.description}"
    reqs = extract_requirements(jd)
    selection = select(reqs)

    all_bullets = [b for grp in ("experiences", "projects") for bl in selection[grp].values() for b in bl]
    rephrased = rephrase(all_bullets, reqs, use_llm=use_llm)

    from .render import render  # lazy: avoids importing jinja/subprocess for pure selection tests
    rendered = render(posting.company_name, posting.title, selection, rephrased)

    coverage = keyword_coverage(reqs, list(rephrased.values()))

    # Diff vs. base: which selected bullets were re-angled for this specific post,
    # so approving in the UI is an informed click (spec §10 guardrail #3).
    diff = []
    for b in all_bullets:
        final = rephrased.get(b.id, b.text)
        diff.append({
            "id": b.id,
            "source": b.source_name,
            "base": b.text,
            "final": final,
            "changed": final.strip() != b.text.strip(),
        })
    changed_count = sum(1 for d in diff if d["changed"])

    return {
        "requirements": reqs,
        "tex_path": rendered["tex_path"],
        "pdf_path": rendered["pdf_path"],
        "keyword_coverage": coverage,
        "selected_bullet_ids": [b.id for b in all_bullets],
        "diff": diff,
        "changed_count": changed_count,
        "rephrased": rephrased,
    }
