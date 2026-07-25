# career-ops

A Claude Cowork plugin that turns your job search into a system. Evaluate job postings, generate ATS-optimized resumes, scan career portals, track applications, and more.

Works for any industry: tech, healthcare, finance, legal, creative, trades, and everything in between.


## Run Locally

This is a plain local folder (no git) — open it directly with Claude Code from
VS Code or the desktop app, or launch it from the terminal:

```bash
# From the terminal (CLI)
cd /Users/user/career-ops-plugin
claude --plugin-dir .

# VS Code — open this folder, then use the Claude Code extension as normal
# Desktop app — open this folder as your working directory
```

Once Claude Code is running in this folder, just talk to it — see **Quick
Start** and **Skills** below. No install step is needed since the plugin
files (`skills/`, `commands/`, `agents/`) already live in this folder.

### Python scripts (job scraper, company crawler & dashboards)

Everything here is plain Python — no Claude-specific tooling required, run
it directly from your own terminal. (You can also just ask Claude Code to
run these for you — say "run the job scraper and dashboard" and it will use
`.venv` automatically.)

**One-time setup:**

```bash
cd /Users/user/career-ops-plugin
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

**Scraping** (activate the venv first — `source .venv/bin/activate`):

```bash
# Job-board scraper only: LinkedIn, Indeed, Greenhouse/Ashby/Lever,
# Arbeitsagentur, Arbeitnow, StepStone — appends results to data/pipeline.md
python scripts/scrape_jobs.py            # daily mode (LinkedIn/EU + ATS boards + DE sources)
python scripts/scrape_jobs.py --quick    # fast LinkedIn-only, English-descriptions-only check
python scripts/scrape_jobs.py --full     # daily mode + Indeed/Google/Glassdoor per target country

# Company career-page crawler only: visits ~513 company career pages directly
# with a headless browser (Playwright), rather than searching job boards.
# Matches Data Engineer / Data Analyst / Analytics / Data Scientist / BI /
# Platform / Cloud Engineer roles. Pulls jobs via each ATS's public API
# directly (Greenhouse/Ashby/Lever/Personio/Workable/BambooHR) where
# possible, falling back to a rendered page otherwise. Results are scored/
# dedup'd/English-filtered the same way scrape_jobs.py does them and
# appended to data/pipeline.md (tagged source: company-crawl) — no separate
# dashboard needed. Kept as its own process rather than merged into
# scrape_jobs.py: incompatible concurrency models (asyncio/Playwright vs
# threaded requests) and a much heavier Chromium dependency.
python scripts/scrape_company_careers.py
python scripts/scrape_company_careers.py <input.json> <output.json>   # custom company list/output

# Both together in parallel, then auto-regenerate the dashboard once both
# finish (recommended — same result as running the two above separately,
# without waiting for one to finish before starting the other)
python scripts/full_scan.py
python scripts/full_scan.py --quick    # scrape_jobs.py --quick + company crawl
python scripts/full_scan.py --full     # scrape_jobs.py --full + company crawl
```

Wired to skills: `scrape-jobs` (job-board only), `scan-companies` (crawler
only), `full-scan` (both together) — say "scrape jobs", "scan companies", or
"full scan".

**Dashboard** (`data/pipeline-dashboard.html` — defaults to showing only the
newest scrape run's new roles, sorted by date descending):

```bash
python scripts/generate_dashboard.py
python scripts/generate_dashboard.py --all                # full historical pipeline
python scripts/generate_dashboard.py --since=2026-07-01    # jobs found on/after a date
python scripts/generate_dashboard.py --country=Germany --output=data/pipeline-dashboard-germany.html

open data/pipeline-dashboard.html   # macOS — opens in your default browser
```

**Other standalone scripts:**

```bash
python scripts/generate_evaluate_dashboard.py   # skill-gap dashboard from data/evaluate-jobs.json
                                                 # (populated by the evaluate skill) — say
                                                 # "refresh the evaluate dashboard" to run this via Claude
python scripts/rebuild_cv.py                    # tight 2-page CV from data/resume.md
python scripts/nl_sponsors.py --refresh         # force-refresh the NL sponsor cache
```

```bash
deactivate
```

`scripts/_archive/` holds one-off, hardcoded CV-editing scripts from past
tailoring sessions (`make_*_cv.py`) — superseded by the `tailor-resume`
skill, kept around only for reference.

## Quick Start

1. Install the plugin
2. Say **"set up my profile"** and paste your resume
3. Paste a job posting and say **"evaluate this"**
4. Say **"tailor my resume"** for your top matches
5. Say **"help"** anytime to see what's available

## Skills

| Skill | What It Does | Try Saying |
|---|---|---|
| **evaluate** | Score a job posting A-F with detailed analysis | "Evaluate this job posting" |
| **tailor-resume** | ATS-optimized resume for a specific role | "Tailor my resume for Acme" |
| **scan** | Search company career portals (WebSearch, ad hoc) | "Scan Stripe for openings" |
| **scrape-jobs** | Run the job-board scraper (LinkedIn/Indeed/ATS/DE sources) | "Scrape jobs" / "quick scrape" / "full scrape" |
| **scan-companies** | Crawl the ~500-company career-page watchlist directly | "Scan companies" |
| **full-scan** | Run both scrapers in parallel, one combined dashboard | "Full scan" / "scan everything" |
| **triage** | Quick-score pipeline from scan results | "Triage my pipeline" |
| **track** | Application tracker with stats | "Show my applications" |
| **apply** | Fill out application forms | "Help me with this application" |
| **research** | Company intelligence brief | "Research this company" |
| **outreach** | Draft LinkedIn/email messages | "Draft outreach to the hiring manager" |
| **compare** | Side-by-side opportunity comparison | "Compare my top options" |

## How Evaluation Works

Paste a job posting (text or URL) and get a full A-F assessment:

- **A. Executive Summary** - Archetype, seniority, one-line verdict
- **B. Background Match** - Every JD requirement mapped to your experience
- **C. Positioning Strategy** - How to present yourself for this specific role
- **D. Compensation & Market** - Salary data and alignment check
- **E. Tailoring Plan** - Specific resume and LinkedIn changes to make
- **F. Interview Prep** - STAR stories mapped to JD requirements

Score from 1.0 to 5.0. Honest, not inflated.

## Industry Support

15 archetypes with specialized evaluation lenses:

Technology, Finance, Healthcare, Legal, Creative/Marketing, Operations,
Sales/BD, Education, Executive, Trades, Customer Success, People/HR,
Government/Nonprofit, Scientific/R&D, Non-Software Engineering

Each archetype adjusts scoring weights and evaluation language for that industry.

## Privacy

Your data stays local. This project runs entirely from this local folder with
no git repository — the `data/` directory (profile, applications, resumes,
cover letters, job pipeline) never leaves your machine. Nothing is sent to
external services beyond what Claude uses to help you (web searches for
salary data, ATS API calls for job scanning).

## License

MIT. See [ATTRIBUTION.md](ATTRIBUTION.md) for credits.
