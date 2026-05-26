"""
Job scraper for career-ops-plugin.
Sources: LinkedIn · Indeed · Glassdoor · Google Jobs (via jobspy)
         Greenhouse · Ashby · Lever (ATS direct APIs)
         Bundesagentur für Arbeit · Arbeitnow · StepStone RSS
"""

import sys
import re
import csv
import json
import xml.etree.ElementTree as ET
import yaml
import warnings
import requests
from datetime import date, datetime, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT           = Path(__file__).parent.parent
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
    t = title.lower()
    t = re.sub(r'\([^)]*\)', '', t)
    t = re.sub(r'[^\w\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def load_tracked_urls():
    """Collect URLs already in applications.md and pipeline.md."""
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
    title_lc = title.lower()
    text = (title + " " + (description or "")).lower()
    score = 0
    if not any(kw in title_lc for kw in _TITLE_MUST_HAVE):
        return 0
    target_roles = [profile["target"]["primary_role"]] + profile["target"].get("secondary_roles", [])
    for role in target_roles:
        if role.lower() in title_lc:
            score += 3
            break
    if "data engineer" in title_lc or "analytics engineer" in title_lc:
        score += 1
    matched = sum(1 for kw in SKILL_KEYWORDS if kw in text)
    score += min(4, matched // 2)
    seniority_words = ["senior", "lead", "principal", "staff", "head of", "sr."]
    if any(w in title.lower() for w in seniority_words):
        score += 2
    elif any(w in text for w in seniority_words):
        score += 1
    return min(score, 10)

def is_excluded(title: str) -> bool:
    return any(kw in title.lower() for kw in EXCLUDE_KEYWORDS)

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

# ── location helpers ───────────────────────────────────────────────────────

_SKIP_PATTERNS = [
    "linkedin.com", "indeed.com", "glassdoor", "stepstone.de", "xing.com",
    "monster.com", "arbeitsagentur.de", "talent.com", "jobsinmunich.com",
    "jobware.de", "stellenanzeigen.de", "englishjobs.de", "yourenglishjob.com",
    "english-jobs.com", "thelocal.com", "expatica.com", "arbeitnow.com",
    "berlinstartupjobs.com", "wellfound.com", "welcometothejungle.com",
    "landing.jobs", "nofluffjobs.com", "weworkremotely.com", "remoteok.com",
    "remotive.com", "flexjobs.com", "justremote.co", "builtin.com",
    "dice.com", "lhh.com", "hays.de", "michaelpage.de", "robertwalters.de",
    "randstad.de", "adecco.com", "my.greenhouse.io", "www.ashbyhq.com/careers",
    "apply.workable.com",
]

_DE_CITIES = {
    "germany", "deutschland", "berlin", "munich", "münchen", "hamburg",
    "frankfurt", "cologne", "köln", "düsseldorf", "freiburg", "stuttgart",
    "dresden", "leipzig", "nuremberg", "nürnberg", "bonn", "darmstadt",
    "heidelberg", "mannheim", "potsdam", "oldenburg", "mainz", "augsburg",
    "essen", "dortmund", "hannover", "karlsruhe", "wiesbaden", "münster",
}

_NON_DE_MARKERS = {
    "united states", "united kingdom", "australia", "canada", "malaysia",
    "singapore", "india", "new zealand", "south africa", "brazil",
    "san francisco", "new york", "los angeles", "seattle", "boston",
    "london", "amsterdam", "paris", "sydney", "toronto",
    "remote, us", "remote - us", "us-remote", "remote, usa", "remote - usa",
    "remote (us", "remote (united", "remote-friendly, us",
}

def _is_de_location(loc: str) -> bool:
    if not loc or not loc.strip():
        return True
    loc_lc = loc.lower()
    if any(k in loc_lc for k in _DE_CITIES):
        return True
    if any(k in loc_lc for k in _NON_DE_MARKERS):
        return False
    if loc_lc.strip() in {"remote", "anywhere", "worldwide", "global", "remote-friendly",
                           "fully remote", "100% remote", "distributed", "europe"}:
        return True
    return False

# ── ATS board scraping (Greenhouse · Ashby · Lever) ────────────────────────

def load_career_sources():
    """Parse workinglinks.csv → Greenhouse, Ashby, and Lever company slugs."""
    greenhouse, ashby, lever = [], [], []
    if not CAREERS_CSV.exists():
        return greenhouse, ashby, lever

    with open(CAREERS_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name  = row.get("Company / Portal", "").strip()
            url   = row.get("Site Link", "").strip()
            if not url or not name:
                continue
            url_lc = url.lower()
            if any(p in url_lc for p in _SKIP_PATTERNS):
                continue
            if "greenhouse.io/" in url_lc and "my.greenhouse.io" not in url_lc:
                slug = url.split("greenhouse.io/")[-1].split("/")[0].split("?")[0]
                if slug:
                    greenhouse.append((name, slug))
            elif "jobs.ashbyhq.com/" in url_lc:
                slug = url.split("jobs.ashbyhq.com/")[-1].split("/")[0].split("?")[0]
                if slug:
                    ashby.append((name, slug))
            elif "jobs.lever.co/" in url_lc:
                slug = url.split("jobs.lever.co/")[-1].split("/")[0].split("?")[0]
                if slug:
                    lever.append((name, slug))

    return greenhouse, ashby, lever


def scrape_company_boards(profile, seen_urls, tracked_pairs):
    """Scrape Greenhouse, Ashby, and Lever ATS boards from workinglinks.csv."""
    greenhouse_list, ashby_list, lever_list = load_career_sources()
    results = []

    _ATS_TITLE_KW = {
        "data", "analytics", "analyst", "pipeline", "warehouse", "lakehouse",
        "etl", "elt", "spark", "platform engineer", "data engineer",
        "machine learning", "ml engineer", "ai engineer", "cloud engineer",
        "infrastructure", "dataops", "devops", "architect", "dbt", "snowflake",
    }

    def _add(title, company, location, url, posted, source, desc=""):
        if not title or not url:
            return
        if not any(kw in title.lower() for kw in _ATS_TITLE_KW):
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
    if greenhouse_list:
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

    # ── Ashby ───────────────────────────────────────────────────────────────
    if ashby_list:
        print(f"\n>> Checking {len(ashby_list)} Ashby boards...")
        for company_name, slug in ashby_list:
            try:
                resp = requests.post(
                    "https://api.ashbyhq.com/posting-public/job-board",
                    json={"organizationHostedJobsPageName": slug},
                    headers=_HEADERS, timeout=10,
                )
                if resp.status_code != 200:
                    continue
                for job in resp.json().get("jobPostings", []):
                    title   = job.get("title", "").strip()
                    job_id  = job.get("id", "")
                    url     = job.get("externalLink", "") or f"https://jobs.ashbyhq.com/{slug}/{job_id}"
                    loc_raw = job.get("location") or {}
                    loc     = (loc_raw.get("name", "") if isinstance(loc_raw, dict) else str(loc_raw)).strip()
                    posted  = (job.get("publishedAt") or "")[:10]
                    if not _is_de_location(loc):
                        continue
                    _add(title, company_name, loc, url, posted, "ashby")
            except Exception as e:
                print(f"   [WARN] Ashby {slug}: {e}")

    # ── Lever ───────────────────────────────────────────────────────────────
    if lever_list:
        print(f"\n>> Checking {len(lever_list)} Lever boards...")
        for company_name, slug in lever_list:
            try:
                resp = requests.get(
                    f"https://api.lever.co/v0/postings/{slug}?mode=json",
                    headers=_HEADERS, timeout=10,
                )
                if resp.status_code != 200:
                    continue
                for job in resp.json():
                    title  = job.get("text", "").strip()
                    url    = job.get("hostedUrl", "").strip()
                    cats   = job.get("categories", {})
                    loc    = cats.get("location", "").strip()
                    ts     = job.get("createdAt", 0)
                    posted = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else "—"
                    desc   = job.get("descriptionPlain", "")[:500]
                    if not _is_de_location(loc):
                        continue
                    _add(title, company_name, loc, url, posted, "lever", desc)
            except Exception as e:
                print(f"   [WARN] Lever {slug}: {e}")

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
                    continue

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


# ── Arbeitnow (EU tech board — free public REST API) ───────────────────────

def scrape_arbeitnow(profile, seen_urls, tracked_pairs):
    """Arbeitnow public API — EU/Germany-focused, English-friendly tech jobs."""
    results = []
    print(f"\n>> Arbeitnow: fetching Germany tech jobs...")

    for page in range(1, 4):
        try:
            resp = requests.get(
                "https://www.arbeitnow.com/api/job-board-api",
                params={"page": page},
                headers={"User-Agent": "Mozilla/5.0 (compatible; career-ops-bot/1.0)"},
                timeout=15,
            )
            if resp.status_code != 200:
                break
            jobs = resp.json().get("data", [])
            if not jobs:
                break

            for job in jobs:
                title   = job.get("title", "").strip()
                company = job.get("company_name", "").strip()
                url     = job.get("url", "").strip()
                loc     = job.get("location", "").strip()
                remote  = bool(job.get("remote", False))
                created = job.get("created_at", 0)
                if isinstance(created, int) and created:
                    posted = datetime.fromtimestamp(created).strftime("%Y-%m-%d")
                else:
                    posted = str(created)[:10] if created else "—"
                desc = job.get("description", "")[:500]

                if not title or not company or not url:
                    continue
                if not _is_de_location(loc):
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

                score = score_job(title, desc, profile)
                if score < 4:
                    continue

                results.append({
                    "title":       title,
                    "company":     company,
                    "location":    loc or "Germany",
                    "score":       score,
                    "job_url":     url,
                    "is_remote":   remote,
                    "source":      "arbeitnow",
                    "date_posted": posted,
                })
        except Exception as e:
            print(f"   [WARN] Arbeitnow page {page}: {e}")
            break

    if results:
        print(f"   + {len(results)} from Arbeitnow")
    return results


# ── StepStone RSS (jailbreak via public feed) ──────────────────────────────

def scrape_stepstone_rss(profile, seen_urls, tracked_pairs):
    """StepStone RSS feed — bypasses HTML scraping blocks. Silently skips if gated."""
    results = []
    search_terms = [
        profile["target"]["primary_role"],
        "Data Analytics Engineer",
        "Analytics Engineer",
        "Data Architect",
    ]
    print(f"\n>> StepStone RSS: trying {len(search_terms)} terms...")

    _SS_NS = "http://www.stepstone.de/rss/"

    for term in search_terms:
        try:
            resp = requests.get(
                "https://www.stepstone.de/rss/stellenangebote.html",
                params={"q": term, "where": "Deutschland", "rssid": "0"},
                headers={"User-Agent": "Mozilla/5.0 (compatible; RSS/2.0)"},
                timeout=15,
            )
            if resp.status_code != 200:
                print(f"   [SKIP] StepStone RSS HTTP {resp.status_code} — feed may be gated")
                break

            root = ET.fromstring(resp.content)
            channel = root.find("channel")
            if channel is None:
                continue

            for item in channel.findall("item"):
                title   = (item.findtext("title") or "").strip()
                url     = (item.findtext("link") or "").strip()
                co_el   = item.find(f"{{{_SS_NS}}}company")
                company = co_el.text.strip() if (co_el is not None and co_el.text) else "Unknown"
                loc_el  = item.find(f"{{{_SS_NS}}}location")
                loc     = loc_el.text.strip() if (loc_el is not None and loc_el.text) else "Germany"
                desc    = (item.findtext("description") or "")[:500]
                pub     = (item.findtext("pubDate") or "")[:16]

                if not title or not url:
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

                score = score_job(title, desc, profile)
                if score < 4:
                    continue

                results.append({
                    "title":       title,
                    "company":     company,
                    "location":    loc,
                    "score":       score,
                    "job_url":     url,
                    "is_remote":   "remote" in title.lower() or "remote" in loc.lower(),
                    "source":      "stepstone",
                    "date_posted": pub or "—",
                })

        except ET.ParseError:
            print(f"   [SKIP] StepStone RSS blocked / non-XML for '{term}' — feed may require login")
            break
        except Exception as e:
            print(f"   [WARN] StepStone RSS '{term}': {e}")

    if results:
        print(f"   + {len(results)} from StepStone RSS")
    else:
        print(f"   [INFO] StepStone RSS: 0 results (blocked or feed gated — Google Jobs covers this)")
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
    session_pairs = set()

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

    # ── jobspy: LinkedIn + Indeed + Glassdoor + Google Jobs ─────────────────
    # Google Jobs aggregates StepStone, XING, and hundreds of other sources —
    # it is the most effective jailbreak for boards that block direct scraping.
    for term in search_terms:
        print(f"\n>> Searching: '{term}' in Germany...")
        try:
            df = scrape_jobs(
                site_name=["linkedin", "indeed", "google"],
                search_term=term,
                location="Germany",
                results_wanted=50,
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

                url_key = url.lower()
                if url_key in seen_urls:
                    continue
                seen_urls.add(url_key)

                pair = (company.lower(), normalize_title(title))
                if pair in session_pairs:
                    continue
                session_pairs.add(pair)

                if is_excluded(title):
                    continue

                score = score_job(title, desc, profile)
                if score < 4:
                    continue

                posted = row.get("date_posted", None)
                posted_str = str(posted) if posted and str(posted) not in ("NaT", "None") else "—"

                # normalize site name so dashboard badges work
                site = str(row.get("site", "")).lower()
                if "linkedin" in site:
                    source = "linkedin"
                elif "indeed" in site:
                    source = "indeed"
                elif "glassdoor" in site:
                    source = "glassdoor"
                elif "google" in site:
                    source = "google"
                else:
                    source = site

                all_jobs.append({
                    "title":       title,
                    "company":     company,
                    "location":    loc,
                    "score":       score,
                    "job_url":     url,
                    "is_remote":   remote,
                    "source":      source,
                    "date_posted": posted_str,
                })

        except Exception as e:
            print(f"   [WARN] Error scraping '{term}': {e}")
            continue

    # ── Company ATS boards (Greenhouse + Ashby + Lever) ─────────────────────
    board_jobs = scrape_company_boards(profile, seen_urls, session_pairs)
    if board_jobs:
        all_jobs.extend(board_jobs)
        print(f"   + {len(board_jobs)} from company ATS boards")

    # ── Bundesagentur für Arbeit ─────────────────────────────────────────────
    ba_jobs = scrape_arbeitsagentur(profile, seen_urls, session_pairs, days_old=7)
    all_jobs.extend(ba_jobs)

    # ── Arbeitnow (EU tech board) ─────────────────────────────────────────────
    an_jobs = scrape_arbeitnow(profile, seen_urls, session_pairs)
    all_jobs.extend(an_jobs)

    # ── StepStone RSS (jailbreak attempt) ────────────────────────────────────
    ss_jobs = scrape_stepstone_rss(profile, seen_urls, session_pairs)
    all_jobs.extend(ss_jobs)

    # sort by score desc
    all_jobs.sort(key=lambda x: x["score"], reverse=True)

    print(f"\n{'='*60}")
    print(f"SCRAPE COMPLETE — {len(all_jobs)} new matching jobs found")
    print(f"{'='*60}\n")

    state = {
        "date":      date.today().isoformat(),
        "timestamp": datetime.now().isoformat(),
        "count":     len(all_jobs),
        "urls":      [j["job_url"] for j in all_jobs],
    }
    LAST_RUN_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

    if not all_jobs:
        print("No new matches found. All results were filtered or already tracked.")
        return

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
