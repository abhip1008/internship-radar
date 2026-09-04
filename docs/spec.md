# Internship Radar — Project Spec

A self-hosted internship tracker for CS/SWE roles that pulls from every source it can reach, ranks Seattle-area postings first, tailors a resume per posting, and tells you what to go learn or build to be competitive for it.

Status: design doc. Everything below is buildable by one person. Cost target: $0/month excluding optional LLM credits.

---

## 1. Goals

1. **Coverage before anything else.** If a CS internship is open within ~60 miles of Seattle, it should be in the table within 30 minutes of going live. Missing a posting is the only real failure mode.
2. **Speed of notification.** Early applicants at big companies get read. The system exists to shorten the gap between "posted" and "you know about it."
3. **A tailored resume per posting**, generated automatically, stored as a file, linked from its row.
4. **Actionable notes per posting** — the skills, projects, and signals that would move you from "plausible" to "obvious hire" for that specific role.
5. **A UI you actually open every morning.** One table, fast, no dashboard clutter.

### Non-goals

- Auto-submitting applications. Workday/Greenhouse forms break constantly and auto-apply gets accounts flagged. The system takes you to a filled-in application; you press submit.
- Being a general job board. Internships and new-grad-adjacent early-career roles only.
- A mobile app. Responsive web is enough.

### Honest constraints to design around

- **"As soon as posted" means 5–30 minutes, not instant.** No public feed pushes new postings. Everything is polling. 15-minute cadence on Tier 0 companies gets you inside the window that matters.
- **LinkedIn, Indeed, Glassdoor, and Handshake all prohibit scraping.** They're also the sources with the worst signal-to-noise. The plan below routes around them by going to the applicant tracking systems (ATS) directly, which is where those aggregators get their data anyway, usually *later* than you will.
- **Most postings don't publish a close date.** Section 9 covers how to handle that without inventing numbers.

---

## 2. The table

Requested columns, plus a few that pull their weight.

| Column | Content | Notes |
|---|---|---|
| **Role** | Company · title, linking to the apply page | Primary cell. Company logo favicon, 16px, fetched once and cached |
| **Location** | Normalized: `Seattle, WA` / `Bellevue, WA` / `Remote (US)` / `Redmond, WA + 2` | Seattle-area rows get a filled location dot |
| **Posted** | Relative: `2h`, `1d`, `6d` | Sorts by `first_seen_at`, not the company's claimed post date |
| **Closes** | Deadline bar + date, or `Rolling`, or `Unknown` | See §9 |
| **Resume** | `PDF` / `TEX` links, or a `Generate` button if not built yet | Regenerate on demand |
| **Notes** | Two-line preview of the gap analysis, expands in the drawer | See §11 |
| **Fit** | 0–100 | Explainable, not a black box. Hover shows the breakdown |
| **Status** | `New` → `Reviewing` → `Applied` → `OA` → `Interview` → `Offer` / `Rejected` / `Skipped` | Only column you edit by hand |

Default sort: `Fit desc` within `Seattle-area first`, then `Posted desc`.
Default filter: `Status = New or Reviewing`, `Term = Summer 2027 or off-cycle`.

---

## 3. Architecture

```
                    ┌──────────────────────────────────────────┐
   sources          │  COLLECTORS (one module per source type) │
   ─────────        │  ats/greenhouse.py   ats/lever.py        │
   4 500+ company   │  ats/ashby.py        ats/workday.py      │
   job boards       │  ats/smartrecruiters.py  ats/workable.py │
                    │  custom/amazon.py    custom/microsoft.py │
                    │  lists/github_repos.py   feeds/rss.py    │
                    └───────────────┬──────────────────────────┘
                                    │  raw postings (JSON)
                                    ▼
                    ┌──────────────────────────────────────────┐
                    │  NORMALIZE → FILTER → DEDUPE             │
                    │  · canonical schema                      │
                    │  · is_internship? is_cs? term?           │
                    │  · geo resolve + Seattle-area flag       │
                    │  · content hash + fuzzy title match      │
                    └───────────────┬──────────────────────────┘
                                    │  new rows only
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            ┌──────────────┐ ┌─────────────┐ ┌──────────────┐
            │ SCORER       │ │ TAILOR      │ │ NOTIFIER     │
            │ fit 0-100    │ │ resume.tex  │ │ push/Discord │
            │ explainable  │ │ → resume.pdf│ │ /email       │
            └──────┬───────┘ └──────┬──────┘ └──────────────┘
                   └────────┬───────┘
                            ▼
                    ┌───────────────┐      ┌────────────────┐
                    │ SQLite / PG   │─────▶│ Next.js UI     │
                    │ + /files      │      │ one table      │
                    └───────────────┘      └────────────────┘
```

Everything is a cron-driven batch job. No queues, no microservices. A single `python -m radar.run --tier 0` is the whole pipeline for one tier.

---

## 4. Source strategy

The core insight: **almost every company, from a 6-person startup to Boeing, hosts its postings on one of about eight ATS platforms, and every one of those platforms has a public, unauthenticated, JSON job-board endpoint.** You don't scrape. You hit the same API the company's own careers page hits.

### Tier 0 — Seattle-area company registry (highest priority, 15-min polling)

A hand-curated + auto-grown registry of every company with engineering headcount in the Puget Sound region. This is where the "every single one" requirement lives. Target: 400+ companies at launch, growing weekly.

**Seeding the registry** — pull company names from these directories, then auto-detect each one's ATS (§5.2):

- Y Combinator company directory, filtered to Seattle/Bellevue/Redmond
- Madrona Venture Group portfolio
- Pioneer Square Labs portfolio + PSL Ventures
- Fuse Venture Partners, Flying Fish Partners, Ascend.vc, Voyager Capital portfolios
- Techstars Seattle cohorts (all years)
- AI2 Incubator portfolio
- Built In Seattle company list
- GeekWire 200 (ranked list of PNW startups, updated monthly)
- WTIA member directory
- Washington Technology Industry Association job board
- UW CSE industry affiliates list (companies that already recruit UW students — highest conversion)
- Levels.fyi company list filtered by Seattle offices
- Your own LinkedIn "companies in Seattle" browsing, entered manually

