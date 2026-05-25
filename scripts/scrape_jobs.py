"""
Job scraper for career-ops-plugin.
Searches LinkedIn and Indeed for matching roles in Germany,
scores them against the profile, deduplicates against applications.md,
and appends new matches to data/pipeline.md.
"""

import sys
import re
import csv
import json
import yaml
import warnings
import requests
from datetime import date, datetime, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
PROFILE_PATH   = ROOT / "data" / "profile.yml"
APPS_PATH      = ROOT / "data" / "applications.md"
PIPELINE_PATH  = ROOT / "data" / "pipeline.md"
LAST_RUN_PATH  = ROOT / "data" / ".last-run.json"
CAREERS_CSV    = ROOT / "data" / "workinglinks.csv"

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
    """Collect URLs already in applications.md and pipeline.md.
    Only URL-based dedup against history — pair dedup runs only within
    the current session to avoid blocking new postings from known companies.
    """
    urls = set()

    for path in [APPS_PATH, PIPELINE_PATH]:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            for url in re.findall(r'\(https?://[^\)]+\)', line):
                urls.add(url.strip("()").lower())

    return urls

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

_TITLE_MUST_HAVE = {
    "data", "analytics", "analytic", "lakehouse", "warehouse",
    "etl", "elt", "dbt", "snowflake", "pipeline", "dataops",
}

def score_job(title: str, description: str, profile: dict) -> int:
    """Score 0–10: title match (0-4) + skill overlap (0-4) + seniority (0-2)."""
    title_lc = title.lower()
    text = (title + " " + (description or "")).lower()
    score = 0

    # Hard gate: title must contain at least one data-domain keyword
    if not any(kw in title_lc for kw in _TITLE_MUST_HAVE):
        return 0

    # title match against target roles (full phrase, not any single word)
    target_roles = [profile["target"]["primary_role"]] + profile["target"].get("secondary_roles", [])
    for role in target_roles:
        if role.lower() in title_lc:
            score += 3
            break
    if "data engineer" in title_lc or "analytics engineer" in title_lc:
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

# ── company career board scraping ──────────────────────────────────────────

# Job board URLs to skip (covered by jobspy or not scrapeable)
_SKIP_PATTERNS = [
    "linkedin.com", "indeed.com", "glassdoor", "stepstone.de", "xing.com",
    "monster.com", "arbeitsagentur.de", "talent.com", "jobsinmunich.com",
    "jobware.de", "stellenanzeigen.de", "englishjobs.de", "yourenglishjob.com",
    "english-jobs.com", "thelocal.com", "expatica.com", "arbeitnow.com",
    "berlinstartupjobs.com", "wellfound.com", "welcometothejungle.com",
    "landing.jobs", "nofluffjobs.com", "weworkremotely.com", "remoteok.com",
    "remotive.com", "flexjobs.com", "justremote.co", "builtin.com",
    "dice.com", "lhh.com", "hays.de", "michaelpage.de", "robertwalters.de",
    "randstad.de", "adecco.com", "www.ashbyhq.com/careers", "my.greenhouse.io",
]

_DE_CITIES = {
    "germany", "deutschland", "berlin", "munich", "münchen", "hamburg",
    "frankfurt", "cologne", "köln", "düsseldorf", "freiburg", "stuttgart",
    "dresden", "leipzig", "nuremberg", "nürnberg", "bonn", "darmstadt",
    "heidelberg", "mannheim", "potsdam", "oldenburg", "mainz", "augsburg",
}

# Locations that signal a non-DE role even when "remote" is also present
_NON_DE_MARKERS = {
    "united states", "united kingdom", "australia", "canada", "malaysia",
    "singapore", "india", "new zealand", "south africa", "brazil",
    "san francisco", "new york", "los angeles", "seattle", "boston",
    "london", "amsterdam", "paris", "sydney", "toronto",
    "remote, us", "remote - us", "us-remote", "remote, usa", "remote - usa",
    "remote (us", "remote (united", "remote-friendly, us",
}

