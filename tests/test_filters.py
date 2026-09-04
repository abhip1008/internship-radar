"""Filter precision tests (spec §6). The word-boundary bugs that shipped once
(`intern` in `internal`, `it` in `audit`) are pinned here so they can't return."""
from radar import filters


def test_intern_not_matched_inside_internal():
    assert filters.is_early_career("Software Engineer Intern") is True
    assert filters.is_early_career("Vice President, Internal Audit") is False


def test_it_not_matched_inside_audit():
    assert filters.is_cs("Internal Audit Data Analytics Lead", "") is True  # 'data' is CS
    assert filters.is_cs("Financial Audit Associate", "") is False


def test_cs_titles():
    assert filters.is_cs("SDE Intern")
    assert filters.is_cs("ML Research Intern")
    assert filters.is_cs("Full Stack Engineer")
    assert not filters.is_cs("Warehouse Associate")


def test_cs_exclude_wins():
    from radar.models import Posting

    p = Posting(id="", company_slug="x", company_name="X", title="Marketing Intern",
                apply_url="http://x", term="unspecified")
    r = filters.evaluate(p, {"unspecified"})
    assert not r.passed and r.reason == "cs_exclude_title"


def test_eligibility_flags():
    flags = filters.eligibility_flags("PhD required. Must be a US citizen. No visa sponsorship.")
    assert "PhD required" in flags
    assert "US citizenship required" in flags
    assert "No visa sponsorship" in flags


def test_full_evaluate_keeps_real_posting():
    from radar.models import Posting

    p = Posting(id="", company_slug="remitly", company_name="Remitly",
                title="Software Engineer Intern - Summer 2027", apply_url="http://x",
                term="summer-2027", description="Build backend services.")
    r = filters.evaluate(p, {"summer-2027"})
    assert r.passed
