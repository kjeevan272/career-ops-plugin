---
name: apply
description: "Help fill out a job application form. Generates personalized answers for every field using your profile and evaluation. Never auto-submits. Use when someone says 'help me apply', 'fill out this application', or 'application for'."
argument-hint: "<company name or 'help me with this application'>"
user-invocable: true
disable-model-invocation: true
allowed-tools:
  - Read
  - Write
  - Glob
  - WebFetch
---

# Application Form Assistant

Help fill out job application forms with personalized, honest answers.

**CRITICAL: NEVER auto-submit an application.** Always show the user every
answer and get explicit confirmation before any form interaction. Always stop
before any submit button.

## Step 0: Load Context

1. Read `data/profile.yml` for structured background
2. Read `data/resume.md` for full resume text
3. Find the relevant evaluation in `data/evaluations/`
4. Check `data/research/{company}.md` for company intel
5. Check `data/resumes/` for a tailored resume file

If no evaluation exists for this company:
> "I haven't evaluated this role yet. Want me to evaluate the posting
> first? That gives me better context for your application answers."

## Step 1: Identify the Application

Parse user input:
- **Company/role name:** Find the matching evaluation
- **"Help me with this application":** Ask which company/role, or if
  computer use is available, take a screenshot to identify the form

## Step 2: Map Common Form Fields

Generate answers for standard application fields:

| Field | Source | How to Fill |
|---|---|---|
| Name / Email / Phone | profile.yml | Direct copy |
| Resume upload | Point to file | "Upload `data/resumes/{file}.html` (or PDF if you printed it)" |
| Cover letter | Generate below | Tailored to this role |
| "Why this company?" | Research + evaluation | Specific, referencing company details |
| "Why this role?" | Evaluation Block C + narrative | Connect background to role requirements |
| Years of experience | profile.yml | Honest number |
| Salary expectations | Evaluation Block D | Use target from profile, informed by market data |
| Work authorization | profile.yml visa_status | Direct answer |
| Willing to relocate | profile.yml work_preference | Direct answer |
| Start date | Ask user | "When can you start?" |

## Step 3: Cover Letter (when needed)

Structure:
1. **Opening (1-2 sentences):** Specific hook referencing something real about the
   company or role — NOT "I'm excited to apply" or "I was thrilled to see your posting."
   Good: "Your team's migration from a Redshift monolith to a lakehouse architecture
   is exactly the kind of challenge I've spent the last 3 years solving."
2. **Bridge (1 sentence):** State your role identity and years of experience.
   Use the exact job title from the JD.
3. **Evidence (2–3 short bullets or sentences):** Concrete accomplishments, each with
   a number. Pull from `proof_points` and `work_history.highlights`.
   - At least 2 of the 3 must be quantified (%, records, cost, time saved)
   - Name the specific tool/technology involved, matching JD keywords
   - Good: "At [Company], I built PySpark pipelines on AWS EMR that reduced
     daily processing time from 6 hours to 40 minutes for 2TB of clickstream data."
4. **Close (2 sentences):** Forward-looking, confident, low-pressure.
   Reference something specific about why THIS company, not just the role.

Rules:
- 250-350 words total
- Mirror exact JD keywords throughout — ATS systems score CLs too
- Match company tone (formal for enterprise, conversational for startups)
- Reference specific details from research file if available
- Every claim must be backed by real experience from the profile
- NO generic phrases: "team player", "passionate", "results-driven", "hard worker"
- Subject line (for email): "{Role Title} – {Your Name} – {1 standout credential}"

## Step 4: Handle Custom Questions

For each custom application question:

**Short answer (< 500 chars):**
- Draw from evaluation blocks, profile, or research
- Be specific, not generic
- Include a number or concrete detail when possible

**"Tell me about a time..." (behavioral):**
- Use STAR format from evaluation Block F stories
- Match the most relevant story to the question

**"What are your salary expectations?":**
- Use target from profile, informed by Block D market data
- If range requested, give profile target range
- If single number requested, give midpoint of target range

**Yes/No questions (authorization, relocation, etc.):**
- Answer directly from profile data
- If not in profile, ask the user

**EEO / demographic questions:**
- Tell the user these are optional and legally cannot affect their candidacy
- Let them answer themselves

## Step 5: Present All Answers

Show EVERY generated answer before any action:

```
## Application Answers: {Company} - {Role}

**Cover letter:**
{full text}

**"Why this company?"**
{answer}

**"Why this role?"**
{answer}

**Salary expectations:** {answer}

**Custom questions:**
1. "{question}" - {answer}
2. "{question}" - {answer}

---

Review these answers. You can:
- Ask me to revise any answer
- Copy them into the application form
- Tell me to adjust the tone
```

## Step 6: Computer Use Assistance (only if available and user requests)

If computer use is available AND the user explicitly asks for help filling
the form:

1. Navigate to the application page
2. Fill each field with the APPROVED answers only
3. Upload resume file if the form accepts it
4. **STOP before the Submit button.** Take a screenshot. Say:

> "Everything is filled in. Please review the form carefully and click
> Submit when you're ready. I won't click it for you."

If no computer use:
> "Copy the answers above into the application form. Let me know
> when you've submitted and I'll update your tracker."

## Step 7: Update Tracker

After the user confirms submission:
- Update `data/applications.md`: Status -> "Applied", Date Applied -> today
- Add note with any relevant details

> "Tracked! Your application to {company} is logged. I'll remind you
> to follow up if you haven't heard back in a week."
