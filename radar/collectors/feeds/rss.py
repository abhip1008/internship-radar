"""RSS/Atom feed collector (spec §4 Tier 4).

Ashby, Workable, Recruitee and many Greenhouse boards expose feeds. Free and
cheap to poll. Uses the stdlib XML parser so there is no extra dependency.
Feed URLs live in registry entries as `feed_url`, or pass a list of URLs.
"""
from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any
from xml.etree import ElementTree as ET

import httpx
from dateutil import parser as dtparser

from ...http import request
from ...models import RawPosting


def _strip_html(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _text(el: Any, *tags: str) -> str:
    for tag in tags:
        found = el.find(tag)
        if found is not None and found.text:
            return found.text.strip()
    return ""


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return dtparser.parse(value)
    except (ValueError, OverflowError):
        return None


async def collect_feed(client: httpx.AsyncClient, feed_url: str, company: dict[str, Any]) -> list[RawPosting]:
    resp = await request(client, "GET", feed_url)
    if resp is None or resp.status_code != 200:
        return []
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        return []
    out: list[RawPosting] = []
    # Support both RSS (<item>) and Atom (<entry>).
    items = root.iter("item")
    atom_ns = "{http://www.w3.org/2005/Atom}"
    entries = list(items) + list(root.iter(f"{atom_ns}entry"))
    for it in entries:
        title = _text(it, "title", f"{atom_ns}title")
        link = _text(it, "link", "guid")
        if not link:
            link_el = it.find(f"{atom_ns}link")
            if link_el is not None:
                link = link_el.get("href", "")
        desc = _text(it, "description", f"{atom_ns}summary", f"{atom_ns}content")
        pub = _text(it, "pubDate", f"{atom_ns}updated", f"{atom_ns}published")
        if not (title and link):
            continue
        out.append(
            RawPosting(
                company_slug=company["slug"],
                company_name=company["name"],
                title=title,
                apply_url=link,
                location_text="",  # feeds rarely tag location cleanly; normalize handles it
                description=_strip_html(desc),
                posted_at=_parse_dt(pub),
                source_type="rss",
                source_url=feed_url,
                raw={"title": title, "link": link},
            )
        )
    return out


async def collect(client: httpx.AsyncClient, company: dict[str, Any]) -> list[RawPosting]:
    feed_url = company.get("feed_url")
    if not feed_url:
        return []
    return await collect_feed(client, feed_url, company)
