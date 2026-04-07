"""
Generate data/pipeline-dashboard.html from data/pipeline.md
Run: python scripts/generate_dashboard.py
"""

import re
import sys
from pathlib import Path

ROOT          = Path(__file__).parent.parent
PIPELINE_PATH = ROOT / "data" / "pipeline.md"
OUTPUT_PATH   = ROOT / "data" / "pipeline-dashboard.html"

def parse_url(cell):
    m = re.search(r'\(https?://[^\)]+\)', cell)
    return m.group(0).strip("()") if m else ""

def parse_score(cell):
    m = re.search(r'(\d+)', cell)
    return int(m.group(1)) if m else 0

def parse_pipeline():
    if not PIPELINE_PATH.exists():
        print("ERROR: data/pipeline.md not found")
        sys.exit(1)

    jobs = []
    for line in PIPELINE_PATH.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or line.startswith("| Date") or line.startswith("|---"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]

        # detect format by column count
        # old (8 cols): date_found | company | role | score | location | remote | url | status
        # new (10 cols): date_found | posted | company | role | score | location | remote | source | url | status
        if len(cols) >= 10:
            date_found = cols[0]
            posted     = cols[1]
            company    = cols[2]
            role       = cols[3]
            score      = parse_score(cols[4])
            location   = cols[5]
            remote     = cols[6].lower() in ("yes", "✅")
            source     = cols[7].lower()
            url        = parse_url(cols[8])
            status     = cols[9]
        elif len(cols) >= 8:
            date_found = cols[0]
            posted     = "—"
            company    = cols[1]
            role       = cols[2]
            score      = parse_score(cols[3])
            location   = cols[4]
            remote     = cols[5] in ("✅", "Yes", "yes")
            source     = "—"
            url        = parse_url(cols[6])
            status     = cols[7]
        else:
            continue

        if not role or not company or not url:
            continue

        # skip header-like rows
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

def escape(s):
    return s.replace("\\", "\\\\").replace("`", "\\`").replace("'", "\\'").replace('"', '\\"')

def js_array(jobs):
    rows = []
    for i, j in enumerate(jobs, 1):
        src = "linkedin" if "linkedin" in j["source"] else ("indeed" if "indeed" in j["source"] else j["source"])
        rows.append(
            "  {" +
            f"n:{i}," +
            f'score:{j["score"]},' +
            f'company:"{escape(j["company"])}",' +
            f'role:"{escape(j["role"])}",' +
            f'location:"{escape(j["location"])}",' +
            f'remote:{"true" if j["remote"] else "false"},' +
            f'source:"{src}",' +
            f'posted:"{escape(j["posted"])}",' +
            f'dateFound:"{escape(j["date_found"])}",' +
            f'url:"{escape(j["url"])}"' +
            "}"
        )
    return "[\n" + ",\n".join(rows) + "\n]"