**Anchor employers to hardcode immediately** (verify board type once via §5.2, then never think about again):

*Large tech:* Amazon, Amazon Web Services, Microsoft, Google (Kirkland/Seattle), Meta (Seattle/Bellevue), Apple (Seattle), Nvidia (Redmond), Salesforce/Tableau, Oracle, Adobe, Uber (Seattle), Snap, Airbnb, Stripe (Seattle), Snowflake (Bellevue), Databricks, OpenAI (Seattle), Anthropic (Seattle), Scale AI, Zillow, Expedia, Redfin, DoorDash (Seattle), Instacart, Indeed (Seattle), Dropbox, Twilio, Cloudflare (Seattle), Atlassian, Netflix (Seattle office), Roblox, Electronic Arts (Redmond), Nintendo of America (Redmond), Valve, Bungie, ArenaNet, Amazon Games, Wizards of the Coast, PopCap.

*Aerospace/hardware/defense:* Boeing, Blue Origin (Kent), SpaceX (Redmond Starlink), Stoke Space (Kent), Aerojet Rocketdyne (Redmond), Anduril (Seattle office), Applied Intuition, Kymeta, Impinj, Tesla (Seattle/Bellevue), Rivian (Bellevue), Zoox (Seattle), Aurora, Nautilus, Radian Aerospace, First Mode, Systima, Astronics.

*Telecom/enterprise/retail/health:* T-Mobile (Bellevue), Costco (Issaquah), Nordstrom, Starbucks, Alaska Airlines, REI, PACCAR, Weyerhaeuser, Puget Sound Energy, Providence, Fred Hutch, Seattle Children's, UW Medicine, Allen Institute, PNNL (Richland, DOE lab), Battelle.

*Mid-size / growth-stage Seattle:* Smartsheet, Remitly, Outreach, Highspot, Icertis, Auth0/Okta, Accolade, Avalara, PitchBook, Qumulo, Pulumi, Temporal, Amperity, Statsig, Common Room, Read AI, Truveta, Karat, Flyhomes, Esper, WhyLabs, SeekOut, Sana Biotechnology, Adaptive Biotechnologies, Rec Room, Convoy successors, Chewy (Seattle), Zulily successors, Cascade Bicycle-adjacent civic tech, Textio, Skilljar, Suplari, Attunely, Xealth, Sila, Dispatch, Trupanion, Porch, Knock, Modumetal, Membrion.

*Public sector / civic:* City of Seattle IT, King County, Sound Transit, Port of Seattle, WA State DES, Seattle Public Utilities. These run internship programs almost nobody in CS applies to.

> Every name above is a *candidate*. The bootstrap script (§5.2) confirms which ATS each actually uses and drops the ones with no discoverable board. Don't trust this list's ATS assumptions — trust the probe.

### Tier 1 — ATS platform sweeps (hourly)

For companies not yet in the registry, sweep the platforms themselves for anything Seattle-tagged. Greenhouse and Lever both expose per-company boards only, so this tier depends on a **board token list**, which you grow by:

- Mining `boards.greenhouse.io/<token>` and `jobs.lever.co/<company>` links out of the GitHub community lists (§Tier 3)
- Mining them out of Hacker News "Who is hiring?" monthly threads (Algolia API, free: `https://hn.algolia.com/api/v1/search?query=hiring&tags=story`)
- Mining them out of any company careers page you visit — the redirect target *is* the token

### Tier 2 — Custom career-site APIs (30-min polling)

The largest employers run their own systems. Each needs a small bespoke collector, but each is one endpoint:

| Employer | Approach |
|---|---|
| Amazon | `amazon.jobs` search JSON endpoint; filter `category=internship`, `normalized_location=Seattle` |
| Microsoft | `careers.microsoft.com` search API (`gcsservices.careers.microsoft.com/search/api/v1/search`), filter by profession + employment type `Internship` |
| Boeing / T-Mobile / Costco / Nordstrom / Starbucks / Alaska / PACCAR | Workday. Same POST pattern for all (§5.1) |
| Tesla | Custom `tesla.com/cua-api/apps/careers/state` JSON |
| Google | `careers.google.com` list API with `employment_type=INTERN` |
| Meta / Apple | Custom endpoints; if brittle, fall back to community lists + RSS |
| Blue Origin, SpaceX | Greenhouse-family boards; treat as Tier 0 |

Rule: **if a custom collector breaks twice in a month, demote that company to "watch via community lists" and stop maintaining it.** Your time is worth more than 100% coverage of one employer that's also on every list in Tier 3.

### Tier 3 — Community lists (2× daily)

Free, high-recall, slightly stale. Parse `listings.json` where available rather than the README.

- `SimplifyJobs/Summer2027-Internships` — the big one, ~46k stars, maintained by Simplify + Pitt CSC, updated daily, has a machine-readable `.github/scripts/listings.json`
- `vanshb03/Summer2027-Internships`
- `sndsh404/summer-2027-internships` — includes off-season roles
- `SimplifyJobs/New-Grad-Positions` — for early-career reqs that accept juniors
- `speedyapply/*` trackers — one publishes ~180 open SWE internships aggregated from thousands of employer boards, refreshed every 30 min
- Off-season / Fall / Winter repos, since a Fall 2027 co-op posted now is a real option

These are also your best **registry growth engine**: every new company appearing in these lists that isn't in your registry gets auto-queued for ATS detection.

### Tier 4 — Long tail (daily)

- **RSS/Atom**: Ashby, Workable, Recruitee, and many Greenhouse boards expose feeds. Free and cheap to poll.
- **Google Programmable Search Engine** (100 queries/day free) restricted to `boards.greenhouse.io`, `jobs.lever.co`, `jobs.ashbyhq.com`, `apply.workable.com`, with queries like `intern software engineer Seattle 2027`. Catches companies you've never heard of.
- **Handshake**: no API, ToS-restricted. Handle manually — a 5-minute daily check with a saved search, and a `+ Add manually` button in the UI that accepts a URL and runs the full pipeline on it. UW postings that appear *only* on Handshake are worth the manual step.
- **University-restricted programs**: UW CSE mailing lists, department newsletters. Manual add.

