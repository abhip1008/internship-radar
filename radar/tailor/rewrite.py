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

    keywords = ", ".join(reqs["keywords"]) or "general software engineering"
    payload = [{"id": b.id, "text": b.text} for b in bullets]
    prompt = (
        "Re-angle each resume bullet to foreground these JD-relevant themes: "
        f"{keywords}. STRICT RULES: do not add any employer, title, date, technology, "
        "or number that is not already in the original text. Only reshape emphasis and wording. "
        "Keep each bullet one line. Return strict JSON: a list of {\"id\":\"\",\"text\":\"\"}.\n\n"
        f"Bullets:\n{json.dumps(payload)}"
    )
    out = complete(prompt, max_tokens=900, temperature=0.3)
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
