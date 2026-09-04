"""ATS platform collectors. See spec §5.1 for endpoint patterns.

Dispatch table maps a company's `ats` field to its collect() coroutine.
"""
from __future__ import annotations

from . import ashby, greenhouse, lever, recruitee, smartrecruiters, workable, workday

REGISTRY = {
    "greenhouse": greenhouse.collect,
    "lever": lever.collect,
    "ashby": ashby.collect,
    "smartrecruiters": smartrecruiters.collect,
    "workable": workable.collect,
    "recruitee": recruitee.collect,
    "workday": workday.collect,
}


def get_collector(ats: str):
    return REGISTRY.get(ats)