---

## 5. Talking to the ATS platforms

### 5.1 Endpoint patterns

All unauthenticated GET unless noted. Cache `ETag`/`Last-Modified` and send conditional requests — most of these support it, which makes 15-minute polling nearly free.

```
Greenhouse      GET  https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
                     → {jobs: [{id, title, location:{name}, absolute_url, updated_at, content}]}

Lever           GET  https://api.lever.co/v0/postings/{company}?mode=json
                     → [{id, text, categories:{location, team, commitment}, hostedUrl, createdAt, descriptionPlain}]

Ashby           GET  https://api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true
                     → {jobs: [{id, title, location, employmentType, jobUrl, publishedAt, descriptionPlain}]}

SmartRecruiters GET  https://api.smartrecruiters.com/v1/companies/{id}/postings?limit=100&offset=0
                     → {content: [{id, name, location, releasedDate, ref}]}  (detail: /postings/{id})

Workable        GET  https://apply.workable.com/api/v1/widget/accounts/{id}?details=true

Recruitee       GET  https://{company}.recruitee.com/api/offers/

Personio        GET  https://{company}.jobs.personio.de/xml

Workday         POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
                     Content-Type: application/json
                     {"appliedFacets":{}, "limit":20, "offset":0, "searchText":"intern"}
                     → {total, jobPostings:[{title, externalPath, locationsText, postedOn}]}
                     Detail: GET .../wday/cxs/{tenant}/{site}{externalPath}
```

Workday is the one that needs care: `{tenant}`, `{N}`, and `{site}` differ per employer and are visible in the careers-page URL. Store all three in the registry. Paginate 20 at a time until `offset >= total`.

### 5.2 ATS auto-detection (the bootstrap script)

Given a company name and homepage, find its board without you looking anything up:

```python
CANDIDATE_PROBES = [
    ("greenhouse",      "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"),
    ("lever",           "https://api.lever.co/v0/postings/{slug}?mode=json"),
    ("ashby",           "https://api.ashbyhq.com/posting-api/job-board/{slug}"),
    ("recruitee",       "https://{slug}.recruitee.com/api/offers/"),
    ("smartrecruiters", "https://api.smartrecruiters.com/v1/companies/{slug}/postings"),
]

def detect(company_name, homepage=None):
    # 1. slug guesses: lowercased name, name minus spaces, name minus "inc/labs/technologies"
    # 2. probe each candidate; 200 + non-empty payload == hit
    # 3. fallback: fetch homepage, regex for board hosts in hrefs
    #    r'(boards|job-boards)\.greenhouse\.io/([\w-]+)'
    #    r'jobs\.lever\.co/([\w-]+)'
    #    r'jobs\.ashbyhq\.com/([\w-]+)'
    #    r'([\w-]+)\.wd(\d)\.myworkdayjobs\.com/([\w-]+)'
    #    r'apply\.workable\.com/([\w-]+)'
    # 4. fallback: fetch /careers, /jobs, /company/careers and repeat step 3
    # 5. still nothing → mark source_type="manual", surface in an "unresolved" admin list
```

Run this once per new company, cache the result forever, re-run only when a collector 404s twice.

### 5.3 Registry file format

```yaml
# registry/seattle.yaml
- name: Remitly
  slug: remitly
  ats: greenhouse
  board_token: remitly
  hq: Seattle, WA
  tier: 0
  tags: [fintech, growth-stage]

- name: Boeing
  slug: boeing
  ats: workday
  workday:
    tenant: boeing
    wd: 1
    site: EXTERNAL_CAREERS
  hq: Arlington, VA
  offices: [Everett WA, Renton WA, Seattle WA, Auburn WA]
  tier: 0
  tags: [aerospace, large-employer]

- name: Amazon
  slug: amazon
  ats: custom
  collector: custom.amazon
  tier: 0
  poll_minutes: 15
```

---

## 6. Filtering: what counts

Run in order, cheapest first. Log every rejection with its reason so you can audit for false negatives — **a false negative is expensive, a false positive costs you three seconds of scrolling.** Tune permissive.

**6.1 Is it an internship or early-career role?**

```
TITLE_INCLUDE  = intern, internship, co-op, coop, summer analyst, apprentice,
                 university, new grad, new graduate, early career, entry level,
                 student, campus, "2027", "2026", trainee, residency
```

**6.2 Is it CS?**

```
CS_INCLUDE = software, swe, sde, developer, engineer(ing) + [software|platform|
             backend|frontend|full stack|fullstack|systems|infrastructure|cloud|
             data|ml|machine learning|ai|security|devops|site reliability|sre|
             embedded|firmware|mobile|ios|android|qa|test|automation|research],
             computer science, computer engineering, data scientist, data analyst,
             research scientist, quantitative developer, technical program manager,
             solutions architect, applied scientist

CS_EXCLUDE = sales, marketing, recruiting, hr, finance intern (unless "quant"),
             legal, nursing, warehouse ops, driver, retail associate
```

Keep `technical program manager`, `solutions architect`, `IT` in — some of the best-paying Seattle internships (Amazon RME automation, T-Mobile IT) are titled unhelpfully.

**6.3 Term classification**
Regex the title and description for `Summer 2027`, `Summer 2026`, `Fall 2026`, `Winter 2027`, `Spring 2027`, `year-round`, `co-op`. Unknown → `unspecified`, still shown. Default UI filter includes Summer 2027 + off-season + unspecified.

**6.4 Geography**
Normalize with a static gazetteer (no API needed):

