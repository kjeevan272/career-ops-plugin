---
name: quick-eval
description: "Quick job evaluation. Paste a JD and get a score plus one-paragraph summary. Faster than a full evaluate. Use when someone says 'quick eval', 'quick score', or 'just give me a number'."
model: haiku
argument-hint: "<paste JD or URL>"
user-invocable: true
allowed-tools:
  - Read
  - WebFetch
---

# Quick Evaluation

Fast, lightweight version of evaluate. Score + one paragraph. No blocks A-F.
No file saved. No tracker update. Just a quick read.

## Step 0: Load Profile

Read `data/profile.yml`. If missing:
> "Run setup first so I know what to score against."

## Step 1: Parse JD

Accept pasted text, URL (use WebFetch), or file path.
Extract: title, company, location, key requirements, seniority signals.

## Step 2: Quick Score

Calculate score (1.0-5.0) based on:
- Hard requirement coverage vs. profile skills and experience (50%)
- Seniority alignment (25%)
- Domain/industry match (25%)

Apply PASS/FAIL credential rules if Healthcare, Legal, Trades, or
Non-Software Engineering archetype detected.

## Step 3: Output

```
**{Score}/5.0** - {Company}: {Role}

{One paragraph: honest assessment. What matches, what doesn't, and
whether it's worth a full evaluation. Be specific, not generic.}

Want the full A-F analysis? Say "evaluate this" and I'll run the complete assessment.
```

No file saved. No tracker update. This is a triage tool.
