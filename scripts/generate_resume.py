#!/usr/bin/env python3
"""
Render a tailored resume + cover letter from data/master_cv.yml (canonical,
stable content) and a small per-job tailoring YAML file.

This exists so Claude only has to author the small JD-specific tailoring
file (profile summary, keyword picks, project order, cover letter prose) —
this script does all the boilerplate HTML/CSS assembly locally, at zero
LLM token cost.

Usage:
    python scripts/generate_resume.py data/tailoring/<company>.yml

Tailoring YAML shape — see data/tailoring/_example.yml for a full example.
"""
import sys
import re
import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
MASTER = ROOT / "data" / "master_cv.yml"


def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def bold_first_match(text, terms):
    """Bold the first literal occurrence of the first matching term in `terms`.
    Mirrors the standing rule: one lead-in keyword per bullet, not scattered."""
    for term in terms or []:
        idx = text.find(term)
        if idx != -1:
            return text[:idx] + f"<strong>{term}</strong>" + text[idx + len(term):]
    return text


def bold_all_matches(text, terms):
    """Bold every literal occurrence of every term in `terms` (used for the
    comma-separated Skills lines, where multiple bold spans per line is the
    established convention — unlike narrative Experience bullets)."""
    if not terms:
        return text
    for term in sorted(set(terms), key=len, reverse=True):
        pattern = re.escape(term)
        text = re.sub(
            pattern,
            lambda m: f"<strong>{m.group(0)}</strong>",
            text,
        )
    return text


RESUME_CSS = """
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    @page {
      size: A4;
      margin: 18mm 20mm 18mm 20mm;
    }

    body {
      font-family: Arial, Calibri, "Segoe UI", Helvetica, sans-serif;
      font-size: 10.5pt;
      line-height: 1.45;
      color: #1a1a1a;
      max-width: 170mm;
      margin: 0 auto;
      padding: 18mm 20mm;
    }

    @media print {
      body { padding: 0; max-width: none; }
      .page-break { page-break-before: always; }
      a { color: #1a1a1a; text-decoration: none; }
    }

    .header {
      border-bottom: 1.5pt solid #2a2a2a;
      padding-bottom: 10pt;
      margin-bottom: 4pt;
    }

    .header h1 {
      font-size: 15pt;
      font-weight: 700;
      margin-bottom: 6pt;
    }

    .personal-grid {
      display: grid;
      grid-template-columns: 140pt 1fr;
      gap: 3pt 8pt;
      font-size: 10pt;
      color: #333;
    }

    .personal-grid .label { font-weight: 600; }

    h2 {
      font-size: 11pt;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.8pt;
      border-bottom: 0.75pt solid #bbb;
      padding-bottom: 3pt;
      margin-top: 13pt;
      margin-bottom: 7pt;
    }

    .entry { margin-bottom: 9pt; }

    .entry-header {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      margin-bottom: 1pt;
    }

    .entry-header .title { font-weight: 700; font-size: 10.5pt; }
    .entry-header .dates { font-size: 10pt; color: #555; white-space: nowrap; }

    .entry .company { font-size: 10pt; color: #333; margin-bottom: 4pt; }

    .entry .project-label {
      font-size: 10pt;
      font-weight: 600;
      color: #444;
      margin-top: 4pt;
      margin-bottom: 2pt;
    }

    .entry ul { padding-left: 16pt; margin: 0; }
    .entry li { font-size: 10.5pt; margin-bottom: 2pt; line-height: 1.4; }

    .summary { font-size: 10.5pt; line-height: 1.5; margin-bottom: 6pt; }

    .highlight-list { padding-left: 16pt; margin: 0; }
    .highlight-list li { font-size: 10.5pt; margin-bottom: 2pt; line-height: 1.4; }

    .competency-grid { width: 100%; border-collapse: collapse; margin-top: 2pt; }
    .competency-grid td { font-size: 10.5pt; padding: 2pt 10pt 2pt 0; vertical-align: top; width: 33.33%; }

    .skill-category { margin-bottom: 4pt; font-size: 10.5pt; }
    .skill-category-name { font-weight: 600; }

    .edu-entry { margin-bottom: 5pt; font-size: 10.5pt; }
    .edu-entry .degree { font-weight: 600; }
    .edu-entry .school { color: #333; }

    .lang-entry { font-size: 10.5pt; margin-bottom: 2pt; }
    .lang-entry .lang-name { font-weight: 600; }

    .signature-block { margin-top: 24pt; font-size: 10pt; color: #333; }
"""