```
SEATTLE_METRO = {seattle, bellevue, redmond, kirkland, bothell, everett, renton,
                 kent, tukwila, issaquah, sammamish, lynnwood, mukilteo, auburn,
                 federal way, tacoma, woodinville, mercer island, shoreline,
                 duvall, monroe, snoqualmie, north bend, puget sound, greater seattle,
                 wa, washington state}
```
Flags: `is_seattle_metro`, `is_remote_us`, `is_wa`, `other`. Nothing is filtered *out* by geography — Seattle just sorts to the top and everything else is one click away. Remote-US roles count as near-Seattle for ranking.

**6.5 Eligibility red flags** (surfaced as a badge, never auto-hidden)
`PhD required`, `Master's required`, `must be graduating by`, `US citizenship required`, `active security clearance`, `no visa sponsorship`. Compare graduation date from config (e.g. June 2028) against any stated window and badge mismatches as `Check eligibility`.

---

## 7. Dedupe

The same Amazon SDE Intern req will arrive from amazon.jobs, three GitHub lists, and an RSS feed.

1. **Exact**: `sha1(normalized_apply_url_without_query)`.
2. **Strong**: `(company_slug, ats_job_id)` when available.
3. **Fuzzy**: `(company_slug, normalized_title, location_bucket, term)` where `normalized_title` strips seniority noise, years, and req IDs; match with `rapidfuzz.token_set_ratio >= 92`.

On collision, **merge rather than drop**: keep the earliest `first_seen_at`, prefer the ATS-direct apply URL over an aggregator's, union the location list, keep the longest description, and append the source to `sources[]`. This matters — the community list often has a Simplify autofill link while the ATS has the canonical one, and you want both.

---

## 8. Freshness and alerts

**Polling cadence**

| Tier | Cadence | Notes |
|---|---|---|
| 0 (Seattle registry) | 15 min | Conditional requests; a full sweep of 400 boards is ~400 cheap GETs |
| 1 (platform sweeps) | 60 min | |
| 2 (custom big-co) | 30 min | Amazon/Microsoft churn constantly |
| 3 (GitHub lists) | 12 h | Upstream only updates daily |
| 4 (search/RSS) | 24 h | Google PSE quota is 100/day |

Stagger with a per-company hash offset so you don't fire 400 requests in the same second.

**"New" detection**: a posting is new if its dedupe key has never been written. `first_seen_at = now()`. Never trust the company's `posted_on` — Workday reposts and lies.

**Notification pipeline**

```
new posting → fit score → if score >= threshold OR is_seattle_metro:
    → generate tailored resume (async, don't block the alert)
    → push notification
```

Channels, in order of how well they actually work:
1. **Discord webhook** to a private server. One line per posting, embeds with company/title/location/apply link. Free, instant, works on phone. Batch into one message if 5+ arrive together.
2. **ntfy.sh** topic for phone push without an app account.
3. **Email digest** at 7am for everything below the alert threshold.

Alert rule: instant ping only for `is_seattle_metro AND fit >= 60`, or any posting from a `watchlist: true` company. Everything else waits for the digest. Getting pinged 40 times a day means you stop reading the pings.

---

## 9. Close dates (the honest version)

Maybe 20% of tech internship postings publish a deadline. Don't fabricate one. Three states:

- **`Explicit`** — parsed from the description. Patterns: `applications close`, `apply by`, `deadline`, `open until`, `priority deadline`, `will close on`. Store the source sentence and show it on hover.
- **`Rolling`** — description says rolling/until filled, or the company is known-rolling (most big tech). Display `Rolling — apply now` with the urgency bar pinned high, because rolling means *earlier is strictly better*.
- **`Unknown`** — no signal. Display an **estimated close** with visible low confidence, derived from a per-company historical median (`median(removed_at - first_seen_at)` across your own observed history) with a global fallback of 21 days. Label it `~est`, style it muted, never sort by it as if it were fact.

**Disappearance tracking is the real deadline signal.** Every sweep, any posting in the DB that no longer appears in its source gets `last_seen_at` frozen and, after two consecutive missed sweeps, `status_source = closed`. This gives you two valuable things: a truthful "closed" state in the UI, and per-company posting-lifetime statistics that make your estimates progressively better.

---

## 10. Resume tailoring engine

This shares its guts with the LaTeX pipeline you've already scoped — same experience bank, same `.tex` template, same "human presses submit" boundary. The tracker just becomes the thing that triggers it automatically instead of you pasting a JD.

### 10.1 Experience bank

The source of truth. Every bullet you could ever put on a resume, stored once, tagged, in `data/experience.yaml`. Bullets are *selected and re-angled*, never invented.

