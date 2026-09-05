# Internship Radar

A self-hosted internship tracker for CS/SWE roles. It pulls postings from every
source it can reach, ranks Seattle-area roles first, tailors a résumé per
posting, and tells you what to build to be competitive for it.

The premise: **missing a posting is the only real failure mode.** Almost every
company — from a 6-person startup to Boeing — hosts its jobs on one of ~8
applicant tracking systems (ATS), and every one of those has a public JSON
endpoint. Radar hits those directly, so you see roles *earlier* than the
aggregators that scrape them.

```
● Truveta            Software Engineering Intern    Seattle, WA   ▓▓▓░░ ~Sep 24   TEX   87  reviewing
● Amazon             SDE Intern — Summer 2027       Seattle, WA   ▓▓▓▓▓ Rolling   PDF   82  new
○ Stripe             Software Engineer, Intern      Remote (US)   ▓▓░░░ ~Apr 2    Gen   74  new
```

<p align="center"><em>One dense table. Seattle-first. The runway bar is the only saturated color on the screen.</em></p>

---

## What it does

- **Coverage first.** A hand-curated Seattle registry (~50 anchor companies,
  growable) polled every 15 minutes, plus ATS platform sweeps, big-company
  custom collectors (Amazon, Microsoft), community GitHub lists, and RSS feeds.
- **Speed of notification.** New Seattle-area, high-fit postings ping a Discord
  webhook (or ntfy) instantly; everything else batches into a morning digest.
- **A tailored résumé per posting.** Bullets are *selected and re-angled* from a
  single experience bank — never invented — rendered to `.tex`/`.pdf`. A
  hallucination check fails the build if any new company, tech, or number
  appears.
- **Auto-prepare** (`radar autoapply`), with an honest readiness model. It never
  auto-submits and never calls anything "Ready" on its own — **Ready means _you_
  approved the résumé**. For each strong Seattle match it tailors a résumé and
  leaves it **⏳ Review**; postings missing a **must-have** skill are **held**
  (⚠ Gaps) rather than tailored; postings with too little job-description text to
  judge are flagged **◍ Thin JD** instead of pretended-ready. The detail drawer
  shows a **diff vs. your base résumé** so approving is an informed click.
- **Actionable notes per posting.** The skill gaps in the JD, the highest-ROI
  thing to build to close them, and the one signal that would make *this*
  reviewer stop.
- **A `/gaps` rollup.** Aggregates missing skills across all open postings so you
  know what to build next — better than any single posting tells you.

Full design rationale lives in [`docs/spec.md`](docs/spec.md).

---

## Architecture

Everything is a cron-driven batch job. No queues, no microservices.

```
 collectors ──▶ normalize ──▶ filter ──▶ dedupe ──▶ score ┬─▶ SQLite ──▶ Next.js UI
 (ats/custom/                                    deadlines │      ▲
  lists/feeds)                                       notes │      │
                                                    tailor ┘   radar serve (API)
                                                                    │
                                                            Discord / ntfy alerts
```

- **Backend** — Python 3.11 · `httpx` · `pydantic` · `rapidfuzz` · `jinja2` ·
  SQLite. One command runs the whole pipeline: `python -m radar.run sweep`.
- **Frontend** — Next.js (App Router) + TypeScript. Reads a live API
  (`radar serve`) or a static `data.json` snapshot.
- **LLM** — optional. Résumé re-angling and notes use Gemini's free tier when a
  key is present, and fall back to a deterministic path when it isn't.

---

## Quick start

```bash
git clone https://github.com/abhip1008/internship-radar.git
cd internship-radar
make install              # venv + backend deps + web deps

# 1. Collect. Hits real ATS APIs; writes to data/radar.db
make sweep

# 2. See what it found
make table
make gaps

# 3. Run the UI (two terminals)
make serve                # local read/write API on :8787
make web                  # Next.js on http://localhost:3000
```

No LaTeX toolchain? Résumés still render to `.tex`; install
[`tectonic`](https://tectonic-typesetting.github.io/) (`brew install tectonic`)
to also get `.pdf`.

Optional alerts and LLM tailoring: copy `.env.example` to `.env` and fill in
`DISCORD_WEBHOOK`, `NTFY_TOPIC`, and/or `GEMINI_API_KEY`.

---

## CLI

| Command | What it does |
|---|---|
| `radar sweep [--tier N] [--lists]` | Run a collection sweep |
| `radar table [--seattle]` | Print the open postings table |
| `radar gaps` | Cross-posting skill-gap rollup |
| `radar detect "Company" [homepage]` | Auto-detect a company's ATS |
| `radar grow` | Resolve the ATS for unresolved companies |
| `radar tailor <posting_id>` | Generate a tailored résumé |
| `radar notes <posting_id>` | Generate the notes blocks |
| `radar autoapply [--scope S] [--min-fit N]` | Auto-prepare clean-match postings; hold ones with gaps |
| `radar export [path]` | Dump the JSON snapshot for the UI |
| `radar serve [--port]` | Run the local read/write API |

Invoke via `./.venv/bin/python -m radar.run <command>`.

---

## Adding companies

Edit `registry/seattle.yaml`. Each entry is a *candidate* — `radar detect`
confirms the real board:

```yaml
- name: Remitly
  slug: remitly
  ats: greenhouse        # radar detect will verify/fix this
  board_token: remitly
  hq: Seattle, WA
  tier: 0
```

`radar detect "Remitly" https://remitly.com` probes Greenhouse, Lever, Ashby,
Recruitee, SmartRecruiters, then falls back to scraping the careers page for a
board host. Unresolved companies land in `registry/unresolved.yaml` for a weekly
review.

The résumé bank (`data/experience.yaml`), gap remediation map
(`data/remediation.yaml`), and scoring weights (`config.yaml`) are all yours to
edit.

---

## Deployment

- **Local (recommended to start):** a `cron`/`launchd` job running
  `radar sweep` every 15 minutes plus `next dev` is genuinely enough.
- **Always-on:** the included [`collect.yml`](.github/workflows/collect.yml)
  GitHub Action sweeps on a 15-minute schedule and commits the snapshot; host
  the read-only UI on Vercel.

---

## Tests

```bash
make test        # 20 tests: filter precision, dedupe/merge, geo, scoring,
                 # deadline parsing, résumé hallucination guardrails
```

CI ([`ci.yml`](.github/workflows/ci.yml)) runs the Python suite and a production
Next.js build on every push.

---

## Operating principles

Radar only hits public, unauthenticated ATS endpoints, with a descriptive
User-Agent, per-host rate limiting, and conditional requests. It never
auto-submits applications, never creates accounts, and never stores credentials.
LinkedIn / Indeed / Glassdoor / Handshake are handled by manual add — their data
is downstream of the ATS endpoints already covered.

## License

MIT — see [LICENSE](LICENSE).
