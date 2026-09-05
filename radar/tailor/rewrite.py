"""LLM re-angling + guardrails (spec §10.2 rephrase()).

The rewriter may ONLY re-angle text that already exists in the bank. No new
employers, titles, dates, technologies, or metrics. If the LLM is unavailable or
a rewrite fails verification, the verbatim bullet is used.
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..llm import complete
from .bank import Bullet
from .verify import verify_bullet


def rephrase(bullets: list[Bullet], reqs: dict[str, Any], use_llm: bool = True) -> dict[str, str]:
    """Return {bullet_id: rephrased_text}. Falls back to verbatim on any failure."""
    result = {b.id: b.text for b in bullets}
    if not (use_llm and bullets):
        return result

    must = ", ".join(reqs.get("must_have", [])) or "n/a"
    nice = ", ".join(reqs.get("nice_to_have", [])) or "n/a"
    keywords = ", ".join(reqs["keywords"]) or "general software engineering"
    domain = reqs.get("domain", "software")
    payload = [{"id": b.id, "text": b.text} for b in bullets]
    prompt = (
        f"You are tailoring a resume for a specific {domain} internship.\n"
        f"This role's MUST-HAVE skills: {must}\n"
        f"Nice-to-have: {nice}\n"
        f"All JD keywords: {keywords}\n\n"
        "Rewrite EACH bullet so it foregrounds the angle most relevant to THIS role — "
        "lead with the JD-relevant technology or outcome, use the JD's own vocabulary where it "
        "honestly applies, and put the strongest signal first. Make each rewrite meaningfully "
        "different from the original in emphasis and phrasing (not a trivial reword).\n"
        "STRICT RULES (non-negotiable): do NOT introduce any employer, job title, date, "
        "technology, tool, or number that is not already in the original bullet. You may only "
        "re-angle and rephrase facts that are already there — never invent capabilities. "
        "Keep each bullet to one line, strong action verb first.\n"
        'Return strict JSON: a list of {"id":"","text":""}.\n\n'
        f"Bullets:\n{json.dumps(payload)}"
    )
    out = complete(prompt, max_tokens=1100, temperature=0.4)
    if not out:
        return result

    m = re.search(r"\[.*\]", out, re.DOTALL)
    if not m:
        return result
    try:
        rewritten = json.loads(m.group(0))
    except json.JSONDecodeError:
        return result

    by_id = {b.id: b for b in bullets}
    for item in rewritten:
        bid, new_text = item.get("id"), item.get("text", "")
        if bid not in by_id or not new_text:
            continue
        # Guardrail #2: diff every claim against the bank; keep verbatim on failure.
        if verify_bullet(by_id[bid].text, new_text):
            result[bid] = new_text.strip()
    return result