```yaml
identity:
  name: "..."
  email: "..."
  phone: "..."
  links: {github: "...", linkedin: "...", portfolio: "..."}
  education:
    school: University of Washington Bothell
    degree: B.S. Computer Science & Software Engineering
    grad: 2028-06
    coursework: [Data Structures, Object-Oriented Programming, Calculus 1, Calculus 2]

experiences:
  - id: mechxcel
    org: MechXcel Robotics
    role: Co-Founder
    location: Bothell, WA
    start: 2023-07
    end: present
    kind: leadership
    bullets:
      - id: mechxcel-scale
        text: "Co-founded a non-profit robotics organization, building the curriculum, competition teams, and operations that serve 120+ students in grades 3-8 around Bothell"
        tags: [leadership, ops, education, scale]
        metrics: {students: 120}
      - id: mechxcel-curriculum
        text: "Designed and taught a hands-on curriculum in Python programming and engineering fundamentals..."
        tags: [python, teaching, curriculum]
      - id: mechxcel-awards
        text: "Mentored student teams to 13 competition awards..."
        tags: [mentorship, debugging, communication]
      - id: mechxcel-fundraising
        text: "Raised and donated $20,000 through sponsorship outreach..."
        tags: [ownership, communication, nonprofit]
      - id: mechxcel-ops
        text: "Managed volunteer coaches, scheduling, parent communication, and competition logistics..."
        tags: [ops, leadership]

  - id: startup-club
    org: Startup Club
    role: Engineering Leader
    start: 2025-12
    end: present
    kind: leadership
    bullets:
      - {id: sc-ownership, text: "Lead engineering work on a student-facing web platform...", tags: [web, ownership, collaboration]}
      - {id: sc-review,    text: "Write code, review PRs, and guide teammates...", tags: [code-review, mentorship, git]}
      - {id: sc-agile,     text: "Run an Agile workflow...", tags: [agile, process, delivery]}
      - {id: sc-arch,      text: "Lead architecture and design discussions...", tags: [architecture, tradeoffs, design]}

projects:
  - id: linx
    name: Linx
    stack: [Python, Ollama, Nemotron 3, Nemoclaw]
    award: "4th Place - BeaverHacks NVIDIA Track"
    kind: ai-systems
    bullets:
      - {id: linx-overview, text: "Built a local-first AI system for Alzheimer's care...", tags: [ai, agents, healthcare, hackathon]}
      - {id: linx-pipeline, text: "Designed a Python-based agentic pipeline with a rolling short-term memory buffer...", tags: [python, llm, memory, architecture]}
      - {id: linx-rules,    text: "Integrated Nemoclaw as a parallel deterministic rule layer...", tags: [safety, systems-design, determinism]}
      - {id: linx-contract, text: "Enforced a strict JSON output contract via system prompt engineering; fully offline...", tags: [prompt-engineering, reliability, offline]}

  - id: everwell
    name: EverWell
    stack: [Node.js, Express, OAuth 2.0, WHOOP API]
    kind: backend
    bullets:
      - {id: ew-platform, text: "Built an AI-powered elder care platform streaming WHOOP wearable data...", tags: [backend, nodejs, oauth, api-integration]}
      - {id: ew-anomaly,  text: "Implemented anomaly monitoring that flags abnormal vitals...", tags: [monitoring, alerting, health]}
      - {id: ew-agnostic, text: "Designed the wearable integration layer to be device-agnostic...", tags: [abstraction, api-design]}

  - id: thunderbolts
    name: Seattle Thunderbolts Cricket Academy App
    stack: [React Native, Expo, TypeScript, Supabase, PostgreSQL, Stripe]
    kind: fullstack-product
    bullets:
      - {id: tb-product, text: "Built a mobile app where members book sessions, pay with Stripe, browse events, and trade gear...", tags: [mobile, product, payments, typescript]}
      - {id: tb-db,      text: "Designed a 6-table PostgreSQL database with row-level security and a booking concurrency rule...", tags: [sql, concurrency, data-modeling, security]}
      - {id: tb-stripe,  text: "Server-side Stripe price validation via a backend function; interactive real-time facility map...", tags: [payments, security, backend]}

  - id: resource-hub
    name: UW Bothell Student Resource Hub
    stack: [React, Open Library API]
    team: true
    kind: frontend
    bullets:
      - {id: rh-roles,  text: "Built the React frontend with role-based views and Open Library API integration with fallbacks...", tags: [react, api-integration, error-handling]}
      - {id: rh-upload, text: "Built React components for file upload with progress and error handling; API contracts with backend teammates...", tags: [react, collaboration, ux]}

skills:
  languages: [Python, JavaScript, TypeScript, Java, SQL]
  frameworks: [React, React Native, Node.js, Express]
  data: [PostgreSQL, Supabase]
  ai: [Ollama, Nemotron, prompt engineering, agentic pipelines]
  tools: [Git, Agile, OOP, Stripe, OAuth 2.0]
```

### 10.2 Tailoring pipeline

```
JD text
  ↓ extract_requirements()      → {must_have[], nice_to_have[], keywords[], domain, seniority}
  ↓ score_bullets()             → cosine(tag_vector, jd_vector) + keyword overlap + recency
  ↓ select()                    → 2 experiences × 3-5 bullets, 3 projects × 2-3 bullets, 1 page hard cap
  ↓ reorder()                   → most JD-relevant project first, skills reordered to lead with JD stack
  ↓ rephrase()                  → LLM rewrites selected bullets to foreground JD-relevant angles
  ↓ verify()                    → guardrails (below)
  ↓ render()                    → Jinja2 → .tex → tectonic/pdflatex → .pdf
  ↓ store()                     → files/resumes/{company}_{role_slug}_{yyyymmdd}.{tex,pdf}
```

**Selection heuristics that matter more than the model:**
- Backend/infra JD → lead with EverWell, then Linx, then Thunderbolts.
- AI/ML JD → lead with Linx, foreground the offline/deterministic-safety layer, mention the hackathon placement.
- Full-stack/product JD → lead with Thunderbolts (Stripe, RLS, concurrency is real production thinking).
- Frontend JD → lead with Resource Hub and the Startup Club platform work.
- Large-company JD (Amazon/Boeing/T-Mobile) → keep MechXcel's scale and ops bullets; they map to Ownership/Deliver Results in a way pure code bullets don't.
- Always keep exactly one bullet with a hard number in the top third.

**Rephrasing guardrails — non-negotiable:**
1. No new employers, titles, dates, technologies, or metrics. The rewriter may only re-angle text that already exists in the bank.
2. A post-generation check diffs every claim in the output against the bank; any unmatched proper noun or numeral fails the build and falls back to the verbatim bullet.
3. Every generated resume is diffed against the base and the diff is shown in the UI drawer. You approve before it counts as "ready."
4. If a JD requires something you don't have (Go, Kubernetes, C++), the system **puts it in Notes as a gap**, never in Skills.

**Keyword coverage report**: after generation, list JD keywords present vs. missing in the resume. Missing ones flow straight into Notes. This is the whole ATS optimization story — no keyword stuffing, just honest coverage measurement.

**Cost control**: rephrasing is one LLM call per posting (~2k in / 800 out). At 40 new Seattle postings a day that's trivial on a free tier. Cache by `(bullet_id, jd_cluster)` so the 15th backend internship reuses the 1st one's phrasing. Only regenerate on demand for postings you actually mark `Reviewing`.

---

## 11. The Notes engine

The differentiator. For each posting, produce three short blocks:

**① Gaps** — requirements in the JD with no evidence in your experience bank.
> `Missing: Go, Kubernetes, distributed systems coursework. You have the concurrency instinct (Thunderbolts lane-booking rule) but nothing distributed on paper.`

