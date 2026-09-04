"""Resume tailoring engine (spec §10).

Pipeline: JD -> extract_requirements -> score_bullets -> select -> reorder ->
rephrase (LLM, guarded) -> verify (hallucination diff) -> render (jinja -> tex
-> pdf). The human presses submit; the system only produces the file.
"""
from .bank import load_bank
from .pipeline import tailor

__all__ = ["load_bank", "tailor"]
