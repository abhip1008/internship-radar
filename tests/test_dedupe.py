"""Dedupe/merge tests (spec §7)."""
from radar import dedupe
from radar.models import Posting


def _p(slug, title, url, ats_id=None, src="greenhouse", **kw):
    return Posting(id="", company_slug=slug, company_name=slug.title(), title=title,
                   apply_url=url, ats_job_id=ats_id, sources=[{"type": src, "url": url}], **kw)


def test_exact_url_dedupe_ignores_query():
    a = _p("remitly", "SWE Intern", "https://x.com/jobs/1?src=a")
    b = _p("remitly", "SWE Intern", "https://x.com/jobs/1?utm=b", src="github-list")
    out = dedupe.dedupe_batch([a, b])
    assert len(out) == 1
    assert {s["type"] for s in out[0].sources} == {"greenhouse", "github-list"}


def test_strong_key_merge():
    a = _p("remitly", "Software Engineer Intern", "https://a.com/1", ats_id="J1")
    b = _p("remitly", "Software Engineer Intern", "https://b.com/2", ats_id="J1", src="rss")
    out = dedupe.dedupe_batch([a, b])
    assert len(out) == 1


def test_fuzzy_title_merge():
    a = _p("acme", "Software Engineer Intern - Summer 2027", "https://a.com/1",
           is_seattle_metro=True, term="summer-2027")
    b = _p("acme", "Software Engineer Intern (2027)", "https://b.com/2",
           is_seattle_metro=True, term="summer-2027")
    out = dedupe.dedupe_batch([a, b])
    assert len(out) == 1


def test_distinct_roles_not_merged():
    a = _p("acme", "Backend Engineer Intern", "https://a.com/1")
    b = _p("acme", "Frontend Engineer Intern", "https://a.com/2")
    out = dedupe.dedupe_batch([a, b])
    assert len(out) == 2


def test_normalize_title_strips_noise():
    assert dedupe.normalize_title("Senior SWE Intern II - Req #12345 (2027)") == "swe intern"
