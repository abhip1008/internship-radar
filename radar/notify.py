"""Notification pipeline (spec §8).

Discord webhook first (works on phone, free, instant), ntfy.sh second. Batches
into one message when 5+ postings arrive together. The alert rule: instant ping
only for `is_seattle_metro AND fit >= threshold`, or any watchlist company —
everything else waits for the digest. Getting pinged 40x/day means you stop
reading the pings.
"""
from __future__ import annotations

from typing import Any

import httpx

from .config import load_config
from .models import Posting


def should_alert(posting: Posting, company: dict[str, Any] | None, threshold: int) -> bool:
    if company and company.get("watchlist"):
        return True
    return posting.is_seattle_metro and posting.fit_score >= threshold


def _discord_embed(p: Posting) -> dict[str, Any]:
    loc = ", ".join(p.locations) or "Location TBD"
    return {
        "title": f"{p.company_name} — {p.title}"[:250],
        "url": p.apply_url,
        "description": f"📍 {loc} · Fit {p.fit_score} · {p.term}",
        "color": 0x1B4DD1,
    }


def send(postings: list[Posting], companies: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Send alerts for the given (already-filtered) postings. Returns a summary."""
    cfg = load_config()
    threshold = cfg["scoring"]["alert_threshold"]
    companies = companies or {}

    alertable = [p for p in postings if should_alert(p, companies.get(p.company_slug), threshold)]
    if not alertable:
        return {"sent": 0, "channel": None}

    webhook = cfg["notify"].get("discord_webhook")
    ntfy_topic = cfg["notify"].get("ntfy_topic")
    channel = None

    if webhook:
        # Batch into one message when 5+ arrive together (spec §8).
        embeds = [_discord_embed(p) for p in alertable[:10]]
        content = f"**{len(alertable)} new Seattle-area posting(s)**" if len(alertable) > 1 else None
        try:
            httpx.post(webhook, json={"content": content, "embeds": embeds}, timeout=15).raise_for_status()
            channel = "discord"
        except httpx.HTTPError:
            pass

    if channel is None and ntfy_topic:
        try:
            lines = [f"{p.company_name} — {p.title} ({p.fit_score})" for p in alertable[:10]]
            httpx.post(
                f"https://ntfy.sh/{ntfy_topic}",
                data="\n".join(lines).encode("utf-8"),
                headers={"Title": f"{len(alertable)} new internship(s)", "Tags": "briefcase"},
                timeout=15,
            ).raise_for_status()
            channel = "ntfy"
        except httpx.HTTPError:
            pass

    return {"sent": len(alertable) if channel else 0, "channel": channel}