def _is_de_location(loc: str) -> bool:
    """True only if: no location specified, explicitly Germany, or purely global remote.
    ATS boards return all open roles worldwide — be strict so non-DE roles don't leak in."""
    if not loc or not loc.strip():
        return True
    loc_lc = loc.lower()
    # Explicit German city/country
    if any(k in loc_lc for k in _DE_CITIES):
        return True
    # Pure global-remote phrases with no country qualifier
    if loc_lc.strip() in {"remote", "anywhere", "worldwide", "global", "remote-friendly",
                           "fully remote", "100% remote", "distributed"}:
        return True
    # Everything else (Dublin, London, Paris, "Remote - US", etc.) → exclude
    return False

def load_career_sources():
    """Parse workinglinks.csv → Greenhouse company slugs.
    Ashby (client-rendered SPA, API auth-only) and Workable (API auth-only) are
    skipped — their companies post on LinkedIn/Indeed and are caught by jobspy.
    """
    greenhouse = []
    if not CAREERS_CSV.exists():
        return greenhouse

    with open(CAREERS_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row.get("Company / Portal", "").strip()
            url  = row.get("Site Link", "").strip()
            if not url or not name:
                continue
            url_lc = url.lower()
            if any(p in url_lc for p in _SKIP_PATTERNS):
                continue
            if "greenhouse.io/" in url_lc:
                slug = url.split("greenhouse.io/")[-1].split("/")[0].split("?")[0]
                if slug:
                    greenhouse.append((name, slug))
            # Ashby/Workable/company-specific pages: captured via LinkedIn/Indeed

    return greenhouse


def scrape_company_boards(profile, seen_urls, tracked_pairs):
    """Scrape Greenhouse ATS boards listed in workinglinks.csv."""
    greenhouse_list = load_career_sources()

    if not greenhouse_list:
        return []

    results = []

    # ATS boards return ALL open roles — require an explicit data/engineering keyword
    # in the title (no description to score against)
    _ATS_TITLE_KW = {
        "data", "analytics", "analyst", "pipeline", "warehouse", "lakehouse",
        "etl", "elt", "spark", "platform engineer", "data engineer",
        "machine learning", "ml engineer", "ai engineer", "cloud engineer",
        "infrastructure", "dataops", "devops", "architect", "dbt", "snowflake",
    }

    def _add(title, company, location, url, posted, source, desc=""):
        if not title or not url:
            return
        # ATS: reject roles with no data/engineering keyword in the title
        title_lc = title.lower()
        if not any(kw in title_lc for kw in _ATS_TITLE_KW):
            return
        url_key = url.lower()
        if url_key in seen_urls:
            return
        seen_urls.add(url_key)
        pair = (company.lower(), normalize_title(title))
        if pair in tracked_pairs:
            return
        tracked_pairs.add(pair)
        if is_excluded(title):
            return
        score = score_job(title, desc, profile)
        if score < 5:
            return
        results.append({
            "title":       title,
            "company":     company,
            "location":    location or "—",
            "score":       score,
            "job_url":     url,
            "is_remote":   "remote" in (location or "").lower(),
            "source":      source,
            "date_posted": posted or "—",
        })

    _HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; career-ops-bot/1.0)"}

    # ── Greenhouse ──────────────────────────────────────────────────────────
    print(f"\n>> Checking {len(greenhouse_list)} Greenhouse boards...")
    for company_name, slug in greenhouse_list:
        try:
            resp = requests.get(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                headers=_HEADERS, timeout=10,
            )
            if resp.status_code != 200:
                continue
            for job in resp.json().get("jobs", []):
                title  = job.get("title", "").strip()
                url    = job.get("absolute_url", "").strip()
                loc    = (job.get("location") or {}).get("name", "").strip()
                posted = (job.get("updated_at") or "")[:10]
                if not _is_de_location(loc):
                    continue
                _add(title, company_name, loc, url, posted, "greenhouse")
        except Exception as e:
            print(f"   [WARN] Greenhouse {slug}: {e}")

    return results


# ── Arbeitsagentur (German Federal Employment Agency) ──────────────────────

