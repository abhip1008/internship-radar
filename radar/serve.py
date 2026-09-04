"""Local read/write API over the SQLite DB (spec §14 Python-only path).

Stdlib http.server — zero extra dependencies. Serves the UI's data needs and
handles the one column you edit by hand (status), on-demand resume generation,
notes generation, the gaps rollup, and manual URL add.

Endpoints:
  GET  /api/snapshot?seattle=1
  GET  /api/postings/{id}
  POST /api/postings/{id}/status      {status}
  POST /api/postings/{id}/generate    -> tailor + notes
  POST /api/postings/{id}/approve     {approved}
  POST /api/postings/{id}/user_notes  {text}
  GET  /api/gaps
  POST /api/add                       {url, company, title}
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import notes as notes_mod
from .db import DB
from .models import Posting
from .view import posting_row, snapshot

VALID_STATUS = {"new", "reviewing", "applied", "oa", "interview", "offer", "rejected", "skipped"}


def _posting_from_row(row: dict) -> Posting:
    return Posting(
        id=row["id"], company_slug=row["company_slug"], company_name=row["company_name"],
        title=row["title"], apply_url=row["apply_url"],
        locations=json.loads(row.get("locations") or "[]"),
        is_seattle_metro=bool(row.get("is_seattle_metro")),
        term=row.get("term", "unspecified"), description=row.get("description", ""),
        eligibility_flags=json.loads(row.get("eligibility_flags") or "[]"),
        fit_score=row.get("fit_score", 0),
    )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quieter console
        pass

    def _send(self, code: int, payload):
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return {}

    def do_OPTIONS(self):
        self._send(204, {})

    def do_GET(self):
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        db = DB()
        try:
            if parts == ["api", "snapshot"]:
                seattle = parse_qs(parsed.query).get("seattle", ["0"])[0] == "1"
                self._send(200, snapshot(db, seattle_only=seattle))
            elif len(parts) == 3 and parts[:2] == ["api", "postings"]:
                row = db.get_posting(parts[2])
                if not row:
                    self._send(404, {"error": "not found"})
                else:
                    self._send(200, posting_row(db, row, detail=True))
            elif parts == ["api", "gaps"]:
                gaps = [g for g in db.keyword_rollup() if not g["covered"]]
                self._send(200, {"gaps": gaps})
            else:
                self._send(404, {"error": "unknown route"})
        finally:
            db.close()

    def do_POST(self):
        parts = [p for p in urlparse(self.path).path.split("/") if p]
        db = DB()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "postings"]:
                pid, action = parts[2], parts[3]
                row = db.get_posting(pid)
                if not row:
                    self._send(404, {"error": "not found"}); return
                body = self._body()
                if action == "status":
                    status = body.get("status")
                    if status not in VALID_STATUS:
                        self._send(400, {"error": "invalid status"}); return
                    db.set_status(pid, status)
                    self._send(200, {"ok": True, "status": status})
                elif action == "approve":
                    db.conn.execute("UPDATE applications SET resume_approved=? WHERE posting_id=?",
                                    (1 if body.get("approved", True) else 0, pid))
                    db.conn.commit()
                    self._send(200, {"ok": True})
                elif action == "user_notes":
                    db.conn.execute("UPDATE applications SET user_notes=? WHERE posting_id=?",
                                    (body.get("text", ""), pid))
                    db.conn.commit()
                    self._send(200, {"ok": True})
                elif action == "generate":
                    self._generate(db, pid, row)
                else:
                    self._send(404, {"error": "unknown action"})
            elif parts == ["api", "add"]:
                self._add_manual(db, self._body())
            else:
                self._send(404, {"error": "unknown route"})
        finally:
            db.close()

    def _generate(self, db: DB, pid: str, row: dict):
        from .tailor import tailor
        posting = _posting_from_row(row)
        use_llm = True
        try:
            tailored = tailor(posting, use_llm=use_llm)
            db.set_resume(pid, tailored["tex_path"], tailored["pdf_path"])
        except Exception as exc:
            self._send(500, {"error": f"tailor failed: {exc}"}); return
        note = notes_mod.generate(posting, use_llm=use_llm)
        db.set_notes(pid, note)
        for kw in note["keyword_coverage"]["present"]:
            db.bump_keyword(kw, covered=True)
        for kw in note["keyword_coverage"]["missing"]:
            db.bump_keyword(kw, covered=False)
        self._send(200, {"ok": True, "resume_pdf": tailored["pdf_path"],
                         "resume_tex": tailored["tex_path"], "notes": note})

    def _add_manual(self, db: DB, body: dict):
        """+ Add manually (spec §4 Tier 4): accept a URL, run the pipeline on it."""
        from .models import RawPosting
        from . import normalize, filters, score, deadlines, dedupe
        url = body.get("url")
        if not url:
            self._send(400, {"error": "url required"}); return
        raw = RawPosting(
            company_slug=(body.get("company", "manual") or "manual").lower().replace(" ", "-"),
            company_name=body.get("company", "Manual add"),
            title=body.get("title", "Internship"),
            apply_url=url, description=body.get("description", ""),
            location_text=body.get("location", ""), source_type="manual", source_url=url,
        )
        p = normalize.normalize(raw)
        verdict = filters.evaluate(p, None)
        p.eligibility_flags = verdict.eligibility_flags
        p.fit_score, p.fit_breakdown = score.score(p, None)
        dl = deadlines.resolve(p)
        p.closes_at, p.closes_kind, p.closes_evidence = dl["closes_at"], dl["closes_kind"], dl["closes_evidence"]
        p.id = dedupe.compute_id(p)
        db.upsert_posting(p)
        self._send(200, {"ok": True, "id": p.id, "passed_filter": verdict.passed})


def serve(port: int = 8787) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Internship Radar API on http://127.0.0.1:{port}  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
