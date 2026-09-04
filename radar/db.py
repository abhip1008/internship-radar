"""SQLite persistence layer.

One file, zero ops (spec §12). Handles the companies/postings/applications/
keyword_stats tables plus the merge-on-collision write path (spec §7).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .config import data_path
from .models import Posting

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
  slug TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  ats TEXT,
  board_token TEXT,
  workday_tenant TEXT, workday_wd INT, workday_site TEXT,
  hq TEXT, tier INT DEFAULT 2, watchlist INTEGER DEFAULT 0,
  poll_minutes INT DEFAULT 60,
  last_polled_at TEXT, consecutive_failures INT DEFAULT 0,
  tags TEXT
);

CREATE TABLE IF NOT EXISTS postings (
  id TEXT PRIMARY KEY,
  company_slug TEXT REFERENCES companies(slug),
  company_name TEXT,
  title TEXT NOT NULL,
  apply_url TEXT NOT NULL,
  ats_job_id TEXT,
  locations TEXT,
  is_seattle_metro INTEGER,
  is_remote_us INTEGER,
  is_wa INTEGER,
  term TEXT,
  description TEXT,
  posted_at TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  closes_at TEXT, closes_kind TEXT, closes_evidence TEXT,
  is_closed INTEGER DEFAULT 0,
  fit_score INT, fit_breakdown TEXT,
  eligibility_flags TEXT,
  sources TEXT,
  raw TEXT
);

CREATE TABLE IF NOT EXISTS applications (
  posting_id TEXT PRIMARY KEY REFERENCES postings(id),
  status TEXT DEFAULT 'new',
  applied_at TEXT,
  resume_tex_path TEXT, resume_pdf_path TEXT, resume_generated_at TEXT,
  resume_approved INTEGER DEFAULT 0,
  cover_letter_path TEXT,
  notes_json TEXT,
  user_notes TEXT,
  referral TEXT,
  next_action TEXT, next_action_due TEXT
);

CREATE TABLE IF NOT EXISTS keyword_stats (
  keyword TEXT PRIMARY KEY,
  seen_count INT, covered INTEGER, last_seen TEXT
);

CREATE INDEX IF NOT EXISTS idx_postings_seattle_new ON postings(is_seattle_metro, first_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_postings_open ON postings(is_closed, fit_score DESC);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dumps(value: Any) -> str:
    return json.dumps(value, default=str)


class DB:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else data_path("radar.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ----- companies -----------------------------------------------------
    def upsert_company(self, c: dict[str, Any]) -> None:
        wd = c.get("workday") or {}
        self.conn.execute(
            """INSERT INTO companies
               (slug, name, ats, board_token, workday_tenant, workday_wd, workday_site,
                hq, tier, watchlist, poll_minutes, tags)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(slug) DO UPDATE SET
                 name=excluded.name, ats=excluded.ats, board_token=excluded.board_token,
                 workday_tenant=excluded.workday_tenant, workday_wd=excluded.workday_wd,
                 workday_site=excluded.workday_site, hq=excluded.hq, tier=excluded.tier,
                 watchlist=excluded.watchlist, poll_minutes=excluded.poll_minutes,
                 tags=excluded.tags""",
            (
                c["slug"], c["name"], c.get("ats"), c.get("board_token"),
                wd.get("tenant"), wd.get("wd"), wd.get("site"),
                c.get("hq"), c.get("tier", 2), 1 if c.get("watchlist") else 0,
                c.get("poll_minutes", 60), _dumps(c.get("tags", [])),
            ),
        )
        self.conn.commit()

    def get_companies(self, tier: Optional[int] = None) -> list[dict[str, Any]]:
        if tier is None:
            rows = self.conn.execute("SELECT * FROM companies").fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM companies WHERE tier=?", (tier,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["tags"] = json.loads(d.get("tags") or "[]")
            d["watchlist"] = bool(d.get("watchlist"))
            if d.get("workday_tenant"):
                d["workday"] = {"tenant": d["workday_tenant"], "wd": d["workday_wd"], "site": d["workday_site"]}
            out.append(d)
        return out

    def mark_polled(self, slug: str, ok: bool) -> None:
        if ok:
            self.conn.execute(
                "UPDATE companies SET last_polled_at=?, consecutive_failures=0 WHERE slug=?",
                (now_iso(), slug),
            )
        else:
            self.conn.execute(
                "UPDATE companies SET last_polled_at=?, consecutive_failures=consecutive_failures+1 WHERE slug=?",
                (now_iso(), slug),
            )
        self.conn.commit()

    # ----- postings ------------------------------------------------------
    def get_posting(self, pid: str) -> Optional[dict[str, Any]]:
        row = self.conn.execute("SELECT * FROM postings WHERE id=?", (pid,)).fetchone()
        return dict(row) if row else None

    def upsert_posting(self, p: Posting) -> str:
        """Insert a new posting or merge into an existing one (spec §7).

        Returns "new" or "merged" so callers know whether to alert.
        """
        existing = self.get_posting(p.id)
        ts = now_iso()
        if existing is None:
            first_seen = p.first_seen_at.isoformat() if p.first_seen_at else ts
            self.conn.execute(
                """INSERT INTO postings
                   (id, company_slug, company_name, title, apply_url, ats_job_id, locations,
                    is_seattle_metro, is_remote_us, is_wa, term, description, posted_at,
                    first_seen_at, last_seen_at, closes_at, closes_kind, closes_evidence,
                    is_closed, fit_score, fit_breakdown, eligibility_flags, sources, raw)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    p.id, p.company_slug, p.company_name, p.title, p.apply_url, p.ats_job_id,
                    _dumps(p.locations), int(p.is_seattle_metro), int(p.is_remote_us), int(p.is_wa),
                    p.term, p.description, p.posted_at.isoformat() if p.posted_at else None,
                    first_seen, ts, p.closes_at, p.closes_kind, p.closes_evidence,
                    int(p.is_closed), p.fit_score, _dumps(p.fit_breakdown),
                    _dumps(p.eligibility_flags), _dumps(p.sources), _dumps(p.raw),
                ),
            )
            # Every new posting gets an application row in the 'new' state.
            self.conn.execute(
                "INSERT OR IGNORE INTO applications (posting_id, status) VALUES (?, 'new')",
                (p.id,),
            )
            self.conn.commit()
            return "new"

        # Merge: keep earliest first_seen, union locations + sources, refresh last_seen.
        old_locs = json.loads(existing.get("locations") or "[]")
        merged_locs = sorted(set(old_locs) | set(p.locations))
        old_sources = json.loads(existing.get("sources") or "[]")
        keys = {(s.get("type"), s.get("url")) for s in old_sources}
        merged_sources = old_sources + [s for s in p.sources if (s.get("type"), s.get("url")) not in keys]
        # Prefer the longer description (spec §7).
        desc = existing.get("description") or ""
        if len(p.description) > len(desc):
            desc = p.description
        self.conn.execute(
            """UPDATE postings SET last_seen_at=?, is_closed=0, locations=?, sources=?,
               description=?, fit_score=?, fit_breakdown=?, is_seattle_metro=?,
               is_remote_us=?, is_wa=?, term=?, closes_at=?, closes_kind=?, closes_evidence=?,
               eligibility_flags=? WHERE id=?""",
            (
                ts, _dumps(merged_locs), _dumps(merged_sources), desc,
                p.fit_score, _dumps(p.fit_breakdown), int(p.is_seattle_metro),
                int(p.is_remote_us), int(p.is_wa), p.term, p.closes_at, p.closes_kind,
                p.closes_evidence, _dumps(p.eligibility_flags), p.id,
            ),
        )
        self.conn.commit()
        return "merged"

    def all_posting_ids_for_company(self, slug: str) -> set[str]:
        rows = self.conn.execute(
            "SELECT id FROM postings WHERE company_slug=? AND is_closed=0", (slug,)
        ).fetchall()
        return {r["id"] for r in rows}

    def mark_closed(self, pid: str) -> None:
        self.conn.execute("UPDATE postings SET is_closed=1 WHERE id=?", (pid,))
        self.conn.commit()

    def open_postings(self, seattle_only: bool = False) -> list[dict[str, Any]]:
        q = "SELECT * FROM postings WHERE is_closed=0"
        if seattle_only:
            q += " AND is_seattle_metro=1"
        q += " ORDER BY is_seattle_metro DESC, fit_score DESC, first_seen_at DESC"
        return [dict(r) for r in self.conn.execute(q).fetchall()]

    def company_lifetimes(self, slug: str) -> list[float]:
        """Observed posting lifetimes (days) for closed postings — feeds §9 estimates."""
        rows = self.conn.execute(
            "SELECT first_seen_at, last_seen_at FROM postings WHERE company_slug=? AND is_closed=1",
            (slug,),
        ).fetchall()
        out = []
        for r in rows:
            try:
                d = (datetime.fromisoformat(r["last_seen_at"]) - datetime.fromisoformat(r["first_seen_at"])).days
                if d >= 0:
                    out.append(float(d))
            except (ValueError, TypeError):
                continue
        return out

    # ----- applications --------------------------------------------------
    def set_status(self, pid: str, status: str) -> None:
        applied_at = now_iso() if status == "applied" else None
        self.conn.execute(
            "UPDATE applications SET status=?, applied_at=COALESCE(?, applied_at) WHERE posting_id=?",
            (status, applied_at, pid),
        )
        self.conn.commit()

    def set_resume(self, pid: str, tex: str, pdf: Optional[str]) -> None:
        self.conn.execute(
            """UPDATE applications SET resume_tex_path=?, resume_pdf_path=?, resume_generated_at=?
               WHERE posting_id=?""",
            (tex, pdf, now_iso(), pid),
        )
        self.conn.commit()

    def set_notes(self, pid: str, notes: dict[str, Any]) -> None:
        self.conn.execute(
            "UPDATE applications SET notes_json=? WHERE posting_id=?", (_dumps(notes), pid)
        )
        self.conn.commit()

    def get_application(self, pid: str) -> Optional[dict[str, Any]]:
        row = self.conn.execute("SELECT * FROM applications WHERE posting_id=?", (pid,)).fetchone()
        return dict(row) if row else None

    # ----- keyword stats -------------------------------------------------
    def bump_keyword(self, keyword: str, covered: bool) -> None:
        self.conn.execute(
            """INSERT INTO keyword_stats (keyword, seen_count, covered, last_seen)
               VALUES (?, 1, ?, ?)
               ON CONFLICT(keyword) DO UPDATE SET
                 seen_count=seen_count+1, covered=?, last_seen=?""",
            (keyword, int(covered), now_iso(), int(covered), now_iso()),
        )
        self.conn.commit()

    def keyword_rollup(self, limit: int = 40) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM keyword_stats ORDER BY seen_count DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