**② Do this** — the smallest concrete action that closes the biggest gap, ranked by effort-to-impact.
> `Highest leverage: add a queue-backed worker to EverWell (Redis + BullMQ, one weekend) so you have a real async-processing story. Second: AWS Cloud Practitioner or a deployed service on ECS — every Seattle backend JD asks for cloud and your resume has none.`

**③ Standout signal** — what would make *this specific* reviewer stop.
> `Amazon screens on Leadership Principles. Your MechXcel $20k fundraise + 120 students is a stronger Ownership story than most applicants' internships. Lead the behavioral prep with it. For the resume, keep the number in the top third.`

**Implementation.** Deterministic layer first, LLM second:
- Diff `jd.keywords` against `experience_bank.all_tags` → gap list. No model needed.
- Map gaps through a static `remediation.yaml` (`kubernetes → "containerize one existing project and deploy to a managed k8s cluster; 1 weekend"`) so advice is consistent and doesn't drift.
- One LLM call composes the three blocks from the gap list + JD + selected bullets. Cap at 120 words total. Long notes don't get read.

**Cross-posting rollup.** The single most useful screen in the app: aggregate gaps across all open Seattle postings and rank by frequency.
> `Appears in 34 of 61 open Seattle CS internships you qualify for: AWS/cloud deployment. 22 of 61: unit testing / CI. 19 of 61: Docker.`

That list tells you what to build next far better than any individual posting does. Render it as a horizontal bar list on a `/gaps` route.

**Seed observations from the current resume** (to bootstrap `remediation.yaml`, and worth acting on regardless):
- **No cloud on the page.** AWS/Azure/GCP appears in the majority of Seattle CS internship JDs and appears zero times here. Deploying one existing project to AWS and adding a line about it is the single highest-ROI edit available.
- **No testing or CI.** Pytest/Jest + a GitHub Actions workflow on any one repo, then one bullet about it.
- **No Docker/containers**, which pairs with the cloud gap.
- **Java is listed but nothing demonstrates it.** Either build something in it or expect it to be probed in interviews.
- **Coursework line is thin for a 2028 grad.** As Algorithms, Databases, Systems Programming, Computer Networks land, add them — big-co resume screens filter on those literal words.
- **Strong and underused:** the Nemoclaw deterministic-override layer in Linx is genuine systems judgment (knowing when *not* to trust a model). Most intern resumes have nothing like it. It should lead every AI-adjacent application.
- **Strong and underused:** the Thunderbolts row-level security + booking concurrency rule. That's production reasoning at an intern level. Lead every backend application with it.

---

## 12. Data model

```sql
CREATE TABLE companies (
  slug TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  ats TEXT,                    -- greenhouse|lever|ashby|workday|smartrecruiters|workable|custom|manual
  board_token TEXT,
  workday_tenant TEXT, workday_wd INT, workday_site TEXT,
  hq TEXT, tier INT DEFAULT 2, watchlist BOOLEAN DEFAULT 0,
  poll_minutes INT DEFAULT 60,
  last_polled_at TIMESTAMP, consecutive_failures INT DEFAULT 0,
  tags JSON
);

CREATE TABLE postings (
  id TEXT PRIMARY KEY,             -- dedupe hash
  company_slug TEXT REFERENCES companies(slug),
  title TEXT NOT NULL,
  apply_url TEXT NOT NULL,
  ats_job_id TEXT,
  locations JSON,                  -- ["Seattle, WA", "Remote (US)"]
  is_seattle_metro BOOLEAN,
  is_remote_us BOOLEAN,
  term TEXT,                       -- summer-2027 | fall-2026 | off-cycle | unspecified
  description TEXT,
  posted_at TIMESTAMP,             -- company-claimed, untrusted
  first_seen_at TIMESTAMP NOT NULL,
  last_seen_at TIMESTAMP NOT NULL,
  closes_at DATE, closes_kind TEXT, closes_evidence TEXT,  -- explicit|rolling|estimated|unknown
  is_closed BOOLEAN DEFAULT 0,
  fit_score INT, fit_breakdown JSON,
  eligibility_flags JSON,
  sources JSON,                    -- [{type:"greenhouse", url:...}, {type:"github-list", ...}]
  raw JSON
);

CREATE TABLE applications (
  posting_id TEXT PRIMARY KEY REFERENCES postings(id),
  status TEXT DEFAULT 'new',
  applied_at TIMESTAMP,
  resume_tex_path TEXT, resume_pdf_path TEXT, resume_generated_at TIMESTAMP,
  resume_approved BOOLEAN DEFAULT 0,
  cover_letter_path TEXT,
  notes_json JSON,                 -- {gaps:[], actions:[], standout:""}
  user_notes TEXT,
  referral TEXT,
  next_action TEXT, next_action_due DATE
);

CREATE TABLE keyword_stats (      -- powers the /gaps rollup
  keyword TEXT, seen_count INT, covered BOOLEAN, last_seen TIMESTAMP,
  PRIMARY KEY (keyword)
);

CREATE INDEX idx_postings_seattle_new ON postings(is_seattle_metro, first_seen_at DESC);
CREATE INDEX idx_postings_open ON postings(is_closed, fit_score DESC);
```

SQLite is correct here. One file, zero ops, handles 100k rows without noticing. Move to Postgres only if you ever host it for other people.

---

## 13. UI

### Design direction

The brief is clean, simple, modern — so the discipline is in what gets left out. This is an operations table, not a marketing page. Reference points: a flight-status board and a well-built email client, not a SaaS analytics dashboard. No cards, no charts on the main view, no sidebar full of icons.

**Spend the boldness in one place: the Closes column.** Every row carries a thin horizontal runway bar showing time remaining, filling and warming as the deadline approaches. It's the only saturated color on the screen. Everything else is greyscale plus one link blue. That single device does the whole job of urgency and makes the table scannable at arm's length.

**Tokens**

