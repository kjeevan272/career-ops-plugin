---
name: track
description: "View and update your job application tracker. See all applications, filter by status, update progress, and get statistics on your search. Use when someone says 'show my applications', 'how is my job search going', 'update status', or 'tracker'."
argument-hint: "[status filter, company name, or 'update Company to Status']"
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Glob
---

# Application Tracker

View and manage your job applications in one place.

## Step 0: Load Tracker

Read `data/applications.md`. If it doesn't exist, create it with the header:

```markdown
# Job Applications

| Date Added | Date Applied | Company | Role | Score | Status | Evaluation | Notes |
|---|---|---|---|---|---|---|---|
```

Then tell the user:
> "Your tracker is empty. Evaluate a job posting to get started, or
> paste a JD and I'll score it for you."

## Step 1: Parse User Intent

- **No argument / "show tracker" / "my applications":** Display full table + stats
- **Status filter ("show applied" / "what's in interview"):** Filter by status
- **Company filter ("show Stripe"):** Filter by company name
- **Update ("update Acme PM to Interview"):** Change status of matching row
- **Stats ("how's my search going" / "search stats"):** Show summary statistics
- **Delete ("remove the Acme entry"):** Confirm, then remove row

## Step 2: Display

### Full View

Show the table as-is from applications.md, then show stats below it.

### Filtered View

Show only matching rows, then summary:
> "Showing {n} applications with status '{status}'."

### Update Flow

1. Find the matching row (by company + role, fuzzy match OK)
2. Show current status and proposed new status
3. Ask for confirmation:
   > "Update **{Company} - {Role}** from **{old status}** to **{new status}**?"
4. On confirmation, update the row
5. If transitioning to "Applied", set Date Applied to today
6. If transitioning to "Accepted", congratulate them!

Validate transitions against references/states.md. If invalid:
> "Can't move from {old} to {new}. Valid next steps: {list}."

## Step 3: Statistics

```
## Your Job Search Dashboard

| Metric | Count |
|---|---|
| Total evaluated | {n} |
| Resumes tailored | {n with status >= Resume Ready} |
| Applied | {n} |
| Response rate | {responses / applied}% |
| Interviews | {n} |
| Offers | {n} |
| Average score (applied) | {avg}/5.0 |
| Active (not resolved) | {n non-terminal} |

**Top scoring opportunities:**
1. {Company} - {Role} ({score}/5.0) - {status}
2. ...
3. ...

**Needs attention (applied but no response > 7 days):**
- {Company} - {Role} - applied {date}
```

If there are evaluations without resumes tailored:
> "You have {n} evaluations scoring 3.5+ without a tailored resume.
> Want me to create one? Say 'tailor my resume for {top company}'."

## Step 4: Suggest Next Actions

Based on current state:

- Mostly "Evaluated": "You've got evaluations but haven't applied to many.
  Want me to tailor resumes for your top-scored roles?"
- Several "Applied" with no updates: "Time for follow-ups? I can draft
  outreach messages to check in on your applications."
- Has "Interview": "Great, you have interviews! Want me to research
  {company} to help you prepare?"
- Everything terminal: "Your current batch is wrapped up. Ready to scan
  for new opportunities?"
