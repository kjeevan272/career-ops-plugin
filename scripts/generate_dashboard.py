"""
Generate pipeline-dashboard.html (repo root) from data/pipeline.md
Defaults to showing ONLY the new roles from the latest scrape run (URL-matched
against data/.last-run.json), sorted by date found descending.
Run: python scripts/generate_dashboard.py
Flags:
  --all           show the full historical pipeline instead of new-only
  --since=YYYY-MM-DD   show jobs found on/after this date
  --country=NAME       only include jobs whose location contains this country name
  --output=PATH        write to this path instead of pipeline-dashboard.html
"""

import json
import re
import sys
import yaml
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from nl_sponsors import load_sponsor_set, is_recognized_sponsor, is_netherlands_location

ROOT           = Path(__file__).parent.parent
PIPELINE_PATH  = ROOT / "data" / "pipeline.md"
LAST_RUN_PATH  = ROOT / "data" / ".last-run.json"
APPS_PATH      = ROOT / "data" / "applications.md"
PROFILE_PATH   = ROOT / "data" / "profile.yml"
# Kept at repo root (tracked in git), not data/ (gitignored) — this is the
# dashboard file the user actually opens/bookmarks.
OUTPUT_PATH    = ROOT / "pipeline-dashboard.html"


def parse_url(cell):
    m = re.search(r'\(https?://[^\)]+\)', cell)
    return m.group(0).strip("()") if m else ""


def parse_score(cell):
    m = re.search(r'(\d+)', cell)
    return int(m.group(1)) if m else 0


