"""CLI entry point — `python -m radar.run <command>`.

Commands:
  sweep   [--tier N] [--lists] [--no-notify]   run a collection sweep
  detect  "Company Name" [homepage]            probe a company's ATS
  grow                                         detect ATS for unresolved list companies
  tailor  <posting_id>                         generate a tailored resume
  notes   <posting_id>                         generate the notes blocks
  gaps                                          print the cross-posting gap rollup
  table                                         print the current open table
  export  [path]                               dump JSON snapshot for the UI
  serve   [--port 8787]                         run the local read/write API
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import detect as detect_mod
from . import notes as notes_mod
from . import registry
from .config import ROOT, load_config
from .db import DB
from .deadlines import days_remaining
from .models import Posting
from .pipeline import run_sweep


def _setup_logging() -> None:
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    rej = logging.getLogger("radar.rejections")
    handler = logging.FileHandler(logs / "rejections.log")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    rej.addHandler(handler)
    rej.propagate = False


# --------------------------------------------------------------------------- #
def cmd_sweep(args) -> None:
    db = DB()
    registry.sync_to_db(db)
    companies = db.get_companies(tier=args.tier)
    if not companies:
        print("No companies in registry. Add entries to registry/seattle.yaml.")
        return
    print(f"Sweeping {len(companies)} companies"
          + (f" (tier {args.tier})" if args.tier is not None else "")
          + (" + community lists" if args.lists else "") + " ...")
    summary = asyncio.run(run_sweep(companies, include_lists=args.lists, db=db, do_notify=not args.no_notify))
    print(json.dumps(summary, indent=2))
    db.close()


def cmd_detect(args) -> None:
    result = asyncio.run(detect_mod.detect(args.name, args.homepage))
    print(json.dumps(result, indent=2))


def cmd_grow(args) -> None:
    """Detect ATS for companies currently marked 'manual' or in unresolved.yaml."""
    db = DB()
    registry.sync_to_db(db)
    manual = [c for c in db.get_companies() if c.get("ats") in (None, "manual")]
    print(f"Attempting ATS detection for {len(manual)} unresolved companies ...")
    resolved = 0
    for c in manual:
        found = asyncio.run(detect_mod.detect(c["name"], c.get("hq")))
        if found.get("ats") != "manual":
            entry = {**c, **found, "tier": c.get("tier", 1)}
            registry.append_company("national.yaml", entry)
            db.upsert_company(entry)
            resolved += 1
            print(f"  resolved {c['name']} -> {found['ats']}")
    print(f"Resolved {resolved}/{len(manual)}.")
    db.close()


def _row_to_posting(row: dict) -> Posting:
    return Posting(
        id=row["id"], company_slug=row["company_slug"], company_name=row["company_name"],
        title=row["title"], apply_url=row["apply_url"], ats_job_id=row.get("ats_job_id"),
        locations=json.loads(row.get("locations") or "[]"),
        is_seattle_metro=bool(row.get("is_seattle_metro")),
        is_remote_us=bool(row.get("is_remote_us")), is_wa=bool(row.get("is_wa")),
        term=row.get("term", "unspecified"), description=row.get("description", ""),
        eligibility_flags=json.loads(row.get("eligibility_flags") or "[]"),
        fit_score=row.get("fit_score", 0),
    )


def cmd_tailor(args) -> None:
    from .tailor import tailor
    db = DB()
    row = db.get_posting(args.posting_id)
    if not row:
        print(f"No posting {args.posting_id}"); return
    posting = _row_to_posting(row)
    result = tailor(posting, use_llm=not args.no_llm)
    db.set_resume(args.posting_id, result["tex_path"], result["pdf_path"])
    print(json.dumps({k: v for k, v in result.items() if k != "requirements"}, indent=2))
    db.close()


def cmd_notes(args) -> None:
    db = DB()
    row = db.get_posting(args.posting_id)
    if not row:
        print(f"No posting {args.posting_id}"); return
    posting = _row_to_posting(row)
    result = notes_mod.generate(posting, use_llm=not args.no_llm)
    db.set_notes(args.posting_id, result)
    for kw in result["keyword_coverage"]["present"]:
        db.bump_keyword(kw, covered=True)
    for kw in result["keyword_coverage"]["missing"]:
        db.bump_keyword(kw, covered=False)
    print(json.dumps(result, indent=2))
    db.close()


def cmd_gaps(args) -> None:
    db = DB()
    rows = db.keyword_rollup()
    total = len(db.open_postings())
    print(f"\nCross-posting gap rollup ({total} open postings):\n")
    for r in rows:
        if r["covered"]:
            continue
        bar = "█" * min(r["seen_count"], 40)
        print(f"  {r['keyword']:<22} {bar} {r['seen_count']}")
    db.close()


def cmd_table(args) -> None:
    db = DB()
    rows = db.open_postings(seattle_only=args.seattle)
    print(f"\n{'DOT':<3}{'COMPANY':<22}{'TITLE':<40}{'LOCATION':<18}{'CLOSES':<12}{'FIT':>4}")
    print("-" * 100)
    for r in rows[:60]:
        dot = "●" if r["is_seattle_metro"] else "○"
        locs = ", ".join(json.loads(r.get("locations") or "[]"))[:16]
        if r["closes_kind"] == "rolling":
            closes = "Rolling"
        elif r["closes_at"]:
            dr = days_remaining(r["closes_at"])
            closes = f"{r['closes_at']}" + (f" ({dr}d)" if dr is not None else "")
            if r["closes_kind"] == "estimated":
                closes = "~" + closes
        else:
            closes = "Unknown"
        print(f"{dot:<3}{r['company_name'][:20]:<22}{r['title'][:38]:<40}{locs:<18}{closes[:11]:<12}{r['fit_score']:>4}")
    print(f"\n{len(rows)} open postings.\n")
    db.close()


def cmd_export(args) -> None:
    from .export import export_snapshot
    path = Path(args.path) if args.path else ROOT / "web" / "public" / "data.json"
    n = export_snapshot(path)
    print(f"Exported {n} postings -> {path}")


def cmd_serve(args) -> None:
    from .serve import serve
    serve(port=args.port)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="radar", description="Internship Radar pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sweep", help="run a collection sweep")
    s.add_argument("--tier", type=int, default=None)
    s.add_argument("--lists", action="store_true", help="also sweep community lists")
    s.add_argument("--no-notify", action="store_true")
    s.set_defaults(func=cmd_sweep)

    d = sub.add_parser("detect", help="probe a company's ATS")
    d.add_argument("name"); d.add_argument("homepage", nargs="?", default=None)
    d.set_defaults(func=cmd_detect)

    g = sub.add_parser("grow", help="detect ATS for unresolved companies")
    g.set_defaults(func=cmd_grow)

    t = sub.add_parser("tailor", help="generate a tailored resume")
    t.add_argument("posting_id"); t.add_argument("--no-llm", action="store_true")
    t.set_defaults(func=cmd_tailor)

    n = sub.add_parser("notes", help="generate notes blocks")
    n.add_argument("posting_id"); n.add_argument("--no-llm", action="store_true")
    n.set_defaults(func=cmd_notes)

    sub.add_parser("gaps", help="cross-posting gap rollup").set_defaults(func=cmd_gaps)

    tb = sub.add_parser("table", help="print the open table")
    tb.add_argument("--seattle", action="store_true")
    tb.set_defaults(func=cmd_table)

    e = sub.add_parser("export", help="dump JSON snapshot for the UI")
    e.add_argument("path", nargs="?", default=None)
    e.set_defaults(func=cmd_export)

    sv = sub.add_parser("serve", help="run the local read/write API")
    sv.add_argument("--port", type=int, default=8787)
    sv.set_defaults(func=cmd_serve)
    return p


def main(argv=None) -> None:
    _setup_logging()
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