```css
--paper:       #FFFFFF;   /* table background */
--surface:     #F5F6F7;   /* header row, drawer, hover */
--line:        #E3E5E8;   /* hairlines */
--ink:         #14171A;   /* primary text */
--ink-muted:   #6B747E;   /* secondary text, timestamps */
--link:        #1B4DD1;   /* the only interactive color */
--urgent-0:    #8C949E;   /* >21 days or unknown */
--urgent-1:    #C9922B;   /* 8-21 days */
--urgent-2:    #C4462F;   /* <=7 days, or rolling */
--ok:          #2E7D5B;   /* applied / offer */
radius: 4px everywhere. shadow: none, except the drawer (0 0 0 1px --line).
```

**Type**: one family — Instrument Sans (or Public Sans if you want a safer fallback), 400/500/600. `font-variant-numeric: tabular-nums` globally so the date and score columns align. 13px body in the table, 15px in the drawer, 1.5 line height. No all-caps labels, no monospace decoration, no eyebrow text.

**Density**: 40px rows, 12px horizontal cell padding, hairline row separators, sticky header. ~18 rows visible on a laptop without scrolling. Density is the feature — you're triaging 60 postings, not admiring 6.

### Layout

```
┌────────────────────────────────────────────────────────────────────────────┐
│  Internship Radar                        61 open · 12 new today · Seattle ▾ │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ 🔍 filter by company, role, or skill                                 │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│  [ All ] [ Seattle 61 ] [ New 12 ] [ Closing soon 4 ] [ Applied 9 ]  + Add │
├────────────────────────────────────────────────────────────────────────────┤
│ ROLE                        LOCATION      POSTED  CLOSES        RESUME  FIT │
├────────────────────────────────────────────────────────────────────────────┤
│ ● Remitly                   Seattle, WA      2h   ▓▓▓▓▓░░ Mar 3   PDF   87 │
│   Software Engineer Intern                        14 days        TEX       │
├────────────────────────────────────────────────────────────────────────────┤
│ ● Amazon                    Seattle, WA      5h   ▓▓▓▓▓▓▓ Rolling PDF   82 │
│   SDE Intern - Summer 2027                        apply now      TEX       │
├────────────────────────────────────────────────────────────────────────────┤
│ ○ Stripe                    Remote (US)      1d   ▓▓░░░░░ ~Apr 2  Generate 74│
│   Software Engineer, Intern                       est.                     │
└────────────────────────────────────────────────────────────────────────────┘
```

Filled dot = Seattle metro. Hollow = elsewhere. Two-line role cell (company on top in medium weight, title beneath in muted) reads faster than a separate company column and saves 140px.

### Detail drawer

Slides from the right, 520px, on row click. Sections in this order — the ones you need before deciding come first:

1. Title, company, location, apply button (primary, says `Open application`)
2. **Notes** — the three blocks, plain prose, no icons
3. **Resume** — PDF preview thumbnail, `Download .tex`, `Regenerate`, `Approve`, and the diff-vs-base toggle
4. **Keyword coverage** — two short lists, present and missing
5. **Fit breakdown** — the five components with their weights
6. Full JD, collapsed by default
7. Your own notes textarea + status selector

### Interactions

- `j`/`k` move rows, `Enter` opens the drawer, `a` marks applied, `x` skips, `/` focuses search. Triaging 60 postings with a mouse is miserable.
- Optimistic status updates; no save button.
- New rows arriving while you're looking: a quiet `3 new postings` pill at the top of the table that you click to merge them in. Never reorder under the cursor.
- Empty state on the Seattle tab: `No open Seattle postings match these filters. 14 are outside the metro.` with a button to widen. Empty states point somewhere.
- Closed postings: struck through, muted, hidden by default behind `Show closed`.

---

## 14. Stack and repo layout

**Backend**: Python 3.11 · `httpx` (async, connection pooling) · `pydantic` (schema) · `rapidfuzz` (dedupe) · `apscheduler` or plain cron · `jinja2` + `tectonic` (LaTeX) · SQLite via `sqlite3`/SQLModel.

**Frontend**: Next.js (App Router) · TypeScript · Tailwind · TanStack Table (virtualized, handles 5k rows) · `better-sqlite3` read-only in a route handler, or a thin FastAPI layer if you'd rather keep Python-only.

**Hosting**: run it on your own machine first — a `launchd`/cron job plus `next dev` is genuinely sufficient. When you want it always-on: GitHub Actions on a 15-minute schedule for collection (free for public repos, commits the SQLite file), plus Vercel for the read-only UI. Fly.io free tier if you'd rather run one always-on container with a volume.

```
internship-radar/
├── radar/
│   ├── collectors/
│   │   ├── ats/{greenhouse,lever,ashby,workday,smartrecruiters,workable,recruitee}.py
│   │   ├── custom/{amazon,microsoft,tesla,google}.py
│   │   ├── lists/github_repos.py
│   │   └── feeds/{rss,google_pse}.py
│   ├── detect.py            # ATS auto-detection (§5.2)
│   ├── normalize.py         # canonical schema, geo, term
│   ├── filters.py           # §6
│   ├── dedupe.py            # §7
│   ├── score.py             # §15
│   ├── deadlines.py         # §9
│   ├── tailor/
│   │   ├── bank.py          # experience bank loader + validation
│   │   ├── extract.py       # JD → requirements
│   │   ├── select.py        # bullet selection
│   │   ├── rewrite.py       # LLM re-angling + guardrails
│   │   ├── verify.py        # hallucination diff check
│   │   └── render.py        # jinja → tex → pdf
│   ├── notes.py             # §11
│   ├── notify.py            # discord / ntfy / email
│   ├── db.py
│   └── run.py               # `python -m radar.run --tier 0`
├── registry/
│   ├── seattle.yaml         # Tier 0
│   ├── national.yaml
│   └── unresolved.yaml      # ATS detection failures, review weekly
├── data/
│   ├── experience.yaml      # source of truth
│   ├── remediation.yaml     # gap → suggested action
│   ├── gazetteer.yaml       # location normalization
│   └── radar.db
├── templates/resume.tex.j2
├── files/resumes/
├── web/                     # Next.js
└── config.yaml
```