COVER_LETTER_CSS = """
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    @page { size: A4; margin: 20mm 22mm 20mm 22mm; }
    body {
      font-family: Arial, Calibri, "Segoe UI", Helvetica, sans-serif;
      font-size: 11pt; line-height: 1.6; color: #1a1a1a;
      max-width: 166mm; margin: 0 auto; padding: 20mm 22mm;
    }
    @media print { body { padding: 0; max-width: none; } a { color: #1a1a1a; text-decoration: none; } }
    .sender { font-size: 10.5pt; color: #333; margin-bottom: 20pt; line-height: 1.5; }
    .sender .name { font-size: 13pt; font-weight: 700; color: #1a1a1a; margin-bottom: 3pt; }
    .recipient { font-size: 10.5pt; color: #1a1a1a; margin-bottom: 18pt; line-height: 1.5; }
    .subject { font-size: 11pt; font-weight: 700; margin-bottom: 16pt; }
    .salutation { margin-bottom: 12pt; font-size: 11pt; }
    p { font-size: 11pt; margin-bottom: 12pt; line-height: 1.6; }
    ul { margin: 0 0 14pt 0; padding-left: 18pt; }
    li { font-size: 11pt; margin-bottom: 7pt; line-height: 1.5; }
    .closing { margin-top: 20pt; font-size: 11pt; line-height: 1.6; }
    .signature-gap { margin-top: 32pt; font-size: 11pt; }
    .signature-gap .sig-name { font-weight: 700; }
"""


def render_change_log(entries):
    lines = "\n".join(f"    {e}" for e in entries)
    return f"<!--\n{lines}\n-->"


def render_resume(master, tailoring):
    work_auth = master["work_auth"][tailoring.get("market", "eu")]

    linkedin_row = ""
    if master.get("linkedin"):
        linkedin_row = (
            f'      <span class="label">LinkedIn</span>'
            f'               <span>{esc(master["linkedin"])}</span>\n'
        )

    highlights = "\n".join(f"    <li>{h}</li>" for h in tailoring["highlights"])

    grid_rows = tailoring["area_of_expertise"]
    grid_html = ""
    for i in range(0, len(grid_rows), 3):
        row = grid_rows[i:i + 3]
        cells = "\n".join(f"      <td>{c}</td>" for c in row)
        grid_html += f"    <tr>\n{cells}\n    </tr>\n"

    projects_html = ""
    for key in tailoring["project_order"]:
        proj = master["projects"][key]
        bold_terms = tailoring.get("project_bold_terms", {}).get(key, [])
        bullets = "\n".join(
            f"      <li>{bold_first_match(esc(b), bold_terms)}</li>"
            for b in proj["bullets"]
        )
        projects_html += f"""
    <div class="project-label">{esc(proj["label"])}</div>
    <ul>
{bullets}
    </ul>
"""

    certs_html = "\n".join(f'  <div class="edu-entry">{esc(c)}</div>' for c in master["certifications"])

    skills_bold = tailoring.get("skills_bold_terms", [])
    skills_html = ""
    for cat in master["skills_categories"]:
        items = bold_all_matches(esc(cat["items"]), skills_bold)
        skills_html += (
            f'  <div class="skill-category">\n'
            f'    <span class="skill-category-name">{esc(cat["name"])}: </span>\n'
            f"    {items}\n"
            f"  </div>\n"
        )

    langs_html = "\n".join(
        f'  <div class="lang-entry"><span class="lang-name">{esc(l["name"])}</span> — {esc(l["level"])}</div>'
        for l in master["languages"]
    )

    change_log = render_change_log(tailoring["change_log"])

    return f"""<!DOCTYPE html>
{change_log}
<html lang="{tailoring.get('lang', 'en')}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc(master["name"])}</title>
  <style>{RESUME_CSS}
  </style>
</head>
<body>

  <div class="header">
    <h1>{esc(master["name"])}</h1>
    <div class="personal-grid">
      <span class="label">Address</span>              <span>{esc(master["location"])}</span>
      <span class="label">Phone</span>                 <span>{esc(master["phone"])}</span>
      <span class="label">Email</span>                 <span>{esc(master["email"])}</span>
{linkedin_row}      <span class="label">GitHub</span>                 <span>{esc(master["github"])}</span>
      <span class="label">Work Authorization</span>   <span>{esc(work_auth)}</span>
    </div>
  </div>

  <h2>Profile</h2>
  <div class="summary">
    {tailoring["profile_summary"]}
  </div>
  <ul class="highlight-list">
{highlights}
  </ul>

  <h2>Area of Expertise</h2>
  <table class="competency-grid">
{grid_html}  </table>

  <h2>Experience</h2>

  <div class="entry">
    <div class="entry-header">
      <span class="title">{esc(master["current_role"]["title"])}</span>
      <span class="dates">{esc(master["current_role"]["dates"])}</span>
    </div>
    <div class="company">{esc(master["current_role"]["company"])} | {esc(master["current_role"]["location"])}</div>
{projects_html}
  </div>

  <h2>Education</h2>
  <div class="edu-entry">
    <span class="degree">{esc(master["education"]["degree"])}</span>
    <span class="school"> {esc(master["education"]["detail"])}</span>
  </div>

  <h2>Certifications</h2>
{certs_html}

  <h2>Skills</h2>
{skills_html}
  <h2>Languages</h2>
{langs_html}

</body>
</html>
"""


