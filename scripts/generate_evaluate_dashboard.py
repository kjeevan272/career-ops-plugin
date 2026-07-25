"""
Generate data/evaluate-dashboard.html — a skill-gap review dashboard.

Reads data/evaluate-jobs.json (a list of {title, company, location, url,
score, jd_text}), runs skill_match.analyze_job_skills() against each using
data/profile.yml, and renders a dashboard showing per-job: fit %, matched
skills, gap skills — so you can eyeball which roles are actually worth
tailoring a resume for before spending the effort.

evaluate-jobs.json is currently populated manually (via WebFetch on job
postings, since that's a Claude-only tool, not something this script can do
unsupervised) — ask Claude to "refresh the evaluate dashboard" to repopulate
it from your saved LinkedIn search and regenerate.

Run: python scripts/generate_evaluate_dashboard.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scrape_jobs import load_profile
from skill_match import analyze_job_skills

ROOT        = Path(__file__).parent.parent
JOBS_PATH   = ROOT / "data" / "evaluate-jobs.json"
OUTPUT_PATH = ROOT / "data" / "evaluate-dashboard.html"


def escape(s):
    return (s or "").replace("\\", "\\\\").replace("`", "\\`").replace("'", "\\'").replace('"', '\\"')


def js_array(jobs):
    rows = []
    for i, j in enumerate(jobs, 1):
        rows.append(
            "  {" +
            f"n:{i}," +
            f'company:"{escape(j["company"])}",' +
            f'role:"{escape(j["title"])}",' +
            f'location:"{escape(j["location"])}",' +
            f'url:"{escape(j["url"])}",' +
            f'score:{j.get("score", 0)},' +
            f'fitPct:{j["skills"]["fit_pct"]},' +
            f'matched:{json.dumps(j["skills"]["matched"])},' +
            f'gaps:{json.dumps(j["skills"]["gaps"])},' +
            f'langFlag:{json.dumps(j.get("language_flag"))}' +
            "}"
        )
    return "[\n" + ",\n".join(rows) + "\n]"


def generate_html(jobs):
    total = len(jobs)
    strong = sum(1 for j in jobs if j["skills"]["fit_pct"] >= 70)
    avg_fit = round(sum(j["skills"]["fit_pct"] for j in jobs) / total, 1) if total else 0
    blocked = sum(1 for j in jobs if (j.get("language_flag") or "").startswith("HARD BLOCK"))

    # Language hard-blocks sink to the bottom regardless of tech fit % —
    # a 90% skill match is irrelevant if the language requirement disqualifies
    # you outright, so this shouldn't visually compete with genuinely viable roles.
    def _sort_key(j):
        is_blocked = (j.get("language_flag") or "").startswith("HARD BLOCK")
        return (is_blocked, -j["skills"]["fit_pct"])

    sorted_jobs = sorted(jobs, key=_sort_key)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Evaluate Dashboard — Jeevan Kumar Kondasingu</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;background:#f0f2f5;color:#1a1a1a;font-size:14px}}
    header{{background:#1a1a2e;color:#fff;padding:18px 28px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}}
    header h1{{font-size:18px;font-weight:700}}
    header p{{font-size:12px;color:#aab;margin-top:3px}}
    .stats{{display:flex;gap:20px}}
    .stat .n{{font-size:26px;font-weight:700;color:#7eb8f7}}
    .stat .l{{font-size:11px;color:#99a;text-transform:uppercase}}
    .note{{background:#fef9c3;border-bottom:1px solid #eab308;padding:8px 28px;font-size:12px;color:#713f12}}
    .cards{{padding:20px 28px;display:flex;flex-direction:column;gap:14px}}
    .card{{background:#fff;border-radius:10px;box-shadow:0 1px 4px rgba(0,0,0,.08);padding:18px 20px}}
    .card-head{{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:10px;margin-bottom:10px}}
    .card-title{{font-size:16px;font-weight:700}}
    .card-sub{{font-size:12px;color:#666;margin-top:2px}}
    .fit-badge{{display:inline-flex;flex-direction:column;align-items:center;justify-content:center;width:64px;height:64px;border-radius:50%;color:#fff;font-weight:700}}
    .fit-badge .pct{{font-size:16px}}
    .fit-badge .lbl{{font-size:9px;text-transform:uppercase;opacity:.85}}
    .fit-high{{background:#1a7f37}}
    .fit-mid{{background:#cf6d17}}
    .fit-low{{background:#b91c1c}}
    .skills-row{{display:flex;gap:24px;flex-wrap:wrap;margin-top:10px}}
    .skills-col{{flex:1;min-width:220px}}
    .skills-col h4{{font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:#666;margin-bottom:6px}}
    .chip{{display:inline-block;padding:3px 9px;border-radius:12px;font-size:12px;margin:2px 3px 2px 0}}
    .chip-match{{background:#d1fae5;color:#065f46}}
    .chip-gap{{background:#fee2e2;color:#991b1b}}
    .card-actions{{margin-top:12px;display:flex;gap:8px;align-items:center}}
    .btn-apply{{display:inline-block;padding:6px 14px;background:#1a73e8;color:#fff;border-radius:6px;font-size:12px;font-weight:600;text-decoration:none}}
    .btn-apply:hover{{background:#1557b0}}
    .no-gaps{{color:#999;font-size:12px;font-style:italic}}
    .lang-flag{{margin-top:10px;padding:8px 12px;border-radius:6px;font-size:12px;font-weight:600}}
    .lang-block{{background:#fee2e2;color:#991b1b;border:1px solid #fca5a5}}
    .lang-risk{{background:#fef3c7;color:#92400e;border:1px solid #fcd34d}}
    .card.is-blocked{{opacity:.72}}
    footer{{text-align:center;padding:16px;color:#999;font-size:12px}}
    .filters{{display:flex;gap:10px;flex-wrap:wrap;align-items:center;padding:14px 28px;background:#fff;border-bottom:1px solid #e0e0e0}}
    .filters input, .filters select{{padding:6px 10px;border:1px solid #ccc;border-radius:6px;font-size:13px}}
    .filters input{{flex:1;min-width:200px}}
    #no-results{{display:none;text-align:center;padding:40px;color:#999}}
    #visible-count{{font-size:12px;color:#666;margin-left:auto}}
  </style>
</head>
<body>
<header>
  <div>
    <h1>Evaluate Dashboard — Skill Gap Review</h1>
    <p>LinkedIn / European Union / Data Engineer — matched against your actual stack</p>
  </div>
  <div class="stats">
    <div class="stat"><div class="n">{total}</div><div class="l">Evaluated</div></div>
    <div class="stat"><div class="n">{strong}</div><div class="l">Strong fit (70%+)</div></div>
    <div class="stat"><div class="n">{avg_fit}%</div><div class="l">Avg fit</div></div>
    <div class="stat"><div class="n" style="color:#f87171">{blocked}</div><div class="l">Language blocked</div></div>
  </div>
</header>
<div class="note">
  Populated by the evaluate skill after each job evaluation (or manually via "refresh the evaluate dashboard"). Fit % is matched-vs-gap skill keyword coverage, not a full evaluation — use it to triage which roles are worth a full tailored resume.
</div>
<div class="filters">
  <input type="text" id="search" placeholder="Search role or company...">
  <select id="filter-fit">
    <option value="0">Any fit %</option>
    <option value="70">70%+ fit</option>
    <option value="45">45%+ fit</option>
  </select>
  <select id="filter-score">
    <option value="0">Any score</option>
    <option value="7">7+/10</option>
    <option value="5">5+/10</option>
  </select>
  <select id="filter-lang">
    <option value="all">All (incl. language-blocked)</option>
    <option value="hide-blocked">Hide language-blocked</option>
    <option value="only-blocked">Only language-blocked</option>
  </select>
  <span id="visible-count"></span>
</div>
<div class="cards" id="cards"></div>
<div id="no-results">No evaluations match these filters.</div>
<footer>career-ops-plugin · skill_match.py · Fit % = matched / (matched + gaps) keyword coverage</footer>
<script>
const JOBS = {js_array(sorted_jobs)};

function fitClass(pct) {{
  return pct >= 70 ? "fit-high" : pct >= 45 ? "fit-mid" : "fit-low";
}}

function applyFilters() {{
  const q        = document.getElementById("search").value.trim().toLowerCase();
  const minFit   = parseInt(document.getElementById("filter-fit").value) || 0;
  const minScore = parseInt(document.getElementById("filter-score").value) || 0;
  const langFilt = document.getElementById("filter-lang").value;

  const filtered = JOBS.filter(j => {{
    const text = (j.company + " " + j.role).toLowerCase();
    if (q && !text.includes(q)) return false;
    if (j.fitPct < minFit) return false;
    if (j.score < minScore) return false;
    const isBlocked = j.langFlag && j.langFlag.startsWith("HARD BLOCK");
    if (langFilt === "hide-blocked" && isBlocked) return false;
    if (langFilt === "only-blocked" && !isBlocked) return false;
    return true;
  }});

  document.getElementById("visible-count").textContent = `${{filtered.length}} of ${{JOBS.length}} shown`;
  render(filtered);
}}

function render(jobs) {{
  const container = document.getElementById("cards");
  const noResults = document.getElementById("no-results");
  if (!jobs.length) {{
    container.style.display = "none";
    noResults.style.display = "block";
    return;
  }}
  container.style.display = "flex";
  noResults.style.display = "none";
  container.innerHTML = jobs.map(j => {{
    const isBlocked = j.langFlag && j.langFlag.startsWith("HARD BLOCK");
    const isRisk = j.langFlag && !isBlocked;
    return `
    <div class="card ${{isBlocked ? 'is-blocked' : ''}}">
      <div class="card-head">
        <div>
          <div class="card-title">${{j.role}} — ${{j.company}}</div>
          <div class="card-sub">${{j.location}} · Scraper score ${{j.score}}/10</div>
        </div>
        <div class="fit-badge ${{fitClass(j.fitPct)}}">
          <span class="pct">${{j.fitPct}}%</span>
          <span class="lbl">tech fit</span>
        </div>
      </div>
      ${{j.langFlag ? `<div class="lang-flag ${{isBlocked ? 'lang-block' : 'lang-risk'}}">${{isBlocked ? '⛔' : '⚠️'}} ${{j.langFlag}}</div>` : ''}}
      <div class="skills-row">
        <div class="skills-col">
          <h4>Matched (${{j.matched.length}})</h4>
          ${{j.matched.length ? j.matched.map(s => `<span class="chip chip-match">${{s}}</span>`).join("") : '<span class="no-gaps">None detected</span>'}}
        </div>
        <div class="skills-col">
          <h4>Gaps (${{j.gaps.length}})</h4>
          ${{j.gaps.length ? j.gaps.map(s => `<span class="chip chip-gap">${{s}}</span>`).join("") : '<span class="no-gaps">No gaps detected</span>'}}
        </div>
      </div>
      <div class="card-actions">
        <a class="btn-apply" href="${{j.url}}" target="_blank" rel="noopener">View posting</a>
      </div>
    </div>
  `;
  }}).join("");
}}

["search","filter-fit","filter-score","filter-lang"]
  .forEach(id => document.getElementById(id).addEventListener("input", applyFilters));
applyFilters();
</script>
</body>
</html>"""


def main():
    if not JOBS_PATH.exists():
        print(f"ERROR: {JOBS_PATH} not found. Populate it first (see script docstring).")
        sys.exit(1)

    jobs = json.loads(JOBS_PATH.read_text(encoding="utf-8"))
    profile = load_profile()

    print(f"Analyzing {len(jobs)} jobs against your skill set...")
    for j in jobs:
        j["skills"] = analyze_job_skills(j.get("jd_text", ""), profile)
        print(f"  {j['company']} — {j['title']}: {j['skills']['fit_pct']}% fit "
              f"({len(j['skills']['matched'])} matched, {len(j['skills']['gaps'])} gaps)")

    html = generate_html(jobs)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"\nDashboard written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