**config.yaml**

```yaml
profile:
  name: "..."
  graduation: 2028-06
  work_authorization: us-citizen        # drives eligibility flags
  target_terms: [summer-2027, fall-2026, off-cycle, unspecified]
  home_metro: seattle
  max_commute_miles: 60

scoring:
  weights: {location: 30, term: 20, stack_overlap: 25, level_fit: 15, company_tier: 10}
  alert_threshold: 60

polling:
  tier0_minutes: 15
  tier1_minutes: 60
  tier2_minutes: 30
  tier3_hours: 12

notify:
  discord_webhook: env:DISCORD_WEBHOOK
  ntfy_topic: env:NTFY_TOPIC
  digest_hour: 7

llm:
  provider: gemini            # free tier
  model: gemini-2.0-flash
  max_calls_per_day: 200
```

---

## 15. Fit score

Explainable, five components, no ML:

| Component | Weight | Rule |
|---|---|---|
| Location | 30 | Seattle metro 30 · Remote-US 22 · WA 20 · elsewhere 5 |
| Term | 20 | Exact target term 20 · off-cycle 14 · unspecified 10 · wrong term 0 |
| Stack overlap | 25 | `|jd_stack ∩ your_stack| / |jd_stack|` × 25, with per-tech weights |
| Level fit | 15 | Full 15 · minor mismatch (prefers rising senior) 8 · hard mismatch (PhD) 0 |
| Company tier | 10 | Watchlist 10 · known-good 7 · unknown 5 |

Show the breakdown on hover. A score you can't interrogate is a score you'll stop trusting by week two.

---

## 16. Build order

**Phase 1 — see everything (weekend 1).** Greenhouse + Lever + Ashby collectors, 40-company hardcoded Seattle registry, filters, dedupe, SQLite, a `print()` table. No UI. Confirm you're catching real postings.

**Phase 2 — never miss one (weekend 2).** ATS auto-detection, registry grown to 200+, GitHub list collectors, 15-minute cron, Discord alerts. **This is the phase that satisfies the actual requirement.** Everything after is convenience.

**Phase 3 — the table (weekend 3).** Next.js UI, columns, filters, keyboard nav, status tracking, drawer.

**Phase 4 — resume tailoring (weekend 4).** Experience bank, JD extraction, selection, LaTeX render, guardrails, diff view.

**Phase 5 — notes (weekend 5).** Gap diff, remediation map, LLM composition, `/gaps` rollup.

**Phase 6 — coverage grind (ongoing).** Workday collectors for Boeing/T-Mobile/Costco/Nordstrom, Amazon + Microsoft custom collectors, Google PSE sweep, registry growth from VC portfolios. Weekly 20-minute ritual: review `unresolved.yaml`, add 10 companies, check the rejection log for false negatives.

Ship Phase 2 before touching Phase 3. A working alert pipeline with an ugly terminal output is worth more in September than a beautiful table in November.

---

## 17. Operational care

- **Be a polite client.** Descriptive User-Agent with a contact address, 2–5 req/s cap per host, conditional requests, exponential backoff on 429/5xx, respect `Retry-After`. These are public endpoints; the way to keep them public is not to hammer them.
- **Use official APIs, skip the ones that forbid you.** LinkedIn/Indeed/Glassdoor/Handshake stay manual-add. Their data is downstream of the ATS endpoints you're already hitting.
- **Circuit-break dead collectors.** Three consecutive failures → back off to daily, surface in an admin list, keep the pipeline running.
- **Log rejections.** Every filtered-out posting with its reason, in a rotating file. Once a week, grep for company names you recognize. That's how you find the filter bug that's been silently dropping "Technical Intern - Software" for a month.
- **Snapshot descriptions.** Companies edit postings after publishing. Keep the first-seen text; it's what your resume was tailored against.
- **Never auto-submit, never auto-create accounts, never store passwords in the repo.** Secrets in env vars only.

---

## 18. Success metrics

Track these in the app; they tell you whether it's working:

- **Time-to-notification**: median minutes between a posting's true publish time and your alert. Target under 30.
- **Coverage check**: once a week, manually search LinkedIn for "software intern Seattle," take the first 20 results, and count how many were already in your DB. Target 90%+. Every miss becomes a registry entry or a filter fix.
- **Applications per week**, and time from `New` to `Applied` for Seattle rows. Target under 24 hours.
- **Response rate by resume version**, once you have volume. This is the only real feedback loop on whether the tailoring helps.

---

## Appendix A — quick endpoint reference

```bash
# Is this company on Greenhouse?
curl -s "https://boards-api.greenhouse.io/v1/boards/remitly/jobs?content=true" | jq '.jobs | length'

# Lever
curl -s "https://api.lever.co/v0/postings/COMPANY?mode=json" | jq '.[0]'

# Ashby
curl -s "https://api.ashbyhq.com/posting-api/job-board/COMPANY" | jq '.jobs[0]'

# Workday (tenant/site from the careers URL)
curl -s -X POST "https://TENANT.wd1.myworkdayjobs.com/wday/cxs/TENANT/SITE/jobs" \
  -H "Content-Type: application/json" \
  -d '{"appliedFacets":{},"limit":20,"offset":0,"searchText":"intern"}' | jq '.total'

# Community list, machine-readable
curl -s "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/.github/scripts/listings.json" | jq 'length'
```

## Appendix B — first ten things to do

1. `mkdir internship-radar && git init`
2. Write `data/experience.yaml` from the current resume (it's already drafted in §10.1 — paste it in).
3. Write `registry/seattle.yaml` with 40 companies you'd actually work at.
4. Build the Greenhouse collector. It's ~60 lines and will immediately return real Seattle postings.
5. Add Lever and Ashby. Same shape.
6. Add filters + dedupe, write to SQLite.
7. Add the ATS detector and run it over 200 more Seattle company names.
8. Add the Discord webhook and a 15-minute cron.
9. Apply to whatever it surfaces in the first 48 hours. The tool has already paid for itself.
10. Then build the table.
