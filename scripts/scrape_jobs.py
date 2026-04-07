"""
Job scraper for career-ops-plugin.
Searches LinkedIn and Indeed for matching roles in Germany,
scores them against the profile, deduplicates against applications.md,
and appends new matches to data/pipeline.md.
"""

import sys
import re
import yaml
import warnings
from datetime import date
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
PROFILE_PATH  = ROOT / "data" / "profile.yml"
APPS_PATH     = ROOT / "data" / "applications.md"
PIPELINE_PATH = ROOT / "data" / "pipeline.md"

# ── profile ────────────────────────────────────────────────────────────────

def load_profile():
    with open(PROFILE_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)

# ── dedup ──────────────────────────────────────────────────────────────────

def normalize_title(title: str) -> str:
    """Lowercase, strip gender markers and punctuation for fuzzy dedup."""
    t = title.lower()
    t = re.sub(r'\([^)]*\)', '', t)          # remove (m/f/d), (all genders), etc.
    t = re.sub(r'[^\w\s]', ' ', t)           # strip punctuation
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def load_tracked_urls():
    """Collect URLs already in applications.md and pipeline.md."""
    urls = set()
    companies_roles = set()

    _skip = {"company", "posted", "date found", "---", ""}

    for path in [APPS_PATH, PIPELINE_PATH]:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            # extract markdown links [text](url)
            for url in re.findall(r'\(https?://[^\)]+\)', line):
                urls.add(url.strip("()").lower())
            # extract company|role pairs — handle both pipeline formats:
            #   old (8-col): | Date Found | Company | Role | Score | ...
            #   new (10-col): | Date Found | Posted | Company | Role | Score | ...
            cols = [c.strip() for c in line.split("|")]
            if len(cols) >= 12:          # new 10-column format
                company = cols[3].lower()
                role    = normalize_title(cols[4])
            elif len(cols) >= 10:        # old 8-column format
                company = cols[2].lower()
                role    = normalize_title(cols[3])
            else:
                continue
            if company not in _skip and role:
                companies_roles.add((company, role))

    return urls, companies_roles

# ── scoring ────────────────────────────────────────────────────────────────

SKILL_KEYWORDS = [
    "python", "sql", "pyspark", "spark", "airflow", "kafka", "snowflake",
    "dbt", "aws", "glue", "redshift", "s3", "emr", "kinesis", "databricks",
    "delta lake", "iceberg", "bigquery", "etl", "elt", "data lake",
    "lakehouse", "data warehouse", "streaming", "flink", "cdc",
    "data engineer", "analytics engineer", "data architect",
    "great expectations", "azure", "gcp", "terraform"
]

EXCLUDE_KEYWORDS = [
    "junior", "intern", "internship", "trainee", "werkstudent",
    "student", "apprentice", "graduate program", "entry level"
]