def load_last_run():
    if not LAST_RUN_PATH.exists():
        return None
    try:
        return json.loads(LAST_RUN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def parse_pipeline():
    if not PIPELINE_PATH.exists():
        print("ERROR: data/pipeline.md not found")
        sys.exit(1)

    jobs = []
    for line in PIPELINE_PATH.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or line.startswith("| Date") or line.startswith("|---"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]

        # Job titles sometimes contain literal unescaped "|" (e.g. "(w|m|d)"),
        # which fragments the naive split. Anchor the fixed trailing columns
        # from the *end* of the row and treat everything in between (after
        # date/posted/company) as the role, rejoined with "|".
        if len(cols) >= 10:   # new 10-column format
            date_found = cols[0]
            posted     = cols[1]
            company    = cols[2]
            role       = "|".join(cols[3:-6]).strip()
            score      = parse_score(cols[-6])
            location   = cols[-5]
            remote     = cols[-4].lower() in ("yes", "✅")
            source     = cols[-3].lower()
            url        = parse_url(cols[-2])
            status     = cols[-1]
        elif len(cols) >= 8:  # old 8-column format
            date_found = cols[0]
            posted     = "—"
            company    = cols[1]
            role       = "|".join(cols[2:-5]).strip()
            score      = parse_score(cols[-5])
            location   = cols[-4]
            remote     = cols[-3] in ("✅", "Yes", "yes")
            source     = "—"
            url        = parse_url(cols[-2])
            status     = cols[-1]
        else:
            continue

        if not role or not company or not url:
            continue
        if company.lower() in ("company", "---"):
            continue

        jobs.append({
            "date_found": date_found,
            "posted":     posted,
            "company":    company,
            "role":       role,
            "score":      score,
            "location":   location,
            "remote":     remote,
            "source":     source,
            "url":        url,
            "status":     status,
        })

    return jobs


def norm(s):
    return re.sub(r'\s*\([^)]*\)', '', s).strip().lower()


def parse_applications():
    """Pull company/role -> resume/cover-letter file links from data/applications.md,
    regardless of exact column layout (that table's shape has drifted over time)."""
    if not APPS_PATH.exists():
        return []

    entries = []
    for line in APPS_PATH.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or line.startswith("| Date") or line.startswith("|---"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 4:
            continue
        company = cols[2]
        role    = cols[3]
        if company.lower() in ("company", "---") or not company:
            continue

        resume_m = re.search(r'\[Resume\]\(([^)]+)\)', line)
        cover_m  = re.search(r'\[Cover Letter\]\(([^)]+)\)', line)
        if not resume_m and not cover_m:
            continue

        entries.append({
            "company_n": norm(company),
            "role_n":    norm(role),
            "resume":    resume_m.group(1) if resume_m else "",
            "cover":     cover_m.group(1) if cover_m else "",
        })
    return entries


def attach_docs(jobs, app_entries):
    for j in jobs:
        cj, rj = norm(j["company"]), norm(j["role"])
        best = None
        for a in app_entries:
            if a["company_n"] != cj:
                continue
            if a["role_n"] == rj or a["role_n"] in rj or rj in a["role_n"]:
                best = a
                break
            if best is None:
                best = a  # same company, different-worded role — still the best guess
        if best:
            j["resume_doc"] = best["resume"]
            j["cover_doc"]  = best["cover"]
        else:
            j["resume_doc"] = ""
            j["cover_doc"]  = ""


def load_search_countries():
    try:
        profile = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
        countries = profile.get("target", {}).get("search_countries", [])
        return countries or ["Germany"]
    except Exception:
        return ["Germany"]


def attach_country(jobs, countries=None):
    """Derive a country label per job from its location string, matching the
    same substring logic the --country= CLI flag already used (so the
    dashboard filter and the CLI flag agree on what "located in Germany"
    means). Falls back to "Other" when the location doesn't contain any of
    profile.yml's target.search_countries — this catches remote-only
    postings with a vague/blank location and postings from a country outside
    the configured search list that still made it in via a broad source."""
    countries = countries or load_search_countries()
    for j in jobs:
        loc = (j.get("location") or "").lower()
        match = next((c for c in countries if c.lower() in loc), None)
        j["country"] = match or "Other"


def attach_nl_sponsor_status(jobs):
    """For Netherlands-located jobs, flag whether the company is an IND-recognized
    sponsor (can legally sponsor a work/highly-skilled-migrant visa)."""
    if not any(is_netherlands_location(j["location"]) for j in jobs):
        for j in jobs:
            j["nl_sponsor"] = None
        return

    sponsor_set = load_sponsor_set()
    for j in jobs:
        if is_netherlands_location(j["location"]):
            j["nl_sponsor"] = is_recognized_sponsor(j["company"], sponsor_set)
        else:
            j["nl_sponsor"] = None


def escape(s):
    return s.replace("\\", "\\\\").replace("`", "\\`").replace("'", "\\'").replace('"', '\\"')


def js_array(jobs):
    rows = []
    for i, j in enumerate(jobs, 1):
        s = j["source"].lower()
        src = ("linkedin"      if "linkedin"      in s
               else "indeed"   if "indeed"        in s
               else "glassdoor" if "glassdoor"    in s
               else "google"   if "google"        in s
               else "stepstone" if "stepstone"    in s
               else s)
        rows.append(
            "  {" +
            f"n:{i}," +
            f'score:{j["score"]},' +
            f'company:"{escape(j["company"])}",' +
            f'role:"{escape(j["role"])}",' +
            f'location:"{escape(j["location"])}",' +
            f'country:"{escape(j.get("country", "Other"))}",' +
            f'remote:{"true" if j["remote"] else "false"},' +
            f'source:"{src}",' +
            f'posted:"{escape(j["posted"])}",' +
            f'dateFound:"{escape(j["date_found"])}",' +
            f'url:"{escape(j["url"])}",' +
            f'isNew:{"true" if j.get("is_new") else "false"},' +
            f'resumeDoc:"{escape(j.get("resume_doc", ""))}",' +
            f'coverDoc:"{escape(j.get("cover_doc", ""))}",' +
            f'nlSponsor:{"null" if j.get("nl_sponsor") is None else ("true" if j["nl_sponsor"] else "false")}' +
            "}"
        )
    return "[\n" + ",\n".join(rows) + "\n]"


def generate_html(jobs, run_info, country_label=None):
    total        = len(jobs)
    new_jobs     = [j for j in jobs if j.get("is_new")]
    new_count    = len(new_jobs)
    all_remote   = sum(1 for j in jobs if j["remote"])
    all_high     = sum(1 for j in jobs if j["score"] >= 7)

    run_count = run_info["count"] if run_info else 0
    run_ts    = run_info.get("timestamp", "")[:16].replace("T", " ") if run_info else "—"

    # Sort: date_found desc, score desc within same date; new-run jobs naturally float to top
    sorted_jobs = sorted(jobs, key=lambda j: (j["date_found"], j["score"]), reverse=True)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Job Pipeline{f" — {country_label}" if country_label else ""} — Jeevan Kumar Kondasingu</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;background:#f0f2f5;color:#1a1a1a;font-size:14px}}
    header{{background:#1a1a2e;color:#fff;padding:18px 28px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}}
    header h1{{font-size:18px;font-weight:700}}
    header p{{font-size:12px;color:#aab;margin-top:3px}}
    .stats{{display:flex;gap:20px}}
    .stat .n{{font-size:26px;font-weight:700;color:#7eb8f7}}
    .stat .l{{font-size:11px;color:#99a;text-transform:uppercase}}
    .run-bar{{background:#0f3460;border-bottom:1px solid #1a2a5a;padding:8px 28px;font-size:12px;color:#7eb8f7;display:flex;align-items:center;gap:16px;flex-wrap:wrap}}
    .run-bar strong{{color:#fff}}
    .controls{{background:#fff;border-bottom:1px solid #e0e0e0;padding:12px 28px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}}
    .controls input,.controls select{{border:1px solid #ccc;border-radius:6px;padding:6px 10px;font-size:13px;outline:none}}
    .controls input{{width:220px}}
    .controls input:focus,.controls select:focus{{border-color:#4a90e2}}
    .count-badge{{margin-left:auto;background:#e8f0fe;color:#1a73e8;padding:4px 12px;border-radius:20px;font-size:13px;font-weight:600}}
    .table-wrap{{padding:16px 28px;overflow-x:auto}}
    .section-divider{{padding:8px 0 4px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#666;border-bottom:2px solid #e0e0e0;margin-bottom:2px}}
    .section-divider.new-section{{color:#1a73e8;border-color:#1a73e8}}
    table{{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
    thead tr{{background:#1a1a2e;color:#fff}}
    thead th{{padding:10px 12px;text-align:left;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;white-space:nowrap}}
    tbody tr{{border-bottom:1px solid #f0f0f0;transition:background .12s}}
    tbody tr:hover{{background:#f7f9ff}}
    tbody tr.applied{{opacity:.4;background:#f9f9f9}}
    tbody tr.is-new{{background:#f0f7ff}}
    tbody tr.is-new:hover{{background:#e3f0ff}}
    tbody tr.separator-row td{{background:#f8f8f8;padding:6px 12px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:#888;border-top:3px solid #ddd}}
    tbody tr:last-child{{border-bottom:none}}
    td{{padding:9px 12px;vertical-align:middle}}
    .score{{display:inline-flex;align-items:center;justify-content:center;width:40px;height:24px;border-radius:12px;font-size:11px;font-weight:700;color:#fff}}
    .s9{{background:#1a7f37}}.s8{{background:#2da44e}}.s7{{background:#5ba35b}}.s6{{background:#e3a008}}.s5{{background:#cf6d17}}.s4{{background:#9e6a03}}
    .company{{font-weight:600}}
    .role{{color:#333;max-width:280px;font-size:13px}}
    .badge{{display:inline-block;padding:2px 7px;border-radius:10px;font-size:11px;font-weight:600;white-space:nowrap}}
    .bnew{{background:#dbeafe;color:#1d4ed8;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px}}
    .bnl-yes{{background:#d1fae5;color:#065f46;font-size:10px;font-weight:700}}
    .bnl-no{{background:#f3f4f6;color:#6b7280;font-size:10px;font-weight:600}}
    .br{{background:#e6f4ea;color:#137333}}.bo{{background:#f1f3f4;color:#666}}
    .bli{{background:#dbeafe;color:#1d4ed8}}.bin{{background:#fef3c7;color:#92400e}}
    .bgr{{background:#f3e8ff;color:#6b21a8}}.bba{{background:#fce7f3;color:#9d174d}}
    .bgl{{background:#d1fae5;color:#065f46}}.bgo{{background:#fef9c3;color:#713f12}}
    .bss{{background:#ffe4e6;color:#9f1239}}.blv{{background:#ede9fe;color:#5b21b6}}
    .ban{{background:#e0f2fe;color:#0369a1}}
    .bcc{{background:#dcfce7;color:#166534}}
    .posted{{font-size:11px;color:#888;white-space:nowrap}}
    .location{{color:#555;font-size:12px;max-width:160px}}
    .btn-apply{{display:inline-block;padding:5px 13px;background:#1a73e8;color:#fff;border-radius:6px;font-size:12px;font-weight:600;text-decoration:none;margin-right:4px;transition:background .15s;white-space:nowrap}}
    .btn-apply:hover{{background:#1557b0}}
    .btn-apply.linkedin{{background:#0a66c2}}.btn-apply.linkedin:hover{{background:#084e96}}
    .btn-apply.indeed{{background:#2164f3}}.btn-apply.indeed:hover{{background:#1a4fcf}}
    .btn-apply.greenhouse{{background:#6b21a8}}.btn-apply.greenhouse:hover{{background:#581c87}}
    .btn-apply.ashby{{background:#5b21b6}}.btn-apply.ashby:hover{{background:#4c1d95}}
    .btn-apply.lever{{background:#5b21b6}}.btn-apply.lever:hover{{background:#4c1d95}}
    .btn-apply.arbeitsagentur{{background:#9d174d}}.btn-apply.arbeitsagentur:hover{{background:#831843}}
    .btn-apply.arbeitnow{{background:#0369a1}}.btn-apply.arbeitnow:hover{{background:#075985}}
    .btn-apply.stepstone{{background:#9f1239}}.btn-apply.stepstone:hover{{background:#881337}}
    .btn-apply.google{{background:#1a73e8}}.btn-apply.google:hover{{background:#1557b0}}
    .btn-apply.glassdoor{{background:#065f46}}.btn-apply.glassdoor:hover{{background:#064e3b}}
    .btn-doc{{display:inline-block;padding:4px 10px;border-radius:6px;font-size:11px;font-weight:600;text-decoration:none;margin-right:4px;margin-bottom:3px;white-space:nowrap;transition:background .15s}}
    .btn-doc.resume{{background:#ecfdf5;color:#065f46;border:1px solid #a7f3d0}}
    .btn-doc.resume:hover{{background:#d1fae5}}
    .btn-doc.cover{{background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe}}
    .btn-doc.cover:hover{{background:#dbeafe}}
    .btn-done{{padding:5px 10px;border:1px solid #ccc;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;background:#fff;color:#555;white-space:nowrap;transition:all .15s}}
    .btn-done:hover{{background:#fef3c7;border-color:#e3a008;color:#92400e}}
    .btn-done.applied{{background:#e6f4ea;border-color:#137333;color:#137333}}
    .no-results{{text-align:center;padding:50px;color:#888;font-size:15px}}
    footer{{text-align:center;padding:16px;color:#999;font-size:12px}}
  </style>
</head>
<body>
<header>
  <div>
    <h1>Job Pipeline{f" — {country_label}" if country_label else ""} — Jeevan Kumar Kondasingu</h1>
    <p>Senior Data Engineer · {country_label or "Germany"} · career-ops-plugin</p>
  </div>
  <div class="stats">
    <div class="stat"><div class="n" id="stat-shown">{total}</div><div class="l">Showing</div></div>
    <div class="stat"><div class="n" style="color:#7eb8f7">{new_count}</div><div class="l">New today</div></div>
    <div class="stat"><div class="n" id="applied-stat">0</div><div class="l">Applied</div></div>
    <div class="stat"><div class="n">{all_remote}</div><div class="l">Remote</div></div>
    <div class="stat"><div class="n">{all_high}</div><div class="l">Score 7+</div></div>
  </div>
</header>
<div class="run-bar">
  <span>Last run: <strong>{run_ts}</strong></span>
  <span>New this run: <strong>{run_count}</strong></span>
  <span>Total in pipeline: <strong>{total}</strong></span>
</div>
<div class="controls">
  <input type="text" id="search" placeholder="Search role, company, location...">
  <select id="filter-score">
    <option value="0">All scores</option>
    <option value="8">8+ Top match</option>
    <option value="7">7+ Strong match</option>
    <option value="6">6+ Good match</option>
  </select>
  <select id="filter-remote">
    <option value="all">All locations</option>
    <option value="remote">Remote only</option>
    <option value="onsite">On-site only</option>
  </select>
  <select id="filter-source">
    <option value="all">All sources</option>
    <option value="linkedin">LinkedIn</option>
    <option value="indeed">Indeed</option>
    <option value="glassdoor">Glassdoor</option>
    <option value="google">Google Jobs</option>
    <option value="greenhouse">Greenhouse</option>
    <option value="ashby">Ashby</option>
    <option value="lever">Lever</option>
    <option value="arbeitsagentur">Arbeitsagentur</option>
    <option value="arbeitnow">Arbeitnow</option>
    <option value="stepstone">StepStone</option>
    <option value="company-crawl">Company Crawl</option>
  </select>
  <select id="filter-new">
    <option value="all">All jobs</option>
    <option value="new">New only</option>
    <option value="old">Previous only</option>
  </select>
  <select id="filter-applied">
    <option value="all">All statuses</option>
    <option value="unapplied">Not applied</option>
    <option value="applied">Applied only</option>
  </select>
  <select id="filter-nl-sponsor">
    <option value="all">All (NL sponsor filter)</option>
    <option value="sponsor">NL: IND-confirmed sponsor only</option>
  </select>
  <select id="filter-country">
    <option value="all">All countries</option>
  </select>
  <span class="count-badge" id="visible-count">— jobs</span>
</div>
<div class="table-wrap">
  <table id="jobs-table">
    <thead>
      <tr>
        <th>#</th>
        <th>Score</th>
        <th>Company</th>
        <th>Role</th>
        <th>Location</th>
        <th>Posted</th>
        <th>Type</th>
        <th>Source</th>
        <th>Docs</th>
        <th>Actions</th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>
  <div class="no-results" id="no-results" style="display:none">No jobs match your filters.</div>
</div>
<footer>career-ops-plugin · python-jobspy · LinkedIn &amp; Indeed Germany · Applied status saved in browser</footer>
<script>
const APPLIED_KEY = "career_ops_applied_v1";

function loadApplied() {{
  try {{ return new Set(JSON.parse(localStorage.getItem(APPLIED_KEY) || "[]")); }}
  catch {{ return new Set(); }}
}}
function saveApplied(set) {{
  localStorage.setItem(APPLIED_KEY, JSON.stringify([...set]));
}}

let appliedSet = loadApplied();

function toggleApplied(url) {{
  if (appliedSet.has(url)) appliedSet.delete(url);
  else appliedSet.add(url);
  saveApplied(appliedSet);
  updateAppliedStat();
  applyFilters();
}}

function updateAppliedStat() {{
  document.getElementById("applied-stat").textContent = appliedSet.size;
}}

function scoreClass(s) {{
  return s>=9?"s9":s>=8?"s8":s>=7?"s7":s>=6?"s6":s>=5?"s5":"s4";
}}

function srcBadge(s) {{
  if (s==="linkedin")      return ["bli","LinkedIn"];
  if (s==="indeed")        return ["bin","Indeed"];
  if (s==="glassdoor")     return ["bgl","Glassdoor"];
  if (s==="google")        return ["bgo","Google Jobs"];
  if (s==="greenhouse")    return ["bgr","Greenhouse"];
  if (s==="ashby")         return ["blv","Ashby"];
  if (s==="lever")         return ["blv","Lever"];
  if (s==="arbeitsagentur") return ["bba","Arbeit"];
  if (s==="arbeitnow")     return ["ban","Arbeitnow"];
  if (s==="stepstone")     return ["bss","StepStone"];
  if (s==="company-crawl") return ["bcc","Company Crawl"];
  return ["bo", s];
}}

// Jobs sorted: new first (by score desc), then old (by score desc)
const ALL_JOBS = {js_array(sorted_jobs)};

function render(data) {{
  const tbody = document.getElementById("tbody");
  document.getElementById("stat-shown").textContent = data.length;
  if (!data.length) {{
    tbody.innerHTML = "";
    document.getElementById("no-results").style.display = "block";
    document.getElementById("jobs-table").style.display = "none";
    return;
  }}
  document.getElementById("no-results").style.display = "none";
  document.getElementById("jobs-table").style.display = "table";

  let html = "";
  let shownNew = false, shownOld = false;

  data.forEach((j, idx) => {{
    const isApplied = appliedSet.has(j.url);
    const [sc, sl] = srcBadge(j.source);
    const applyClass = j.source==="linkedin"?"linkedin":j.source==="indeed"?"indeed":j.source==="greenhouse"?"greenhouse":j.source==="arbeitsagentur"?"arbeitsagentur":"";

    // Section dividers
    if (j.isNew && !shownNew) {{
      shownNew = true;
      html += `<tr class="separator-row"><td colspan="10">&#9733; New from latest run ({new_count} jobs)</td></tr>`;
    }}
    if (!j.isNew && !shownOld) {{
      shownOld = true;
      html += `<tr class="separator-row"><td colspan="10">Previous runs ({total - new_count} jobs)</td></tr>`;
    }}

    html += `<tr class="${{isApplied?"applied":""}} ${{j.isNew?"is-new":""}}">
      <td style="color:#999;font-size:11px">${{idx+1}}</td>
      <td>
        <span class="score ${{scoreClass(j.score)}}">${{j.score}}/10</span>
        ${{j.isNew?'<span class="badge bnew" style="margin-left:3px">NEW</span>':''}}
      </td>
      <td class="company">${{j.company}}</td>
      <td class="role">${{j.role}}</td>
      <td class="location">${{j.location}}${{j.nlSponsor===true?' <span class="badge bnl-yes" title="IND-recognized sponsor — can sponsor a work/highly-skilled-migrant visa">IND Sponsor ✓</span>':''}}${{j.nlSponsor===false?' <span class="badge bnl-no" title="Not found in the IND recognized-sponsor register">Not IND-listed</span>':''}}</td>
      <td class="posted">${{j.posted}}</td>
      <td><span class="badge ${{j.remote?"br":"bo"}}">${{j.remote?"Remote":"On-site"}}</span></td>
      <td><span class="badge ${{sc}}">${{sl}}</span></td>
      <td>
        ${{j.resumeDoc?`<a class="btn-doc resume" href="${{j.resumeDoc}}" target="_blank" rel="noopener">Resume</a>`:''}}
        ${{j.coverDoc?`<a class="btn-doc cover" href="${{j.coverDoc}}" target="_blank" rel="noopener">Cover Letter</a>`:''}}
        ${{!j.resumeDoc && !j.coverDoc?'<span style="color:#bbb;font-size:11px">—</span>':''}}
      </td>
      <td>
        <a class="btn-apply ${{applyClass}}" href="${{j.url}}" target="_blank" rel="noopener">Apply</a>
        <button class="btn-done ${{isApplied?"applied":""}}" onclick="toggleApplied('${{j.url}}')">${{isApplied?"Applied ✓":"Mark Applied"}}</button>
      </td>
    </tr>`;
  }});

  tbody.innerHTML = html;
  document.getElementById("visible-count").textContent = `${{data.length}} job${{data.length!==1?"s":""}}`;
}}

function applyFilters() {{
  const q        = document.getElementById("search").value.toLowerCase();
  const minScore = parseInt(document.getElementById("filter-score").value) || 0;
  const remFilt  = document.getElementById("filter-remote").value;
  const srcFilt  = document.getElementById("filter-source").value;
  const newFilt  = document.getElementById("filter-new").value;
  const appFilt  = document.getElementById("filter-applied").value;
  const nlFilt   = document.getElementById("filter-nl-sponsor").value;
  const ctryFilt = document.getElementById("filter-country").value;

  render(ALL_JOBS.filter(j => {{
    const text = (j.company + " " + j.role + " " + j.location).toLowerCase();
    if (q && !text.includes(q)) return false;
    if (j.score < minScore) return false;
    if (remFilt === "remote" && !j.remote) return false;
    if (remFilt === "onsite" && j.remote) return false;
    if (srcFilt !== "all" && j.source !== srcFilt) return false;
    if (newFilt === "new" && !j.isNew) return false;
    if (newFilt === "old" && j.isNew) return false;
    if (appFilt === "unapplied" && appliedSet.has(j.url)) return false;
    if (appFilt === "applied" && !appliedSet.has(j.url)) return false;
    if (nlFilt === "sponsor" && j.nlSponsor !== true) return false;
    if (ctryFilt !== "all" && j.country !== ctryFilt) return false;
    return true;
  }}));
}}

function populateCountryFilter() {{
  const sel = document.getElementById("filter-country");
  const counts = {{}};
  ALL_JOBS.forEach(j => {{ counts[j.country] = (counts[j.country] || 0) + 1; }});
  Object.keys(counts).sort((a, b) => counts[b] - counts[a]).forEach(country => {{
    const opt = document.createElement("option");
    opt.value = country;
    opt.textContent = `${{country}} (${{counts[country]}})`;
    sel.appendChild(opt);
  }});
}}

updateAppliedStat();
populateCountryFilter();
["search","filter-score","filter-remote","filter-source","filter-new","filter-applied","filter-nl-sponsor","filter-country"]
  .forEach(id => document.getElementById(id).addEventListener("input", applyFilters));
applyFilters();
</script>
</body>
</html>"""


def main():
    since    = None
    show_all = False
    country  = None
    output   = OUTPUT_PATH
    for arg in sys.argv[1:]:
        if arg.startswith("--since="):
            since = arg.split("=", 1)[1]
        elif arg == "--all":
            show_all = True
        elif arg.startswith("--country="):
            country = arg.split("=", 1)[1]
        elif arg.startswith("--output="):
            output = Path(arg.split("=", 1)[1])

    print("Parsing pipeline.md...")
    jobs = parse_pipeline()
    print(f"Found {len(jobs)} jobs total")

    if since:
        jobs = [j for j in jobs if j["date_found"] >= since]
        print(f"Filtered to jobs found on/after {since}: {len(jobs)}")

    if country:
        jobs = [j for j in jobs if country.lower() in j["location"].lower()]
        print(f"Filtered to jobs located in {country}: {len(jobs)}")

    run_info = load_last_run()

    if run_info:
        last_run_urls = set(run_info.get("urls", []))
        print(f"Last run: {run_info['date']} · {run_info['count']} new jobs")
        for j in jobs:
            j["is_new"] = j["url"] in last_run_urls
    else:
        print("No run state found — marking today's jobs as new")
        today = date.today().isoformat()
        for j in jobs:
            j["is_new"] = j["date_found"] == today

    # Default: dashboard shows only the latest run's new roles, newest first.
    # Pass --all, --since, or --country to render a broader slice instead.
    if not show_all and not since and not country:
        jobs = [j for j in jobs if j["is_new"]]
        print(f"Showing new roles only from the latest run: {len(jobs)}")

    app_entries = parse_applications()
    attach_docs(jobs, app_entries)
    docs_count = sum(1 for j in jobs if j["resume_doc"] or j["cover_doc"])
    print(f"Matched {docs_count} job(s) to a ready resume/cover letter in applications.md")

    attach_country(jobs)

    attach_nl_sponsor_status(jobs)
    nl_count = sum(1 for j in jobs if j["nl_sponsor"] is not None)
    if nl_count:
        verified = sum(1 for j in jobs if j["nl_sponsor"])
        print(f"Checked {nl_count} Netherlands job(s) against the IND sponsor register: {verified} confirmed sponsors")

    jobs.sort(key=lambda j: j["date_found"], reverse=True)

    html = generate_html(jobs, run_info, country_label=country)
    output.write_text(html, encoding="utf-8")
    print(f"Dashboard written to {output}")


if __name__ == "__main__":
    main()
