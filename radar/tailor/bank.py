"""Experience bank loader + validation (spec §10.1).

The bank is the source of truth. Bullets are selected and re-angled, never
invented. This module loads and lightly validates the YAML and exposes a flat
view of every bullet for selection/verification.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import yaml

from ..config import data_path


@dataclass
class Bullet:
    id: str
    text: str
    tags: list[str] = field(default_factory=list)
    source_id: str = ""       # parent experience/project id
    source_name: str = ""
    kind: str = ""            # leadership | ai-systems | backend | ...
    stack: list[str] = field(default_factory=list)


@lru_cache(maxsize=1)
def load_bank() -> dict[str, Any]:
    with open(data_path("experience.yaml"), "r", encoding="utf-8") as fh:
        bank = yaml.safe_load(fh)
    if "identity" not in bank:
        raise ValueError("experience.yaml missing `identity`")
    return bank


def all_bullets() -> list[Bullet]:
    bank = load_bank()
    out: list[Bullet] = []
    for section in ("experiences", "projects"):
        for item in bank.get(section, []):
            stack = [s.lower() for s in item.get("stack", [])]
            name = item.get("org") or item.get("name", "")
            for b in item.get("bullets", []):
                out.append(
                    Bullet(
                        id=b["id"],
                        text=b["text"],
                        tags=[t.lower() for t in b.get("tags", [])],
                        source_id=item.get("id", ""),
                        source_name=name,
                        kind=item.get("kind", ""),
                        stack=stack,
                    )
                )
    return out


def flat_terms() -> set[str]:
    """Every proper noun / tech the bank legitimately contains, for verify()."""
    bank = load_bank()
    terms: set[str] = set()
    for section in ("experiences", "projects"):
        for item in bank.get(section, []):
            for key in ("org", "name", "role", "award"):
                if item.get(key):
                    terms.update(str(item[key]).lower().split())
            for s in item.get("stack", []):
                terms.update(str(s).lower().split())
    for group in bank.get("skills", {}).values():
        for s in group:
            terms.update(str(s).lower().split())
    edu = bank["identity"].get("education", {})
    for v in edu.values():
        if isinstance(v, str):
            terms.update(v.lower().split())
    return terms
