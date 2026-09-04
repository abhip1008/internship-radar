"""Hallucination diff check (spec §10.2 verify(), guardrails §10).

A rewritten bullet passes only if every proper noun and numeral in it already
appears in the original bullet (or the wider bank). Any unmatched token fails the
rewrite and the caller falls back to the verbatim bullet.
"""
from __future__ import annotations

import re

from .bank import flat_terms

STOPWORDS = {
    "A", "An", "The", "I", "Built", "Designed", "Led", "Lead", "Managed", "Wrote",
    "Run", "Ran", "Raised", "Mentored", "Implemented", "Added", "Integrated",
    "Enforced", "Co-founded", "Co-Founded",
}


def _proper_nouns(text: str) -> set[str]:
    """Capitalized tokens that look like names/techs — skipping sentence-initial
    words (a leading verb like "Drove" is not a proper noun)."""
    out: set[str] = set()
    for m in re.finditer(r"[A-Z][A-Za-z0-9.+#/-]{1,}", text):
        token = m.group(0)
        if token in STOPWORDS:
            continue
        # Skip if this is the first word or directly follows sentence punctuation.
        prefix = text[: m.start()].rstrip()
        if not prefix or prefix[-1] in ".!?;:":
            continue
        out.add(token)
    return out


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\b\d[\d,]*\+?\b", text))


def verify_bullet(original: str, rewritten: str) -> bool:
    """True if the rewrite introduces no new proper noun or numeral."""
    bank = flat_terms()
    orig_nouns = {n.lower() for n in _proper_nouns(original)}
    orig_nums = _numbers(original)

    for noun in _proper_nouns(rewritten):
        low = noun.lower()
        if low in orig_nouns:
            continue
        # Allow words that exist anywhere in the bank (e.g. "Python" reused).
        if any(low == t or low in t for t in bank):
            continue
        return False

    for num in _numbers(rewritten):
        if num not in orig_nums:
            return False
    return True


def verify_document(rendered_text: str, base_text: str) -> list[str]:
    """Return a list of suspicious claims in the final doc not present in base.

    Used as a final safety net (guardrail #2 at the document level).
    """
    bank = flat_terms()
    base_nums = _numbers(base_text)
    issues = []
    for num in _numbers(rendered_text):
        if num not in base_nums:
            issues.append(f"numeral not in base: {num}")
    for noun in _proper_nouns(rendered_text):
        low = noun.lower()
        if low in {b.lower() for b in _proper_nouns(base_text)}:
            continue
        if any(low == t or low in t for t in bank):
            continue
        issues.append(f"proper noun not in bank: {noun}")
    return issues
