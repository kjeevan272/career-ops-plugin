---
name: tailor-resume
description: "Generate an ATS-optimized resume tailored to a specific job posting. Auto-detects German market and generates Lebenslauf format. Works directly from a JD paste — no prior evaluation needed. Use when someone says 'tailor my resume', 'make me a resume', 'create a resume for', 'update my resume for', or after evaluating a job."
argument-hint: "<company name, 'for the latest evaluation', or paste JD directly>"
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Glob
---

# Tailor Resume

Generate an ATS-optimized, market-appropriate resume for a specific job posting.
Read `references/ats-rules.md` before generating any HTML — including the German
market section at the bottom.

---

## Step 0: Load Profile

Read `data/profile.yml` and `data/resume.md` (if it exists).
If profile doesn't exist, run setup first.

---

## Step 1: Get the Job Posting

Sources (in priority order):

1. **Prior evaluation exists:** User named a company/role → search `data/evaluations/`
   for a matching file. "latest" or no argument → use the most recent file.
2. **JD pasted in this message:** Use it directly. Extract all fields below.
3. **No evaluation, no JD:** Ask the user to paste the JD.

Extract from the JD:
- Job title, company name, location / remote policy
- Required qualifications (hard requirements)
- Preferred qualifications (nice-to-haves)
- Key responsibilities and action verbs
- Stated compensation (if any)
- Seniority signals
- JD language (English / German / other)

---

## Step 2: Detect Market & Format

**German market** → use `references/resume-template-de.html` when ANY of:
- Job location includes Germany, Austria, or Switzerland
- Profile location is Germany / DE
- JD is written in German

**All other markets** → use `references/resume-template.html`
- US company → Letter (8.5" × 11")
- Non-US, non-DE → A4

Resume language MUST match the JD language.

---

## Step 3: Extract ATS Keywords

From the JD, extract 15–20 keywords that ATS systems scan for:

- Exact phrases from Required Qualifications (highest priority)
- Tool names and technologies named in the JD
- Certifications or methodologies listed
- Action verbs from the responsibilities section
- Industry-standard terms — never creative synonyms

Place the top 8 keywords in the Summary and first experience entry.

---

## Step 4: Build Resume Content

### Professional Summary / Profil (3–4 lines)
- First line: "[X]+ years of experience as [exact job title from JD]"
- Weave in 4–5 top JD keywords naturally across the 3–4 lines
- End with a forward-looking statement connecting to this specific role
- Use `narrative.headline` from profile as a starting point
- For German market: write in the JD language (EN or DE)

### Area of Expertise / Core Competencies
Place this section AFTER summary, BEFORE experience. It is the single highest-density
keyword section — critical for ATS score.
- Pick 9–12 competency phrases directly from the JD's Required and Preferred sections
- Lay them out in a 3-column grid (simple `<table>` with no borders, no styling)
- Use exact JD phrasing — not paraphrases
- Example grid for a Data Engineering role:
  | ETL Pipeline Development | Data Modeling & Governance | Cloud Data Platforms |
  | Stream Processing (Kafka) | Data Warehouse Architecture | Performance Optimization |
  | Pipeline Orchestration | Lakehouse Design | Data Quality & Observability |

### Experience / Berufserfahrung
- All roles from `work_history`, most relevant FIRST
- Each role: Title, Company, Dates (right-aligned), Location
- 4–6 bullets per role, ordered by relevance to THIS JD
- **Bullet formula (mandatory):** Strong verb → tool/tech named → quantified result
  - Good: "Architected PySpark pipelines on AWS EMR processing 2TB daily, reducing
    job latency by 45% and cutting compute costs by $30K/year"
  - Bad: "Worked on data pipelines to improve performance"
- Every bullet must contain a number. If exact metric unknown, use a meaningful
  approximation ("~40% reduction", "500M+ records/day")
- Mirror JD language exactly (if JD says "data pipeline," use "data pipeline")
- Pull numbers from `proof_points` and `work_history.highlights`
- For roles with many client projects (like consulting): group highlights by
  the 3–4 most relevant clients/projects for this specific JD

### Projects / Projekte (if profile has project entries)
- Include after Experience, before Education
- Format per project: **Project Name** | Tech stack | 1-line impact
- Name specific tools — adds keyword coverage for tech not in work history

### Education / Ausbildung
- Degree, School, Year
- Add honors or relevant coursework only for recent grads