def score_job(title: str, description: str, profile: dict) -> int:
    """Score 0–10: title match (0-4) + skill overlap (0-4) + seniority (0-2)."""
    text = (title + " " + (description or "")).lower()
    score = 0

    # title match against target roles
    target_roles = [profile["target"]["primary_role"]] + profile["target"].get("secondary_roles", [])
    for role in target_roles:
        if any(word.lower() in title.lower() for word in role.split()):
            score += 3
            break
    if "data engineer" in title.lower() or "analytics engineer" in title.lower():
        score += 1

    # skill keyword overlap
    matched = sum(1 for kw in SKILL_KEYWORDS if kw in text)
    score += min(4, matched // 2)

    # seniority signals
    seniority_words = ["senior", "lead", "principal", "staff", "head of", "sr."]
    if any(w in title.lower() for w in seniority_words):
        score += 2
    elif any(w in text for w in seniority_words):
        score += 1

    return min(score, 10)

def is_excluded(title: str) -> bool:
    title_lower = title.lower()
    return any(kw in title_lower for kw in EXCLUDE_KEYWORDS)

# ── pipeline file ──────────────────────────────────────────────────────────

PIPELINE_HEADER = """# Job Pipeline

| Date Found | Posted | Company | Role | Score | Location | Remote | Source | URL | Status |
|---|---|---|---|---|---|---|---|---|---|
"""

def append_to_pipeline(matches: list):
    if not matches:
        return

    if not PIPELINE_PATH.exists():
        PIPELINE_PATH.write_text(PIPELINE_HEADER, encoding="utf-8")

    content = PIPELINE_PATH.read_text(encoding="utf-8")
    if "| Date Found |" not in content:
        content = PIPELINE_HEADER

    today = date.today().isoformat()
    new_rows = []
    for m in matches:
        remote  = "Yes" if m.get("is_remote") else "No"
        url     = m.get("job_url", "")
        posted  = m.get("date_posted", "—")
        source  = m.get("source", "—")
        row = (
            f"| {today} | {posted} | {m['company']} | {m['title']} | "
            f"{m['score']}/10 | {m['location']} | {remote} | {source} | "
            f"[Link]({url}) | New |"
        )
        new_rows.append(row)

    PIPELINE_PATH.write_text(content.rstrip() + "\n" + "\n".join(new_rows) + "\n", encoding="utf-8")
    print(f"\n[OK] Appended {len(new_rows)} new jobs to data/pipeline.md")

# ── main ───────────────────────────────────────────────────────────────────

def main():
    hours_old = 24
    if len(sys.argv) > 1:
        try:
            hours_old = int(sys.argv[1])
        except ValueError:
            pass
    print(f"Loading profile... (hours_old={hours_old})")
    profile = load_profile()

    print("Loading tracked jobs for dedup...")
    tracked_urls, tracked_pairs = load_tracked_urls()

    search_terms = [
        profile["target"]["primary_role"],
        "Data Analytics Engineer",
        "Analytics Engineer",
        "Cloud Data Engineer",
        "Data Architect",
    ]

    try:
        from jobspy import scrape_jobs
    except ImportError:
        print("ERROR: jobspy not installed. Run: pip install python-jobspy")
        sys.exit(1)

    all_jobs = []
    seen_urls = set(tracked_urls)

    for term in search_terms:
        print(f"\n>> Searching: '{term}' in Germany...")
        try:
            df = scrape_jobs(
                site_name=["linkedin", "indeed"],
                search_term=term,
                location="Germany",
                results_wanted=25,
                country_indeed="Germany",
                hours_old=hours_old,
                linkedin_fetch_description=False,
                verbose=0,
            )
            if df is None or df.empty:
                print(f"   No results for '{term}'")
                continue

            print(f"   Found {len(df)} raw results")

            for _, row in df.iterrows():
                title   = str(row.get("title", "")).strip()
                company = str(row.get("company", "")).strip()
                url     = str(row.get("job_url", "")).strip()
                loc     = str(row.get("location", "")).strip()
                desc    = str(row.get("description", "") or "")
                remote  = bool(row.get("is_remote", False))

                if not title or not company:
                    continue

                # dedup by URL
                url_key = url.lower()
                if url_key in seen_urls:
                    continue
                seen_urls.add(url_key)

                # dedup by normalized company+role pair
                pair = (company.lower(), normalize_title(title))
                if pair in tracked_pairs:
                    continue
                tracked_pairs.add(pair)

                # exclude junior/intern
                if is_excluded(title):
                    continue

                # score
                score = score_job(title, desc, profile)
                if score < 4:
                    continue

                posted = row.get("date_posted", None)
                posted_str = str(posted) if posted and str(posted) != "NaT" and str(posted) != "None" else "—"

                all_jobs.append({
                    "title":      title,
                    "company":    company,
                    "location":   loc,
                    "score":      score,
                    "job_url":    url,
                    "is_remote":  remote,
                    "source":     str(row.get("site", "")),
                    "date_posted": posted_str,
                })

        except Exception as e:
            print(f"   [WARN] Error scraping '{term}': {e}")
            continue

    # sort by score desc
    all_jobs.sort(key=lambda x: x["score"], reverse=True)

    print(f"\n{'='*60}")
    print(f"SCRAPE COMPLETE — {len(all_jobs)} new matching jobs found")
    print(f"{'='*60}\n")

    if not all_jobs:
        print("No new matches found. All results were filtered or already tracked.")
        return

    # print table — encode to ASCII with replacement to survive narrow Windows terminals
    def _p(s: str, width: int) -> str:
        return s[:width].encode("ascii", errors="replace").decode("ascii")

    print(f"{'#':<4} {'Score':<7} {'Title':<45} {'Company':<30} {'Location':<20} {'Src'}")
    print("-" * 115)
    for i, job in enumerate(all_jobs, 1):
        title   = _p(job["title"], 43)
        company = _p(job["company"], 28)
        loc     = _p(job["location"], 18)
        remote  = " [remote]" if job["is_remote"] else ""
        print(f"{i:<4} {job['score']}/10   {title:<45} {company:<30} {loc:<20}{remote}  {job['source']}")

    print()
    append_to_pipeline(all_jobs)
    print(f"\nOpen data/pipeline.md to review. Use 'evaluate' on any role to get a full score.")

if __name__ == "__main__":
    main()
