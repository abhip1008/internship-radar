"""Registry loading + growth (spec §5.3).

Loads the YAML registries into the DB and provides the auto-grow path: new
company names discovered in community lists get queued for ATS detection and,
on success, written to national.yaml; failures go to unresolved.yaml.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .config import registry_path
from .db import DB

REGISTRY_FILES = ["seattle.yaml", "national.yaml"]


def load_files() -> list[dict[str, Any]]:
    companies: list[dict[str, Any]] = []
    for fname in REGISTRY_FILES:
        path = registry_path(fname)
        if not path.exists():
            continue
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or []
        if isinstance(data, list):
            companies.extend(data)
    return companies


def sync_to_db(db: DB) -> int:
    companies = load_files()
    for c in companies:
        db.upsert_company(c)
    return len(companies)


def append_company(fname: str, company: dict[str, Any]) -> None:
    path = registry_path(fname)
    existing = []
    if path.exists():
        with open(path, "r", encoding="utf-8") as fh:
            existing = yaml.safe_load(fh) or []
    if any(c.get("slug") == company.get("slug") for c in existing):
        return
    existing.append(company)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(existing, fh, sort_keys=False, allow_unicode=True)
