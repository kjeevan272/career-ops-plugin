---
name: full-scan
description: "Run the job-board scraper and the company career-page crawler together in one command, then regenerate the single pipeline dashboard with combined results. Use when someone says 'full scan', 'scan everything', 'run all scrapers', or 'find every new role'."
argument-hint: "[optional: 'quick' or 'full' to control scrape_jobs.py's mode]"
user-invocable: true
allowed-tools:
  - Bash
  - Read
---

# Full Scan: Job Boards + Company Career Pages

Runs both scraper systems in parallel (they're kept as separate processes —
see the "Why not one script" note below) and produces one merged dashboard.

## Step 1: Run It

```bash
cd /Users/user/career-ops-plugin
source .venv/bin/activate
python scripts/full_scan.py            # scrape_jobs.py daily mode + company crawl
python scripts/full_scan.py --quick    # scrape_jobs.py --quick + company crawl
python scripts/full_scan.py --full     # scrape_jobs.py --full + company crawl
deactivate
```

This launches `scrape_jobs.py` and `scrape_company_careers.py` at the same
time, waits for both, merges their "what's new" state, and runs
`generate_dashboard.py` automatically — `pipeline-dashboard.html` (repo root)
will show new roles from both sources.

Expect this to take as long as the slower of the two (typically the company
crawl, ~3-10 min) — tell the user up front if they asked for a "quick" scan,
since `--quick` only shortens the job-board half.

## Step 2: Report Results

Read `data/pipeline.md`, summarise new roles same as the `scrape-jobs`
skill does, and note the source split (job-board vs `company-crawl`).

## Why not one script?

`scrape_jobs.py` (threaded HTTP requests, seconds-to-minutes) and
`scrape_company_careers.py` (asyncio + a real Chromium browser, minutes) use
incompatible concurrency models and very different runtimes. Merging them
into one process would make every run as slow as the crawler, require
Playwright even for a quick LinkedIn check, and let one hung company page
stall the whole run. Keeping them as separate processes run in parallel gets
the same "one command, one dashboard" result without that coupling — see
the module docstrings in both scripts for the full reasoning.
