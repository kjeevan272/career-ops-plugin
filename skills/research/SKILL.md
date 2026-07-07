---
name: research
description: "Research a company before applying or interviewing. Get an intelligence brief with culture, financials, recent news, team structure, key contacts, and smart interview questions. Use when someone says 'research this company', 'tell me about', 'what do you know about', or 'prep me for my interview at'."
argument-hint: "<company name>"
user-invocable: true
allowed-tools:
  - Read
  - Write
  - WebSearch
  - WebFetch
  - Glob
---

# Company Research

Build an intelligence brief on a target company.

## Step 1: Gather Data

Use WebSearch to find:

1. **Company basics:** What they do, size, founded, HQ, funding/revenue
2. **Recent news (last 6 months):** Product launches, layoffs, acquisitions,
   leadership changes, funding rounds
3. **Culture signals:** Glassdoor rating + recurring themes, any "best places
   to work" lists or notable controversies
4. **Team/department:** Who leads the department you'd join? Likely hiring
   manager? Team size?
5. **Tech/tools/methodology:** What does this team use? (Check job postings,
   tech blog, team member LinkedIn profiles via web search)

If WebSearch is unavailable:
> "I can share what I know about {company}, but for the latest info
> (recent news, Glassdoor reviews, team changes), enable web search
> in your settings. Here's what I can tell you from general knowledge:"

Then provide what you know, clearly labeled as potentially outdated.

## Step 2: Find Contacts

Search for likely hiring contacts:
- **Hiring manager** (head of the relevant department)
- **Recruiter** (search "{company} recruiter {department}")
- **Team members** (potential peers for informational outreach)

For each contact found: Name, Title, and where you found them.

Note: Do NOT scrape LinkedIn profiles directly. Use web search results
and public company pages only.

## Step 3: Check for Existing Evaluation

Read `data/evaluations/` for any evaluation at this company. If found,
reference it to add context to the brief.

## Step 4: Output

```
## Company Brief: {Company Name}

### Overview
| Field | Detail |
|---|---|
| **Industry** | {industry} |
| **Size** | {employee count range} |
| **Founded** | {year} |
| **HQ** | {location} |
| **Revenue/Funding** | {if available} |
| **Website** | {URL} |

### Recent News (Last 6 Months)
- {headline} ({source}, {date})
- ...
(If no news found: "No major recent news found.")

### Culture Snapshot
**Glassdoor:** {rating}/5 ({review count} reviews)
**Positive themes:** {what employees like}
**Negative themes:** {common complaints}
**Work style:** {remote/hybrid/in-office, hours culture}

### Key Contacts
| Name | Title | Source |
|---|---|---|
| {name} | {title} | {where found} |

### Interview Intelligence
- **Company values/mission:** {what they emphasize}
- **Current priorities:** {what they're working on now}
- **Smart questions to ask:**
  1. {question based on recent news or strategy}
  2. {question about team/culture}
  3. {question about role's impact}
- **Topics to handle carefully:** {any sensitive items}
```

## Step 5: Save

Write to `data/research/{company-slug}.md`.

> "Research saved. You can reference it anytime.
>
> Want me to:
> - **Draft outreach** to one of these contacts?
> - **Evaluate a role** at this company? Paste the job posting.
> - **Prepare interview stories** specific to this company?"
