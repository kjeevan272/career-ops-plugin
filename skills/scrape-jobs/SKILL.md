---
name: scrape-jobs
description: "Scrape LinkedIn and Indeed for matching Data Engineer / Analytics Engineer roles in Germany. Scores results against profile, deduplicates against applications.md and pipeline.md, and appends new matches to data/pipeline.md. Use when someone says 'scrape jobs', 'find new roles', 'search jobs', 'scan job boards', or 'find listings'."
argument-hint: "[optional: role keyword override, e.g. 'data architect' or 'principal engineer']"
user-invocable: true
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# Scrape Jobs from LinkedIn & Indeed

Run the Python scraper to find new matching roles in Germany.

## Step 1: Run the Scraper

```bash
cd C:\Users\91973\career-ops-plugin && python scripts/scrape_jobs.py
```

If the user provided a role keyword override, note it — the scraper uses
profile.yml targets by default. Custom keywords require editing the
search_terms list in the script or passing args (future enhancement).

## Step 2: Report Results

After the script completes, read `data/pipeline.md` and summarise:

- How many new jobs were found
- Top 3 by score with company, title, location, URL
- Any patterns (e.g. "8 of 12 are remote", "most are on LinkedIn")

## Step 3: Offer Next Steps

> "Want me to:
> - **Evaluate** a specific role? Paste the job description or say 'evaluate #1'
> - **Triage** the full pipeline? Say 'triage my pipeline'
> - **Run again** with a different keyword? Say 'scrape jobs: data architect'"