### Skills / Kenntnisse
- Group into categories. For data engineering roles use:
  - **Cloud & Data Platforms:** (AWS Glue, Redshift, S3, EMR, Databricks, Snowflake…)
  - **Processing & Orchestration:** (PySpark, Kafka, Spark, Flink, Airflow…)
  - **Storage & Formats:** (Delta Lake, Iceberg, Parquet, dbt…)
  - **Analytics & BI:** (SQL, Tableau, Power BI, Athena…)
  - **DevOps & Security:** (IAM, KMS, CloudWatch, Linux…)
- List JD keywords FIRST within each category
- Include acronym + full form where needed: "CDC (Change Data Capture)"

### Languages / Sprachen (German market only)
- Always include this section for German market applications
- Pull from profile if available; otherwise use sensible defaults:
  - English: Fluent / Professional (if resume was written in English)
  - German: state level honestly; if unknown, write "Basic (A1–A2)" unless profile says otherwise
  - Any other languages from profile

### Work Authorization line (German market only)
Use the `visa_status` field from profile. Format:
> "Work Authorization – Germany; employment contract required; no visa sponsorship needed"

### Signature block (German market only)
> {City from profile.location}, {today's date in DD. Month YYYY format}
>
> ___________________________
> {Name}

---

## Step 5: Generate HTML

Open the correct template file.
Replace ALL `{{PLACEHOLDER}}` slots with generated content.

For German template, set:
- `{{LANG}}` → `de` if JD is German, `en` if English
- `{{SECTION_PROFILE}}` → "Profil" (DE) or "Professional Profile" (EN)
- `{{SECTION_EXPERIENCE}}` → "Berufserfahrung" (DE) or "Experience" (EN)
- `{{SECTION_EDUCATION}}` → "Ausbildung" (DE) or "Education" (EN)
- `{{SECTION_SKILLS}}` → "Kenntnisse" (DE) or "Skills" (EN)
- `{{SECTION_LANGUAGES}}` → "Sprachen" (DE) or "Languages" (EN)
- `{{LINKEDIN_ROW}}` → full `<span class="label">LinkedIn</span><span>URL</span>` row,
  or empty string if no LinkedIn in profile
- `{{PORTFOLIO_ROW}}` → same pattern for GitHub/portfolio, or empty string
- `{{WORK_AUTH}}` → work authorization string from profile
- `{{SIGNATURE_CITY}}` → city from profile.location
- `{{SIGNATURE_DATE}}` → today's date formatted as "20. Mai 2026" (DE) or "20 May 2026" (EN)

ATS compliance checklist before writing the file:
- [ ] Single column, no sidebars
- [ ] No images or graphics
- [ ] All text is real text (selectable)
- [ ] Standard fonts only
- [ ] No JavaScript
- [ ] Max 2 pages when printed
- [ ] Standard section header names

---

## Step 6: Write & Preview

Write the HTML to `data/resumes/{FirstName}-{LastName}-{CompanySlug}-{RoleSlug}.html`.

Show the user a content preview (not raw HTML):

```
## Resume Ready: {Name} → {Role} at {Company}
**Format:** {German Lebenslauf / US Letter / A4}

**Profile summary (first 2 lines):** {text}

**Experience highlights:**
- {Title} at {Company} ({dates})
  → {first bullet}
- {same for next role if any}

**Skills (top 10):** {comma-separated}
**Languages:** {if German format}

**ATS keywords matched:** {n}/{total} from JD
```

---

## Step 7: PDF Instructions

> "Your tailored resume is ready at `data/resumes/{filename}.html`
>
> **To export as PDF:**
> 1. Open the file in your browser (double-click it)
> 2. Press **Ctrl+P** (Windows) or **Cmd+P** (Mac)
> 3. Choose **Save as PDF** — set paper to **A4**
> 4. Disable headers/footers in print settings
> 5. Save it as `{Name}-{Company}-{Role}.pdf`
>
> That PDF is ATS-safe and ready to attach to your application."

---

## Step 8: Update Tracker

Update `data/applications.md`:
- If a matching row exists (same company + role): set Status → "Resume Ready",
  append `Resume: {filename}` to Notes
- If no row exists: add a new row with today's date, company, role, Status = "Resume Ready"

---

## Step 9: Next Steps

> "Resume is ready. Next steps:
> - **Apply** — open the HTML, print to PDF (Ctrl+P → Save as PDF), attach to application
> - **Cover letter** — say 'write a cover letter for {company}' and I'll draft one
> - **Compare options** — say 'compare my options' to rank all evaluated roles"
