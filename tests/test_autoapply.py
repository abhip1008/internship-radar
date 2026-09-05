"""Auto-prepare gating tests (the user's rule: tailor clean matches, hold gaps)."""
import tempfile

from radar import autoapply, dedupe
from radar.db import DB
from radar.models import Posting


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


def test_clean_match_is_tailored_and_ready():
    db = _db()
    _seed(db, "acme", "Build services with Python, PostgreSQL, JavaScript.")
    r = autoapply.prepare_one(db, db.open_postings()[0], use_llm=False)
    assert r["state"] == "ready" and r["gaps"] == []
    db.close()


def test_gapped_posting_is_held():
    db = _db()
    _seed(db, "globex", "Build distributed systems in Go on Kubernetes with Docker.")
    r = autoapply.prepare_one(db, db.open_postings()[0], use_llm=False)
    assert r["state"] == "needs_improvement"
    assert "go" in r["gaps"] and "kubernetes" in r["gaps"]
    # No resume should have been generated for a held posting.
    app = db.get_application(r["id"])
    assert not app.get("resume_tex_path")
    db.close()


def test_scope_seattle_min_fit_excludes_low_fit_and_non_seattle():
    db = _db()
    _seed(db, "hi", "Python.", fit=80, seattle=True)
    _seed(db, "lowfit", "Python.", fit=40, seattle=True)
    _seed(db, "remote", "Python.", fit=90, seattle=False)
    cands = autoapply.select_candidates(db, scope="seattle", min_fit=60)
    slugs = {c["company_slug"] for c in cands}
    assert "hi" in slugs and "lowfit" not in slugs and "remote" not in slugs
    db.close()


def test_reviewing_scope_only_takes_reviewing():
    db = _db()
    _seed(db, "new1", "Python.", status="new")
    _seed(db, "rev1", "Python.", status="reviewing")
    cands = autoapply.select_candidates(db, scope="reviewing", min_fit=0)
    slugs = {c["company_slug"] for c in cands}
    assert slugs == {"rev1"}
    db.close()
