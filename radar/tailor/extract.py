"""JD -> requirements (spec §10.2, extract_requirements()).

Deterministic keyword/domain extraction. No LLM needed for this step — it drives
bullet selection and the keyword-coverage report.
"""
from __future__ import annotations

import re
from typing import Any

from ..score import extract_jd_stack

DOMAIN_SIGNALS = {
    "ai-systems": ["machine learning", "ml", " ai ", "llm", "model", "nlp", "deep learning"],
    "backend": ["backend", "back-end", "api", "microservice", "distributed", "server", "database"],
    "fullstack-product": ["full stack", "full-stack", "end-to-end", "product", "feature"],
    "frontend": ["frontend", "front-end", "react", "ui", "user interface", "css"],
}

MUST_HAVE_CUES = ["required", "must have", "you have", "minimum qualifications", "basic qualifications"]
NICE_CUES = ["preferred", "nice to have", "bonus", "plus", "a plus"]


def _split_sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.!?])\s+|\n+", text)


def extract_requirements(jd_text: str) -> dict[str, Any]:
    text = jd_text or ""
    lower = text.lower()

    jd_stack = extract_jd_stack(text)

    # Split stack into must/nice by which section-cue sentence they appear near.
    must_have, nice_to_have = set(), set()
    for sent in _split_sentences(lower):
        techs = extract_jd_stack(sent)
        if not techs:
            continue
        if any(c in sent for c in NICE_CUES):
            nice_to_have |= techs
        elif any(c in sent for c in MUST_HAVE_CUES):
            must_have |= techs
    # Anything not classified defaults to must_have (be strict about coverage).
    must_have |= (jd_stack - nice_to_have)

    # Domain: whichever signal group scores highest.
    scores = {d: sum(lower.count(s) for s in sigs) for d, sigs in DOMAIN_SIGNALS.items()}
    domain = max(scores, key=scores.get) if any(scores.values()) else "fullstack-product"

    seniority = "intern"
    if re.search(r"rising senior|junior standing|3rd year|third year", lower):
        seniority = "rising-senior"

    return {
        "must_have": sorted(must_have),
        "nice_to_have": sorted(nice_to_have),
        "keywords": sorted(jd_stack),
        "domain": domain,
        "seniority": seniority,
    }
