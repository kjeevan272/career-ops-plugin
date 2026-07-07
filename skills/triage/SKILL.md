---
name: triage
description: "Quick-score your pipeline of scan results. Ranks every role in your pipeline by fit and recommends which ones deserve a full evaluation. Use when someone says 'triage my pipeline', 'which scanned jobs should I apply to', 'rank my pipeline', or 'process my scan results'."
argument-hint: "['all' or company name to triage]"
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Glob
  - WebFetch
---

# Triage Pipeline

Quick-score scan results to find the best candidates for full evaluation.

## Step 0: Load Context

1. Read `data/profile.yml`
2. Read `data/pipeline.md` - the queue from scan results
3. Read `data/applications.md` - exclude already-tracked roles

If pipeline is empty:
> "Your pipeline is empty. Scan some companies first:
> say 'scan {company name}' or 'scan all' for your watchlist."

## Step 1: Determine Scope

- **No argument / "all":** Process every "New" entry in pipeline
- **Company name:** Process only that company's entries
- **Number limit:** "triage top 10" -> process first 10 by relevance

## Step 2: Quick-Score Each Role

For each pipeline entry with status "New":

1. Fetch the full JD if only a URL is stored (use WebFetch)
2. If WebFetch unavailable, score based on title + location only (partial)
3. Quick-score on 3 dimensions:
   - **Title fit** (0-5): How well does the title match target roles?
   - **Requirements fit** (0-5): If JD available, how many requirements match?
   - **Logistics fit** (0-5): Location, seniority, compensation range match?
4. Average = quick score out of 5.0

This is FAST scoring. No blocks A-F. No STAR stories. Just a fit check.

## Step 3: Rank & Recommend

Sort by quick score, descending.

```
## Pipeline Triage: {date}

Scored **{n}** roles from your pipeline.

### Recommended for Full Evaluation (score >= 3.5)

| # | Company | Role | Quick Score | Why |
|---|---|---|---|---|
| 1 | {company} | {title} | {score}/5 | {one-line reason} |
| 2 | ... | ... | ... | ... |

### Maybe (score 2.5-3.4)

| # | Company | Role | Quick Score | Why |
|---|---|---|---|---|
| ... | | | | |

### Skip (score < 2.5)

| # | Company | Role | Quick Score | Why |
|---|---|---|---|---|
| ... | | | | {why it doesn't fit} |
```

## Step 4: Update Pipeline

Update `data/pipeline.md`:
- Add quick score to each entry
- Change status from "New" to "Triaged"

## Step 5: Next Steps

> "Top {n} roles are worth a full evaluation.
>
> Want me to:
> - **Evaluate the top pick?** Say 'evaluate {company} {role}'
> - **Evaluate all recommended?** I'll work through them one by one
> - **Scan more companies?** Say 'scan {company}'"

If user says "evaluate all recommended," process each sequentially
using the evaluate skill, pausing between each for user confirmation.
