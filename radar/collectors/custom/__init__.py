"""Custom career-site collectors for the largest employers (spec §4 Tier 2).

Each large employer runs its own system but exposes one JSON endpoint. Modules
here expose `async def collect(client, company) -> list[RawPosting]` and are
referenced from the registry via `collector: custom.<name>`.
"""
from __future__ import annotations

from . import amazon, microsoft

REGISTRY = {
    "custom.amazon": amazon.collect,
    "custom.microsoft": microsoft.collect,
}


def get_collector(name: str):
    return REGISTRY.get(name)
