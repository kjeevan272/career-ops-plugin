---
name: help
description: "See all available career-ops skills, what they do, and which one to use next based on where you are in your job search. Use when someone says 'help', 'what can you do', 'how does this work', or seems unsure what to do next."
argument-hint: "[skill name for detailed help]"
user-invocable: true
allowed-tools:
  - Read
  - Glob
---

# career-ops Help

Guide the user through available skills based on where they are in their
job search.

## Step 0: Check State

Read `data/profile.yml` - does it exist?
Read `data/applications.md` - how many entries?
Glob `data/evaluations/*.md` - how many evaluations?
Glob `data/resumes/*.html` - how many resumes?

## Step 1: Show Skill Directory

If the user asked about a specific skill, show detailed help for that skill.
Otherwise show the full directory:

```
## career-ops - Your Job Search Copilot

| Skill | What It Does | Try Saying |
|---|---|---|
| **evaluate** | Score a job posting against your background (A-F blocks) | "Evaluate this job posting" |
| **tailor-resume** | Generate an ATS-optimized resume for a specific role | "Tailor my resume for the Acme role" |
| **scan** | Search company career portals for matching openings | "Scan Google for jobs" |
| **triage** | Quick-score your pipeline of scan results | "Triage my pipeline" |
| **track** | View and update your application tracker | "Show my applications" |
| **apply** | Help fill out application forms | "Help me with this application" |
| **research** | Deep-dive a company before applying or interviewing | "Research Stripe" |
| **outreach** | Draft LinkedIn/email messages to contacts | "Draft outreach to the hiring manager" |
| **compare** | Side-by-side comparison of opportunities | "Compare my top options" |

**Commands:**
| Command | What It Does |
|---|---|
| **setup** | Set up or update your profile |
| **quick-eval** | Fast score + one paragraph (no full report) |
```

## Step 2: Smart Suggestion

Based on the user's current state, suggest the most valuable next action:

**No profile:**
> "Start here: paste your resume or tell me about yourself so I can
> evaluate jobs for you."

**Profile exists, no evaluations:**
> "You're all set! Paste a job posting (URL or text) and I'll evaluate
> how well you match."

**Has evaluations, no resumes:**
> "You have {n} evaluations. Your top match is **{company} - {role}**
> ({score}/5.0). Want me to tailor a resume for it?"

**Has resumes, none applied:**
> "You have resumes ready for {n} roles. Ready to apply? Say 'help me
> with the {company} application' and I'll generate your form answers."

**Has applications:**
> "You have {n} active applications. Say 'show my applications' for a
> status overview, or 'update {company} to {status}' to track progress."

**Has interviews:**
> "You have interviews coming up! Say 'research {company}' to prepare."

## Step 3: Workflow Overview (if user asks "how does this work")

```
## The career-ops Workflow

1. **Set up** your profile (one time, 5 minutes)
   ↓
2. **Evaluate** job postings (paste a JD, get an honest A-F assessment)
   ↓
3. **Tailor** your resume for the best matches
   ↓
4. **Apply** with personalized form answers
   ↓
5. **Track** your applications and follow up

**Discovery tools** (use anytime):
- **Scan** company career pages for new openings
- **Research** companies before interviews
- **Outreach** to contacts at target companies
- **Compare** multiple opportunities side by side
```