def render_cover_letter(master, tailoring):
    cl = tailoring["cover_letter"]
    change_log = render_change_log(tailoring["change_log"])

    recipient_lines = f'    <strong>{esc(cl["company_display"])}</strong><br>\n    {esc(cl.get("recipient_title", "Hiring Team"))}'
    salutation = f'Dear {esc(cl["salutation_name"])},' if cl.get("salutation_name") else "Dear Hiring Team,"

    bullets = "\n".join(f"    <li>{b}</li>" for b in cl["bullets"])

    return f"""<!DOCTYPE html>
{change_log}
<html lang="{tailoring.get('lang', 'en')}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Cover Letter - {esc(master["name"])} - {esc(cl["company_display"])}</title>
  <style>{COVER_LETTER_CSS}
  </style>
</head>
<body>

  <div class="sender">
    <div class="name">{esc(master["name"])}</div>
    {esc(master["location"])} &nbsp;|&nbsp; {esc(master["phone"])} &nbsp;|&nbsp; {esc(master["email"])} &nbsp;|&nbsp; {esc(master["github"])}
  </div>

  <div class="recipient">
{recipient_lines}
  </div>

  <div class="subject">{esc(cl["subject"])}</div>

  <div class="salutation">{salutation}</div>

  <p>
    {cl["opening"]}
  </p>

  <ul>
{bullets}
  </ul>

  <p>
    {cl["closing"]}
  </p>

  <div class="closing">
    Best regards,
  </div>

  <div class="signature-gap">
    <span class="sig-name">{esc(master["name"])}</span>
  </div>

</body>
</html>
"""


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/generate_resume.py data/tailoring/<company>.yml")
        sys.exit(1)

    tailoring_path = Path(sys.argv[1])
    master = load_yaml(MASTER)
    tailoring = load_yaml(tailoring_path)

    slug = tailoring["filename_slug"]
    resume_path = ROOT / "data" / "resumes" / f"Jeevan-Kondasingu-{slug}.html"
    resume_path.write_text(render_resume(master, tailoring), encoding="utf-8")
    print(f"Wrote {resume_path.relative_to(ROOT)}")

    if tailoring.get("cover_letter"):
        cl_path = ROOT / "data" / "cover-letters" / f"Jeevan-Kondasingu-{slug}-CoverLetter.html"
        cl_path.write_text(render_cover_letter(master, tailoring), encoding="utf-8")
        print(f"Wrote {cl_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
