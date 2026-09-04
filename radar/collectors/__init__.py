"""Collectors: one module per source type (spec §3, §4).

Each ATS collector exposes `async def collect(client, company) -> list[RawPosting]`.
The custom, list, and feed collectors follow the same signature where it makes
sense so `run.py` can treat them uniformly.
"""
