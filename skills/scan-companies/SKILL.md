---
name: scan-companies
description: "Crawl a fixed watchlist of ~500 company career pages directly (Playwright + ATS APIs for Greenhouse/Ashby/Lever/Personio/Workable/BambooHR), rather than searching job boards. Matches Data Engineer / Data Analyst / Analytics / Data Scientist / BI / Platform / Cloud Engineer roles. Use when someone says 'scan companies', 'crawl career pages', 'check all company career pages', or 'run the company crawler'."
argument-hint: "[optional: path to a different company list JSON]"
user-invocable: true
allowed-tools:
  - Bash
  - Read
  - Glob
---

# Scan Company Career Pages Directly

This is a different tool from `scrape-jobs`: instead of searching job
boards, it visits each company's own career page (`data/company_career_pages.json`,
~500 companies) with a headless browser, using each ATS's public API
directly where possible for accurate apply links. Kept as a separate script
from `scrape_jobs.py` deliberately (different concurrency model, heavier
Chromium dependency) — see `full-scan` skill to run both together.

## Step 1: One-Time Setup Check

```bash
cd /Users/user/career-ops-plugin
source .venv/bin/activate
playwright install chromium   # only needed once
```

## Step 2: Run the Crawler

```bash
python scripts/scrape_company_careers.py
deactivate
```

Or point it at a different company list / output file:

```bash
python scripts/scrape_company_careers.py <input.json> <output.json>
```

Matches are scored, dedup'd, and English-filtered the same way
`scrape_jobs.py` does them, then appended to `data/pipeline.md` (tagged
`source: company-crawl`) — no separate dedup step needed, and no separate
dashboard. Raw output is also saved to `data/scraped_company_jobs.json` for
debugging.

## Step 3: Refresh the Dashboard

```bash
python scripts/generate_dashboard.py
```

Results show up in `pipeline-dashboard.html` (repo root) alongside job-board
matches — filter by `Source: company-crawl` to see just this crawler's hits.

## Step 4: Report & Offer Next Steps

Summarise new matches (company, title, link), then:

> "Want me to:
> - **Evaluate** one of these? Paste the job description or say 'evaluate #1'
> - Run `scrape-jobs` too, to cover LinkedIn/Indeed/board sources this crawler doesn't touch? Or say 'full scan' to run both at once."