_BA_BASE    = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
_BA_HEADERS = {"User-Agent": "Mozilla/5.0", "X-API-Key": "jobboerse-jobsuche"}

def scrape_arbeitsagentur(profile, seen_urls, tracked_pairs, days_old: int = 7):
    """Query the Bundesagentur für Arbeit public REST API (no auth required)."""
    results = []
    cutoff  = (date.today() - timedelta(days=days_old)).isoformat()

    search_terms = [
        profile["target"]["primary_role"],
        "Data Analytics Engineer",
        "Analytics Engineer",
        "Cloud Data Engineer",
        "Data Architect",
    ]

    print(f"\n>> Arbeitsagentur: searching {len(search_terms)} terms (last {days_old} days)...")

    for term in search_terms:
        try:
            resp = requests.get(
                _BA_BASE,
                params={"was": term, "wo": "Deutschland", "angebotsart": 1,
                        "page": 1, "size": 25},
                headers=_BA_HEADERS,
                timeout=15,
            )
            if resp.status_code != 200:
                print(f"   [WARN] Arbeitsagentur '{term}': HTTP {resp.status_code}")
                continue

            for job in resp.json().get("stellenangebote", []):
                pub = job.get("aktuelleVeroeffentlichungsdatum", "")
                if pub and pub < cutoff:
                    continue                # skip older than days_old

                title   = job.get("titel", "").strip()
                company = job.get("arbeitgeber", "").strip()
                refnr   = job.get("refnr", "")
                url     = f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"
                ort     = job.get("arbeitsort", {})
                city    = ort.get("ort") or ort.get("region") or "Germany"
                loc     = f"{city}, Germany" if city != "Germany" else "Germany"

                if not title or not refnr:
                    continue
                if is_excluded(title):
                    continue

                url_key = url.lower()
                if url_key in seen_urls:
                    continue
                seen_urls.add(url_key)

                pair = (company.lower(), normalize_title(title))
                if pair in tracked_pairs:
                    continue
                tracked_pairs.add(pair)

                score = score_job(title, "", profile)
                if score < 4:
                    continue

                results.append({
                    "title":       title,
                    "company":     company,
                    "location":    loc,
                    "score":       score,
                    "job_url":     url,
                    "is_remote":   "remote" in title.lower(),
                    "source":      "arbeitsagentur",
                    "date_posted": pub or "—",
                })

        except Exception as e:
            print(f"   [WARN] Arbeitsagentur '{term}': {e}")

    if results:
        print(f"   + {len(results)} from Arbeitsagentur")
    return results

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
    tracked_urls = load_tracked_urls()
    session_pairs = set()   # within-run pair dedup only (catches same job on LinkedIn+Indeed)

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

                # dedup by URL (against history + current session)
                url_key = url.lower()
                if url_key in seen_urls:
                    continue
                seen_urls.add(url_key)

                # within-session pair dedup: catches same job on LinkedIn AND Indeed
                pair = (company.lower(), normalize_title(title))
                if pair in session_pairs:
                    continue
                session_pairs.add(pair)

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

    # ── company ATS boards (Greenhouse) ─────────────────────────────────────
    board_jobs = scrape_company_boards(profile, seen_urls, session_pairs)
    if board_jobs:
        all_jobs.extend(board_jobs)
        print(f"   + {len(board_jobs)} from company ATS boards")

    # ── Bundesagentur für Arbeit ─────────────────────────────────────────────
    ba_jobs = scrape_arbeitsagentur(profile, seen_urls, session_pairs, days_old=7)
    all_jobs.extend(ba_jobs)

    # sort by score desc
    all_jobs.sort(key=lambda x: x["score"], reverse=True)

    print(f"\n{'='*60}")
    print(f"SCRAPE COMPLETE — {len(all_jobs)} new matching jobs found")
    print(f"{'='*60}\n")

    # always save run state so dashboard knows what's current
    state = {
        "date": date.today().isoformat(),
        "timestamp": datetime.now().isoformat(),
        "count": len(all_jobs),
        "urls": [j["job_url"] for j in all_jobs],
    }
    LAST_RUN_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

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
