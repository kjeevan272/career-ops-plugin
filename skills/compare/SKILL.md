---
name: compare
description: "Compare multiple job opportunities side by side. See scores, compensation, pros/cons, and a recommendation. Use when someone says 'compare my options', 'which job should I take', 'rank my opportunities', or 'compare these roles'."
argument-hint: "[company names to compare, or 'my top options']"
user-invocable: true
allowed-tools:
  - Read
  - Glob
---

# Compare Opportunities

Side-by-side comparison of evaluated job opportunities.

## Step 0: Load Evaluations

Read all files in `data/evaluations/`. Parse the scores, archetype, company,
role, location, and compensation from each.

## Step 1: Select Opportunities

- If user specified companies/roles: match to evaluations (fuzzy OK)
- If "compare my top options" or no argument: select top 3-5 by score
  with non-terminal status (Evaluated, Resume Ready, Applied, Interview)
- If fewer than 2 evaluations exist:
  > "You need at least 2 evaluated jobs to compare. Evaluate more
  > postings first by pasting a JD."

## Step 2: Comparison Table

```
## Opportunity Comparison

| Dimension | {Company A: Role} | {Company B: Role} | {Company C: Role} |
|---|---|---|---|
| **Score** | {X.X}/5.0 | {X.X}/5.0 | {X.X}/5.0 |
| **Archetype** | {type} | {type} | {type} |
| **Seniority** | {level} | {level} | {level} |
| **Location** | {loc} | {loc} | {loc} |
| **Compensation** | {range or "Not disclosed"} | {range} | {range} |
| **Strongest match** | {top requirement match} | ... | ... |
| **Biggest gap** | {main risk} | ... | ... |
| **Status** | {current status} | ... | ... |
```

## Step 3: Pros and Cons

For each opportunity, list 3 specific pros and 2 specific cons.
These must reference actual evaluation data, not generic statements.

```
### {Company A} - {Role}
**Pros:**
- {specific strength from Block B match}
- {compensation/location advantage}
- {career trajectory fit}

**Cons:**
- {specific gap or risk}
- {concern from evaluation}
```

## Step 4: Recommendation

```
## My Recommendation

**Best overall match:** {Company - Role} ({score}/5.0)
{2-3 sentences: why this one stands out, what makes it the strongest fit}

**Best growth opportunity:** {Company - Role}
{1-2 sentences: highest upside if you can close the gaps}

**Safest option:** {Company - Role}
{1-2 sentences: most likely to result in an offer}
```

If scores are very close (within 0.3), say so:
> "These are genuinely close. The tiebreaker is which company and role
> excites you most. Numbers can't measure that."

## Step 5: Next Steps

> "Want me to:
> - **Tailor a resume** for your top pick? Say 'tailor my resume for {company}'
> - **Research** any of these companies deeper? Say 'research {company}'
> - **Evaluate more** options? Paste another job posting"
