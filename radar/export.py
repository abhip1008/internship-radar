"""Static JSON snapshot for the UI (spec §14 — Vercel read-only path).

Writes web/public/data.json so the Next.js UI can render without a live backend.
Status edits in that mode are local-only; use `radar serve` for a writable API.
"""
from __future__ import annotations

import json
from pathlib import Path

from .db import DB
from .view import snapshot


def export_snapshot(path: Path) -> int:
    db = DB()
    data = snapshot(db)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    db.close()
    return len(data["postings"])
