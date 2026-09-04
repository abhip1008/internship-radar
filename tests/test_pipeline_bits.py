"""Normalize, score, deadlines, and tailoring-guardrail tests."""
from datetime import datetime, timezone

from radar import deadlines, normalize, score
from radar.models import Posting, RawPosting
from radar.tailor.verify import verify_bullet


def _raw(**kw):
    base = dict(company_slug="x", company_name="X", title="SWE Intern",
                apply_url="http://x", source_type="greenhouse")
    base.update(kw)
    return RawPosting(**base)


def test_geo_seattle_metro():
    p = normalize.normalize(_raw(location_text="Bellevue, WA"))
    assert p.is_seattle_metro and p.is_wa


def test_geo_remote_us():
    p = normalize.normalize(_raw(location_text="Remote (US)"))
    assert p.is_remote_us


def test_term_classification():
    p = normalize.normalize(_raw(title="SWE Intern - Summer 2027"))
    assert p.term == "summer-2027"


def test_score_prefers_seattle_target_term():
    seattle = Posting(id="", company_slug="x", company_name="X", title="SWE Intern",
                      apply_url="http://x", is_seattle_metro=True, is_wa=True,
                      term="summer-2027", description="Python and PostgreSQL.")
    remote = Posting(id="", company_slug="y", company_name="Y", title="SWE Intern",
                     apply_url="http://y", is_remote_us=True, term="unspecified",
                     description="Python.")
    s1, _ = score.score(seattle, {"tier": 0, "watchlist": True})
    s2, _ = score.score(remote, {"tier": 2})
    assert s1 > s2
    assert s1 <= 100


def test_deadline_explicit_parsed():
    p = Posting(id="", company_slug="x", company_name="X", title="t", apply_url="http://x",
                description="Applications close March 3, 2027. Apply soon.",
                first_seen_at=datetime.now(timezone.utc))
    dl = deadlines.resolve(p)
    assert dl["closes_kind"] == "explicit" and dl["closes_at"] == "2027-03-03"


def test_deadline_rolling_for_big_tech():
    p = Posting(id="", company_slug="amazon", company_name="Amazon", title="t",
                apply_url="http://x", first_seen_at=datetime.now(timezone.utc))
    dl = deadlines.resolve(p)
    assert dl["closes_kind"] == "rolling"


def test_deadline_estimated_fallback():
    p = Posting(id="", company_slug="acme", company_name="Acme", title="t", apply_url="http://x",
                description="No deadline here.", first_seen_at=datetime.now(timezone.utc))
    dl = deadlines.resolve(p, global_fallback_days=21)
    assert dl["closes_kind"] == "estimated" and dl["closes_at"] is not None


def test_verify_rejects_hallucinated_metric():
    orig = "Raised and donated $20,000 through sponsorship outreach"
    good = "Drove $20,000 in sponsorship funding through outreach"
    bad = "Raised $50,000 through sponsorship outreach"
    assert verify_bullet(orig, good) is True
    assert verify_bullet(orig, bad) is False


def test_verify_rejects_new_technology():
    orig = "Built a Node.js backend streaming wearable data"
    bad = "Built a Rust and Kubernetes backend streaming wearable data"
    assert verify_bullet(orig, bad) is False
