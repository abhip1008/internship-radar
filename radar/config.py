"""Configuration loader.

Reads config.yaml and resolves `env:NAME` references against the environment so
secrets never live in the repo.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _resolve_env(value: Any) -> Any:
    """Recursively replace `env:NAME` strings with os.environ["NAME"] (or None)."""
    if isinstance(value, str) and value.startswith("env:"):
        return os.environ.get(value[4:])
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    return value


@lru_cache(maxsize=1)
def load_config(path: str | None = None) -> dict[str, Any]:
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    with open(cfg_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return _resolve_env(raw)


def data_path(*parts: str) -> Path:
    return ROOT.joinpath("data", *parts)


def registry_path(*parts: str) -> Path:
    return ROOT.joinpath("registry", *parts)


def files_path(*parts: str) -> Path:
    return ROOT.joinpath("files", *parts)
