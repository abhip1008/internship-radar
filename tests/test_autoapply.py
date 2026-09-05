"""Auto-prepare gating tests.

New model: nothing is auto-marked "Ready" (that means you approved it). The gate
holds postings missing must-have skills, tailors strong matches for your review,
and flags thin-JD postings it can't honestly assess.
"""
import tempfile

from radar import assess as assess_mod
from radar import autoapply, dedupe
from radar.db import DB
from radar.models import Posting

# A JD long enough to clear the MIN_JD_CHARS assessability bar.
LONG_MATCH = (
    "We are hiring a software engineering intern to build backend services. "
    "You will write Python and JavaScript, design PostgreSQL schemas, build REST APIs, "
    "and work with Git in an Agile team. Strong fundamentals in data structures and "
    "object-oriented programming are expected. You will collaborate with senior engineers, "
    "review code, and ship backend and frontend features end to end over the summer."
)
LONG_GAP = (
    "We are hiring an infrastructure engineering intern. You will build distributed systems "
    "in Go and Rust, deploy services on Kubernetes with Docker, and manage cloud infrastructure "
    "on AWS using Terraform. Experience with Kafka and gRPC is expected. You will own reliability "
    "and on-call for critical services and write production-grade systems code every day."
)


def _seed(db, slug, desc, fit=80, status="new", seattle=True):
    p = Posting(id="", company_slug=slug, company_name=slug.title(), title="SWE Intern",
                apply_url=f"http://x/{slug}", is_seattle_metro=seattle, term="summer-2027",
                fit_score=fit, description=desc)
    p.id = dedupe.compute_id(p)
    db.upsert_posting(p)
    if status != "new":
        db.set_status(p.id, status)
    return p.id


def _db():
    return DB(tempfile.mktemp(suffix=".db"))


def test_strong_match_is_tailored_awaiting_approval():
    db = _db()
    _seed(db, "acme", LONG_MATCH)
    r = autoapply.prepare_one(db, db.open_postings()[0], use_llm=False)
    assert r["state"] == "tailored"
    # Tailored, but NOT approved -> not Ready yet.
    app = db.get_application(r["id"])
    assert app.get("resume_tex_path") and not app.get("resume_approved")
    db.close()


def test_missing_must_have_is_held():
    db = _db()
    _seed(db, "globex", LONG_GAP)
    r = autoapply.prepare_one(db, db.open_postings()[0], use_llm=False)
    assert r["state"] == "needs_improvement"
    assert "go" in r["gaps"] and "kubernetes" in r["gaps"]
    app = db.get_application(r["id"])
    assert not app.get("resume_tex_path")  # held postings are not tailored
    db.close()


def test_thin_jd_is_flagged_not_confidently_ready():
    db = _db()
    _seed(db, "listco", "Software Engineer Intern")  # no real JD text
    r = autoapply.prepare_one(db, db.open_postings()[0], use_llm=False)
    assert r["state"] == "thin_jd"
    db.close()


def test_assess_states():
    strong = Posting(id="", company_slug="a", company_name="A", title="SWE Intern",
                     apply_url="http://a", description=LONG_MATCH)
    gap = Posting(id="", company_slug="b", company_name="B", title="SWE Intern",
                  apply_url="http://b", description=LONG_GAP)
    thin = Posting(id="", company_slug="c", company_name="C", title="SWE Intern",
                   apply_url="http://c", description="short")
    assert assess_mod.assess(strong).state == "strong"
    assert assess_mod.assess(gap).state == "needs_improvement"
    assert assess_mod.assess(thin).state == "thin_jd"


def test_scope_seattle_min_fit_excludes_low_fit_and_non_seattle():
    db = _db()
    _seed(db, "hi", LONG_MATCH, fit=80, seattle=True)
    _seed(db, "lowfit", LONG_MATCH, fit=40, seattle=True)
    _seed(db, "remote", LONG_MATCH, fit=90, seattle=False)
    cands = autoapply.select_candidates(db, scope="seattle", min_fit=60)
    slugs = {c["company_slug"] for c in cands}
    assert "hi" in slugs and "lowfit" not in slugs and "remote" not in slugs
    db.close()


def test_reviewing_scope_only_takes_reviewing():
    db = _db()
    _seed(db, "new1", LONG_MATCH, status="new")
    _seed(db, "rev1", LONG_MATCH, status="reviewing")
    cands = autoapply.select_candidates(db, scope="reviewing", min_fit=0)
    slugs = {c["company_slug"] for c in cands}
    assert slugs == {"rev1"}
    db.close()
