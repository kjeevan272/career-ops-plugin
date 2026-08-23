#!/usr/bin/env python3
"""
Render a tailored resume + cover letter from data/master_cv.yml (canonical,
stable content) and a small per-job tailoring YAML file.

This exists so Claude only has to author the small JD-specific tailoring
file (profile summary, keyword picks, project order, cover letter prose) —
this script does all the boilerplate HTML/CSS assembly locally, at zero
LLM token cost.

Template: matches the 2026-07-30 hand-authored house style (tinted header
box, role-tag line, accent-colored bold keywords, bordered project titles,
no separate long Skills-category dump) — see data/resumes/cv_*.html for the
original hand-written examples this was reverse-engineered from.

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

DEFAULT_COLORS = {"accent": "#26282b", "accent2": "#3aa6a6", "tint": "#eef2f2", "sub": "#444"}


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
    """Bold every literal occurrence of every term in `terms` (used for
    comma-separated lines where multiple bold spans per line is fine —
    unlike narrative Experience bullets)."""
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


def resume_css(c):
    return f"""
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{ --accent: {c['accent']}; --accent-2: {c['accent2']}; --tint: {c['tint']}; --ink: #1a1a1a; --sub: {c['sub']}; }}
    @page {{ size: A4; margin: 14mm 18mm 14mm 18mm; }}
    body {{
      font-family: Arial, Calibri, "Segoe UI", Helvetica, sans-serif;
      font-size: 9.7pt; line-height: 1.45; color: var(--ink);
      max-width: 174mm; margin: 0 auto; padding: 14mm 18mm;
      -webkit-print-color-adjust: exact; print-color-adjust: exact;
    }}
    @media print {{ body {{ padding: 0; max-width: none; }} a {{ color: var(--accent); text-decoration: none; }} }}
    strong {{ font-weight: 700; color: var(--accent-2); }}
    .header {{ background: var(--tint); border-left: 3pt solid var(--accent); padding: 10pt 12pt; margin-bottom: 12pt; }}
    .header h1 {{ font-size: 16pt; font-weight: 700; margin-bottom: 3pt; color: var(--accent); }}
    .header .role-tag {{ font-size: 9.3pt; font-weight: 600; color: var(--accent-2); margin-bottom: 6pt; text-transform: uppercase; letter-spacing: 0.3pt; }}
    .header .contact {{ font-size: 9.3pt; color: var(--sub); line-height: 1.6; }}
    h2 {{
      font-size: 10.5pt; font-weight: 700; text-transform: uppercase; letter-spacing: 0.7pt;
      color: var(--accent); border-bottom: 1.5pt solid var(--accent-2);
      padding-bottom: 3pt; margin-top: 11pt; margin-bottom: 6pt;
    }}
    p {{ font-size: 9.7pt; margin-bottom: 6pt; line-height: 1.5; }}
    .highlight-list {{ list-style: none; padding: 0; margin-bottom: 4pt; }}
    .highlight-list li {{ font-size: 9.5pt; margin-bottom: 3pt; padding-left: 10pt; position: relative; }}
    .highlight-list li::before {{ content: ""; position: absolute; left: 0; top: 6pt; width: 5pt; height: 5pt; background: var(--accent-2); border-radius: 50%; }}
    .expertise-list {{ list-style: none; padding: 0; margin-bottom: 4pt; display: flex; flex-wrap: wrap; }}
    .expertise-list li {{ font-size: 9.5pt; font-weight: 600; color: var(--accent); flex: 0 0 33.33%; padding: 2.5pt 8pt 2.5pt 0; }}
    .skills-block {{ font-size: 9.3pt; margin-bottom: 5pt; line-height: 1.5; }}
    .skills-block .cat-name {{ font-weight: 700; color: var(--accent); }}
    .entry-intro {{ font-size: 9.5pt; margin-bottom: 6pt; color: var(--sub); }}
    .ref-note {{ background: var(--tint); color: var(--accent-2); font-weight: 700; padding: 2pt 5pt; border-radius: 3pt; }}
    .role-block {{ margin-bottom: 4pt; }}
    .role-header {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 1pt; }}
    .role-header .title {{ font-weight: 700; font-size: 10.5pt; color: var(--accent); }}
    .role-header .dates {{ font-size: 9.3pt; color: var(--sub); white-space: nowrap; }}
    .role-header .company {{ font-size: 9.3pt; color: var(--sub); font-style: italic; }}
    .project {{ margin-top: 7pt; margin-bottom: 2pt; }}
    .project-title {{ font-size: 9.3pt; font-weight: 700; color: var(--accent-2); border-left: 2.5pt solid var(--accent-2); padding-left: 6pt; margin-bottom: 2pt; }}
    .project ul {{ list-style: none; padding: 0; margin: 0 0 4pt 8pt; }}
    .project li {{ font-size: 9.3pt; margin-bottom: 1.5pt; padding-left: 9pt; position: relative; line-height: 1.4; }}
    .project li::before {{ content: ""; position: absolute; left: 0; top: 5.5pt; width: 4pt; height: 4pt; background: var(--accent); border-radius: 50%; }}
    .edu-entry, .lang-entry, .cert-row {{ font-size: 9.7pt; margin-bottom: 3pt; }}
    .edu-entry .degree, .lang-name {{ font-weight: 600; color: var(--accent); }}
