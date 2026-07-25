---
name: scrape-jobs
description: "Scrape LinkedIn, Indeed, ATS boards, and Germany-specific job sources for matching Data Engineer / Analytics Engineer roles across your target countries. Scores results against profile, deduplicates against applications.md and pipeline.md, appends new matches to data/pipeline.md, and refreshes the dashboard. Use when someone says 'scrape jobs', 'find new roles', 'search jobs', 'scan job boards', or 'find listings'."
argument-hint: "[optional: 'quick' for a fast LinkedIn-only check, 'full' for full multi-source coverage]"
user-invocable: true
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# Scrape Jobs from Job Boards

Run the Python scraper (`scripts/scrape_jobs.py`) to find new matching roles,
then refresh the dashboard so results are viewable immediately.

## Step 1: Pick a Mode

`scrape_jobs.py` has three modes — pick based on what the user asked for:

| User says | Mode | What runs |
|---|---|---|
| "scrape jobs", "find new roles" (default) | daily | LinkedIn across the EU + ATS boards (Greenhouse/Ashby/Lever) + Bundesagentur + Arbeitnow + StepStone RSS |
| "quick scrape", "quick check" | `--quick` | LinkedIn/EU only, single search term, English-language descriptions only — fastest option |
| "full scrape", "deep scrape", "check everything" | `--full` | Everything in daily mode **plus** Indeed/Google/Glassdoor per target country (slowest, most thorough) |

## Step 2: Run the Scraper

```bash
cd /Users/user/career-ops-plugin
source .venv/bin/activate
python scripts/scrape_jobs.py            # daily mode
python scripts/scrape_jobs.py --quick    # fast LinkedIn-only check
python scripts/scrape_jobs.py --full     # full multi-source coverage
deactivate
```

If a role keyword override was requested, note that the scraper's search
terms are driven by `data/profile.yml`'s `target` block (primary/secondary
roles) — editing that file changes future runs; there's no per-invocation
keyword flag today.

## Step 3: Refresh the Dashboard

Always regenerate the dashboard right after a scrape so results are
immediately viewable — don't leave this as a separate manual step:

```bash
python scripts/generate_dashboard.py
```

This defaults to showing only the newest run's new roles. Use
`--all` (full historical pipeline), `--since=YYYY-MM-DD`, or
`--country=Germany` (writes a filtered view — pair with `--output=` to avoid
overwriting the main dashboard) if the user wants a different slice.

## Step 4: Report Results

Read `data/pipeline.md` and summarise:

- How many new jobs were found
- Top 3 by score with company, title, location, URL
- Any patterns (e.g. "8 of 12 are remote", "most are on LinkedIn")

## Step 5: Offer Next Steps

> "Want me to:
> - **Evaluate** a specific role? Paste the job description or say 'evaluate #1'
> - **Triage** the full pipeline? Say 'triage my pipeline'
> - **Run again** in a different mode? Say 'quick scrape' or 'full scrape'"