def generate_html(jobs):
    total   = len(jobs)
    remote  = sum(1 for j in jobs if j["remote"])
    high    = sum(1 for j in jobs if j["score"] >= 7)
    scraped = jobs[0]["date_found"] if jobs else "—"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Job Pipeline — Jeevan Kumar Kondasingu</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;background:#f0f2f5;color:#1a1a1a;font-size:14px}}
    header{{background:#1a1a2e;color:#fff;padding:18px 28px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}}
    header h1{{font-size:18px;font-weight:700}}
    header p{{font-size:12px;color:#aab;margin-top:3px}}
    .stats{{display:flex;gap:20px}}
    .stat .n{{font-size:26px;font-weight:700;color:#7eb8f7}}
    .stat .l{{font-size:11px;color:#99a;text-transform:uppercase}}
    .controls{{background:#fff;border-bottom:1px solid #e0e0e0;padding:12px 28px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}}
    .controls input,.controls select{{border:1px solid #ccc;border-radius:6px;padding:6px 10px;font-size:13px;outline:none}}
    .controls input{{width:220px}}
    .controls input:focus,.controls select:focus{{border-color:#4a90e2}}
    .count-badge{{margin-left:auto;background:#e8f0fe;color:#1a73e8;padding:4px 12px;border-radius:20px;font-size:13px;font-weight:600}}
    .table-wrap{{padding:16px 28px;overflow-x:auto}}
    table{{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
    thead tr{{background:#1a1a2e;color:#fff}}
    thead th{{padding:10px 12px;text-align:left;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;cursor:pointer;user-select:none;white-space:nowrap}}
    thead th:hover{{background:#2d2d4e}}
    tbody tr{{border-bottom:1px solid #f0f0f0;transition:background .12s}}
    tbody tr:hover{{background:#f7f9ff}}
    tbody tr.applied{{opacity:.4;background:#f9f9f9}}
    tbody tr:last-child{{border-bottom:none}}
    td{{padding:9px 12px;vertical-align:middle}}
    .score{{display:inline-flex;align-items:center;justify-content:center;width:40px;height:24px;border-radius:12px;font-size:11px;font-weight:700;color:#fff}}
    .s9{{background:#1a7f37}}.s8{{background:#2da44e}}.s7{{background:#5ba35b}}.s6{{background:#e3a008}}.s5{{background:#cf6d17}}.s4{{background:#9e6a03}}
    .company{{font-weight:600}}
    .role{{color:#333;max-width:280px;font-size:13px}}
    .badge{{display:inline-block;padding:2px 7px;border-radius:10px;font-size:11px;font-weight:600;white-space:nowrap}}
    .br{{background:#e6f4ea;color:#137333}}.bo{{background:#f1f3f4;color:#666}}
    .bli{{background:#dbeafe;color:#1d4ed8}}.bin{{background:#fef3c7;color:#92400e}}
    .posted{{font-size:11px;color:#888;white-space:nowrap}}
    .location{{color:#555;font-size:12px;max-width:160px}}
    .btn-apply{{display:inline-block;padding:5px 13px;background:#1a73e8;color:#fff;border-radius:6px;font-size:12px;font-weight:600;text-decoration:none;margin-right:4px;transition:background .15s;white-space:nowrap}}
    .btn-apply:hover{{background:#1557b0}}
    .btn-apply.linkedin{{background:#0a66c2}}.btn-apply.linkedin:hover{{background:#084e96}}
    .btn-apply.indeed{{background:#2164f3}}.btn-apply.indeed:hover{{background:#1a4fcf}}
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
    <h1>Job Pipeline — Jeevan Kumar Kondasingu</h1>
    <p>Senior Data Engineer · Munich, Germany · Last scraped {scraped}</p>
  </div>
  <div class="stats">
    <div class="stat"><div class="n">{total}</div><div class="l">Total</div></div>
    <div class="stat"><div class="n" id="applied-stat">0</div><div class="l">Applied</div></div>
    <div class="stat"><div class="n">{remote}</div><div class="l">Remote</div></div>
    <div class="stat"><div class="n">{high}</div><div class="l">Score 7+</div></div>
  </div>
</header>
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
  </select>
  <select id="filter-applied">
    <option value="all">All jobs</option>
    <option value="new">Not applied</option>
    <option value="applied">Applied only</option>
  </select>
  <span class="count-badge" id="visible-count">{total} jobs</span>
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

const jobs = {js_array(jobs)};

function render(data) {{
  const tbody = document.getElementById("tbody");
  if (!data.length) {{
    tbody.innerHTML="";
    document.getElementById("no-results").style.display="block";
    document.getElementById("jobs-table").style.display="none";
  }} else {{
    document.getElementById("no-results").style.display="none";
    document.getElementById("jobs-table").style.display="table";
    const srcClass = s => s==="linkedin"?"bli":s==="indeed"?"bin":"bo";
    tbody.innerHTML = data.map(j => {{
      const isApplied = appliedSet.has(j.url);
      const src = j.source==="linkedin"?"LinkedIn":j.source==="indeed"?"Indeed":j.source;
      return `<tr class="${{isApplied?"applied":""}}">
        <td style="color:#999;font-size:11px">${{j.n}}</td>
        <td><span class="score ${{scoreClass(j.score)}}">${{j.score}}/10</span></td>
        <td class="company">${{j.company}}</td>
        <td class="role">${{j.role}}</td>
        <td class="location">${{j.location}}</td>
        <td class="posted">${{j.posted}}</td>
        <td><span class="badge ${{j.remote?"br":"bo"}}">${{j.remote?"Remote":"On-site"}}</span></td>
        <td><span class="badge ${{srcClass(j.source)}}">${{src}}</span></td>
        <td>
          <a class="btn-apply ${{j.source}}" href="${{j.url}}" target="_blank" rel="noopener">Apply</a>
          <button class="btn-done ${{isApplied?"applied":""}}" onclick="toggleApplied('${{j.url}}')">${{isApplied?"Applied":"Mark Applied"}}</button>
        </td>
      </tr>`;
    }}).join("");
  }}
  document.getElementById("visible-count").textContent = `${{data.length}} job${{data.length!==1?"s":""}}`;
}}

function applyFilters() {{
  const q        = document.getElementById("search").value.toLowerCase();
  const minScore = parseInt(document.getElementById("filter-score").value)||0;
  const remFilt  = document.getElementById("filter-remote").value;
  const srcFilt  = document.getElementById("filter-source").value;
  const appFilt  = document.getElementById("filter-applied").value;

  render(jobs.filter(j => {{
    const text = (j.company+" "+j.role+" "+j.location).toLowerCase();
    if (q && !text.includes(q)) return false;
    if (j.score < minScore) return false;
    if (remFilt==="remote" && !j.remote) return false;
    if (remFilt==="onsite" && j.remote) return false;
    if (srcFilt!=="all" && j.source!==srcFilt) return false;
    if (appFilt==="new" && appliedSet.has(j.url)) return false;
    if (appFilt==="applied" && !appliedSet.has(j.url)) return false;
    return true;
  }}));
}}

updateAppliedStat();
["search","filter-score","filter-remote","filter-source","filter-applied"]
  .forEach(id => document.getElementById(id).addEventListener("input", applyFilters));
render(jobs);
</script>
</body>
</html>"""

def main():
    print("Parsing pipeline.md...")
    jobs = parse_pipeline()
    print(f"Found {len(jobs)} jobs total")

    html = generate_html(jobs)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Dashboard written to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