"""


def cover_letter_css(c):
    return f"""
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{ --accent: {c['accent']}; --accent-2: {c['accent2']}; --tint: {c['tint']}; --ink: #1a1a1a; --sub: {c['sub']}; }}
    @page {{ size: A4; margin: 20mm 22mm 20mm 22mm; }}
    body {{
      font-family: Arial, Calibri, "Segoe UI", Helvetica, sans-serif;
      font-size: 11pt; line-height: 1.55; color: var(--ink);
      max-width: 166mm; margin: 0 auto; padding: 20mm 22mm;
      -webkit-print-color-adjust: exact; print-color-adjust: exact;
    }}
    @media print {{ body {{ padding: 0; max-width: none; }} a {{ color: var(--accent); text-decoration: none; }} }}
    .sender {{ background: var(--tint); border-left: 3pt solid var(--accent); padding: 8pt 10pt; font-size: 10.5pt; color: var(--sub); margin-bottom: 18pt; }}
    .sender strong {{ font-size: 14pt; font-weight: 700; color: var(--accent); display: block; margin-bottom: 4pt; }}
    .date-line {{ margin-bottom: 18pt; font-size: 10.5pt; color: var(--sub); }}
    .recipient {{ font-size: 10.5pt; color: var(--sub); margin-bottom: 18pt; line-height: 1.5; }}
    .subject {{ font-weight: 700; font-size: 11.5pt; color: var(--accent); margin-bottom: 14pt; border-bottom: 1.5pt solid var(--accent-2); padding-bottom: 6pt; }}
    p {{ margin-bottom: 10pt; font-size: 11pt; }}
    strong {{ font-weight: 700; color: var(--accent-2); }}
    ul.points {{ list-style: none; padding: 0; margin: 0 0 12pt 0; }}
    ul.points li {{ font-size: 10.7pt; margin-bottom: 6pt; padding-left: 12pt; position: relative; line-height: 1.45; }}
    ul.points li::before {{ content: ""; position: absolute; left: 0; top: 6pt; width: 5pt; height: 5pt; background: var(--accent-2); border-radius: 50%; }}
    .signature-block {{ margin-top: 24pt; font-size: 10.5pt; color: var(--sub); border-top: 1pt solid var(--tint); padding-top: 10pt; }}
"""


def render_change_log(entries):
    lines = "\n".join(f"    {e}" for e in entries)
    return f"<!--\n{lines}\n-->"


def render_resume(master, tailoring):
    colors = {**DEFAULT_COLORS, **tailoring.get("colors", {})}
    work_auth = master["work_auth"][tailoring.get("market", "eu")]

    highlights = "\n".join(f"    <li>{h}</li>" for h in tailoring["highlights"])

    grid_html = "\n".join(f"    <li>{c}</li>" for c in tailoring["area_of_expertise"])

    skills_html = "\n".join(
        f'  <p class="skills-block"><span class="cat-name">{esc(cat["name"])}:</span> {esc(cat["items"])}</p>'
        for cat in master["skills_categories"]
    )

    projects_html = ""
    for key in tailoring["project_order"]:
        proj = master["projects"][key]
        bold_terms = tailoring.get("project_bold_terms", {}).get(key, [])
        picks = tailoring.get("project_bullet_picks", {}).get(key, [0])
        selected_bullets = [proj["bullets"][i] for i in picks]
        bullets = "\n".join(
            f"      <li>{bold_first_match(esc(b), bold_terms)}</li>"
            for b in selected_bullets
        )
        projects_html += f"""
    <div class="project">
      <div class="project-title">{esc(proj["label"])}</div>
      <ul>
{bullets}
      </ul>
    </div>
"""

    certs_html = "\n".join(f'  <div class="cert-row">{esc(c)}</div>' for c in master["certifications"])

    langs_html = "\n".join(
        f'  <div class="lang-entry"><span class="lang-name">{esc(l["name"])}</span> &mdash; {esc(l["level"])}</div>'
        for l in master["languages"]
    )

    change_log = render_change_log(tailoring["change_log"])
    title_suffix = tailoring.get("title_suffix") or tailoring.get("cover_letter", {}).get("company_display", "")
    entry_intro = tailoring.get("entry_intro", "")
    additional = f"{work_auth}. {tailoring.get('additional', '')}".strip()

    return f"""<!DOCTYPE html>
{change_log}
<html lang="{tailoring.get('lang', 'en')}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CV - {esc(master["name"])} - {esc(title_suffix)}</title>
  <style>{resume_css(colors)}
  </style>
</head>
<body>

  <div class="header">
    <h1>{esc(master["name"])}</h1>
    <div class="role-tag">{tailoring.get("role_tag", "Data Engineer")}</div>
    <div class="contact">
      {esc(master["location"])} &nbsp;-&nbsp; {esc(master["phone"])} &nbsp;-&nbsp; {esc(master["email"])}<br>
      {esc(master["linkedin"])} &nbsp;-&nbsp; {esc(master["github"])}
    </div>
  </div>

  <h2>Professional Profile</h2>
  <p>
    {tailoring["profile_summary"]}
  </p>
  <ul class="highlight-list">
{highlights}
  </ul>

  <h2>Area of Expertise</h2>
  <ul class="expertise-list">
{grid_html}
  </ul>

  <h2>Technical Skills</h2>
{skills_html}

  <h2>Professional Experience</h2>

  <div class="role-block">
    <div class="role-header">
      <span class="title">{esc(master["current_role"]["title"])}</span>
      <span class="dates">{esc(master["current_role"]["dates"])}</span>
    </div>
    <div class="role-header"><span class="company">{esc(master["current_role"]["company"])} - {esc(master["current_role"]["location"])}</span></div>
    <p class="entry-intro">{esc(entry_intro)}</p>
{projects_html}
  </div>

  <h2>Education</h2>
  <div class="edu-entry"><span class="degree">{esc(master["education"]["degree"])}</span><br> {esc(master["education"]["detail"])}</div>

  <h2>Certifications</h2>
{certs_html}

  <h2>Languages</h2>
{langs_html}

  <h2>Additional</h2>
  <p>{additional}</p>

</body>
</html>
"""


def render_cover_letter(master, tailoring):
    colors = {**DEFAULT_COLORS, **tailoring.get("colors", {})}
    cl = tailoring["cover_letter"]
    change_log = render_change_log(tailoring["change_log"])

    home_city = master["location"].split(",")[0]
    date_str = datetime.date.today().strftime("%d %B %Y").lstrip("0")

    recipient_lines = f'    {esc(cl["company_display"])}<br>\n    {esc(cl.get("recipient_title", "Hiring Team"))}'
    bullets = "\n".join(f"    <li>{b}</li>" for b in cl["bullets"])

    return f"""<!DOCTYPE html>
{change_log}
<html lang="{tailoring.get('lang', 'en')}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Cover Letter - {esc(master["name"])} - {esc(cl["company_display"])}</title>
  <style>{cover_letter_css(colors)}
  </style>
</head>
<body>

  <div class="sender">
    <strong>{esc(master["name"])}</strong>
    {esc(master["location"])} &nbsp;|&nbsp; {esc(master["phone"])} &nbsp;|&nbsp; {esc(master["email"])} &nbsp;|&nbsp; {esc(master["github"])}
  </div>

  <div class="date-line">{esc(home_city)}, {date_str}</div>

  <div class="recipient">
{recipient_lines}
  </div>

  <div class="subject">{esc(cl["subject"])}</div>

  <p>
    {cl["opening"]}
  </p>

  <ul class="points">
{bullets}
  </ul>

  <p>
    {cl["closing"]}
  </p>

  <div class="signature-block">
    Yours sincerely,<br><br><br>
    ___________________________<br>
    {esc(master["name"])}
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
