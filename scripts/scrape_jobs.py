"""
Job scraper for career-ops-plugin.
Sources: LinkedIn · Indeed · Glassdoor · Google Jobs (via jobspy)
         Greenhouse · Ashby · Lever (ATS direct APIs)
         Bundesagentur für Arbeit · Arbeitnow · StepStone RSS
         NL agency boards: Randstad · Olympia · Uitzendbureau · YoungCapital ·
         Manpower · Luba · Tempo-Team · Jopportunity (see scrape_nl_agencies)
Countries: set via profile.yml target.search_countries (default: ["Germany"]).
           Bundesagentur/StepStone are Germany-only regardless of this list;
           the NL agency boards are Netherlands-only regardless of this list.
Titles: data engineering, analytics/BI, data science, and data-focused
        architecture/cloud/platform roles (see _STRICT_TITLE_PATTERNS) —
        matches the same breadth as scrape_company_careers.py.
English-only: applied wherever a source provides description text (LinkedIn,
        Indeed/Google/Glassdoor, Greenhouse/Ashby/Lever, Arbeitnow, StepStone).
        Bundesagentur's list API returns no description text, so it isn't
        filtered — see its docstring. The NL agency boards deliberately skip
        this filter too — see scrape_nl_agencies docstring.

Modes (mutually exclusive; plain run with no flag = full/default):
  --quick   Fast single-term LinkedIn/EU-only pass. For a quick daily check.
            (Formerly a separate script, scrape_linkedin_europe.py — folded
            in here so there's one scraper instead of two making overlapping
            LinkedIn/EU calls back to back.)
  --daily   LinkedIn/EU + ATS boards + Arbeitsagentur + Arbeitnow + StepStone
            only — skips the slower Indeed/Google/Glassdoor per-country pass.
  (none)    Full mode (default): everything in --daily, PLUS Indeed/Google/
            Glassdoor per target country. Google Jobs in particular
            aggregates many boards direct scraping can't reach, so this is
            the default despite being slower (~3-6 min extra) — an
            automated run costs you nothing to wait on, and narrower
            coverage means missed roles. --full is still accepted as an
            explicit alias for this default.
"""

import sys
import re
import csv
import json
import logging
import xml.etree.ElementTree as ET
import yaml
import warnings
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def patch_jobspy_country_parsing():
    """
    jobspy's LinkedIn scraper crashes the ENTIRE multi-page fetch (not just
    skips one job) if any single result's displayed location contains a
    territory outside its own Country enum — e.g. "Isle of Man", "Jersey",
    "Vatican City". This only surfaces when searching broadly (e.g.
    location="European Union") rather than one of jobspy's known single-country
    strings, since a broad search naturally turns up small territories jobspy
    doesn't recognize. Patches Country.from_string to fall back to the raw
    string instead of raising, so one exotic location doesn't take down the
    whole run. Call once, after `from jobspy import scrape_jobs`, before any
    broad-location (non-single-country) call.
    """
    from jobspy.model import Country
    original = Country.from_string.__func__

    def _safe_from_string(cls, country_str):
        try:
            return original(cls, country_str)
        except ValueError:
            return country_str

    Country.from_string = classmethod(_safe_from_string)


def patch_jobspy_quiet_glassdoor():
    """
    Glassdoor is known-broken upstream (tightened anti-scraping — returns
    HTTP 400 / "location not parsed" for every call; see the NOTE at the
    jobspy: LinkedIn + Indeed + Glassdoor + Google Jobs section below). Its
    ERROR-level logging is noise for a failure mode we already expect and
    ignore, not a signal — left in the site list since it's harmless and
    may silently start working again if/when jobspy patches it upstream.

    A plain `logging.getLogger("JobSpy:Glassdoor").setLevel(...)` doesn't
    stick: jobspy.scrape_jobs() calls set_logger_level(verbose) internally
    on every invocation, which resets every "JobSpy:*" logger's level based
    on the verbose param (default verbose=0 -> ERROR, i.e. still shows
    ERRORs) — clobbering anything set beforehand. Wrap set_logger_level
    itself so our Glassdoor override survives each call. Call once, after
    `from jobspy import scrape_jobs`.
    """
    import jobspy
    from jobspy.util import set_logger_level as original_set_logger_level

    def _set_logger_level_and_quiet_glassdoor(verbose):
        original_set_logger_level(verbose)
        logging.getLogger("JobSpy:Glassdoor").setLevel(logging.CRITICAL)

    jobspy.set_logger_level = _set_logger_level_and_quiet_glassdoor

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

def load_tracked_url_pairs():
    """Collect (url, normalized title) pairs already in pipeline.md and
    applications.md. Some sources (e.g. a company career page with no
    per-job permalinks) return the SAME generic URL for many genuinely
    different job postings — plain URL-only dedup would then treat those
    distinct jobs as duplicates of each other and only keep the first one
    seen. Keying on (url, title) instead only treats it as "already seen"
    when both match, which still catches real repeats (same URL AND same
    title) without collapsing different titles that happen to share a URL."""
    pairs = set()
    for path in [APPS_PATH, PIPELINE_PATH]:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.startswith("|") or line.startswith("| Date") or line.startswith("|---"):
                continue
            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) < 4:
                continue
            company = cols[2]
            role = "|".join(cols[3:-6]).strip() if len(cols) >= 10 else cols[3]
            if not company or company.lower() in ("company", "---"):
                continue
            url_match = re.search(r'\(https?://[^\)]+\)', line)
            if not url_match:
                continue
            url = url_match.group(0).strip("()").lower()
            pairs.add((url, normalize_title(role)))
    return pairs

def load_tracked_pairs():
    """Collect (company, normalized title) pairs already in pipeline.md and
    applications.md. URL-only dedup (load_tracked_urls) misses the same job
    posted under different URLs on different platforms — e.g. found via
    LinkedIn last run, then the same role turns up via Indeed, a company's
    own Greenhouse board, or the company-crawl scraper today. Matching on
    (company, title) instead catches that regardless of which platform or
    scraper found it, or which run it was first seen in."""
    pairs = set()
    for path in [APPS_PATH, PIPELINE_PATH]:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.startswith("|") or line.startswith("| Date") or line.startswith("|---"):
                continue
            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) < 4:
                continue
            company = cols[2]
            # pipeline.md's 10-column format can have literal "|" inside the
            # role (e.g. "(w|m|d)"), which fragments a naive split — anchor
            # from the end the same way generate_dashboard.py does.
            role = "|".join(cols[3:-6]).strip() if len(cols) >= 10 else cols[3]
            if not company or company.lower() in ("company", "---"):
                continue
            pairs.add((company.lower(), normalize_title(role)))
    return pairs

# ── scoring ────────────────────────────────────────────────────────────────

SKILL_KEYWORDS = [
    "python", "sql", "pyspark", "spark", "airflow", "kafka", "snowflake",
    "dbt", "aws", "glue", "redshift", "s3", "emr", "kinesis", "databricks",
    "delta lake", "iceberg", "bigquery", "etl", "elt", "data lake",
    "lakehouse", "data warehouse", "streaming", "flink", "cdc",
    "data engineer", "analytics engineer", "data architect",
    "great expectations", "azure", "gcp", "terraform",
    # analytics / BI / data science terms — added when title scope widened
    # to cover Data Analyst / Data Scientist / BI roles, so those titles can
    # actually score against the candidate's real listed skills (Tableau,
    # Power BI are in profile.yml) instead of always scoring near 0.
    "tableau", "power bi", "looker", "qlik", "machine learning",
    "data analytics", "business intelligence",
    "dagster", "fivetran", "geospatial", "mlops",
]

EXCLUDE_KEYWORDS = [
    "junior", "intern", "internship", "trainee", "werkstudent",
    "student", "apprentice", "graduate program", "entry level",
    # Adjacent-but-wrong roles — not data roles at all, unlike Data Analyst /
    # Data Scientist / BI (which ARE in _STRICT_TITLE_PATTERNS below, matching
    # scrape_company_careers.py's broader data-role coverage). Deliberately
    # NOT excluding "marketing"/"sales"/etc as bare words — those are business
    # domains a real Data Engineer role can be scoped to (e.g. "Data Engineer -
    # Marketing & Communication" is a real data engineering role), and NOT
    # excluding "engineering manager" since EM-for-a-data-platform is a role
    # this candidate has genuinely pursued before.
    "business analyst",
    "operations analyst", "reporting analyst", "research scientist",
    "product owner", "product manager", "project manager",
    "program manager", "delivery manager",
    "account manager", "recruiter", "talent acquisition",
    "hr business partner",
]

# Title must contain an actual data-role-shaped phrase — not just the word
# "data" or "analytics" on its own, which used to let Product Owner-type
# roles through as long as "data" appeared anywhere in the title. Mirrors
# scrape_company_careers.py's DATA_ENGINEER_TERMS so both scrapers cover the
# same breadth of data roles: engineering, analytics, BI, data science,
# architecture, and data-focused cloud/platform roles.
_STRICT_TITLE_PATTERNS = (
    # data engineering
    "data engineer", "dataengineer", "etl engineer", "etl developer",
    "big data engineer", "data platform engineer", "platform data engineer",
    "data infrastructure engineer", "database engineer",
    "lead data engineer", "senior data engineer", "principal data engineer",
    "staff data engineer",
    # analytics / BI
    "analytics engineer", "data analyst", "data analytics",
    "bi developer", "bi engineer", "bi analyst",
    "business intelligence engineer", "business intelligence developer",
    "business intelligence analyst",
    # data science
    "data scientist",
    # architecture / data-focused cloud & platform
    "data architect", "cloud data engineer", "cloud platform engineer",
    "cloud architect", "platform engineer", "data platform",
    # Dutch-language equivalents — needed for the NL staffing-agency sources
    # (scrape_nl_agencies), whose listings are titled in Dutch even when the
    # role itself doesn't require Dutch fluency, so those sources deliberately
    # skip the is_english() filter and rely on title/skill matching instead.
    "data analist", "data-analist", "databeheerder", "data specialist",
    "data consultant", "data management specialist", "data solution architect",
    "informatie architect",
)

# Generic engineering titles that DON'T name a data role at all — e.g. a
# "Backend Developer" job that's mostly API/service work but happens to
# mention building data pipelines. Real example: an ALTEN "Senior Python
# Backend Developer" posting missed entirely because the title carries no
# data-role signal. These are let through ONLY if the description shows a
# real concentration of data-engineering skill keywords (see
# _GENERIC_TITLE_MIN_SKILL_MATCHES below) — otherwise this would flood
# results with ordinary backend/software roles that have nothing to do with
# data work. Expect these to score lower than a genuine data-titled role
# (no title-family bonus below), which is intentional — they're a "maybe,
# worth a look" tier, not a confirmed strong match.
_GENERIC_TITLE_PATTERNS = (
    "backend developer", "backend engineer", "software engineer",
    "software developer", "api developer", "python developer",
    "devops engineer", "site reliability engineer",
)
_GENERIC_TITLE_MIN_SKILL_MATCHES = 3

# Best-effort extraction of an overall years-of-experience requirement from
# JD body text, e.g. "5+ years of experience", "6-8 years' experience",
# "at least 7 years professional experience". Deliberately permissive on
# what precedes the number (skips over "at least", "minimum of", etc. since
# the regex isn't anchored to the start of the phrase) and tolerant of a
# trailing apostrophe ("years' experience"). Only the first (lower-bound)
# number in a range is captured, since that's the actual minimum threshold
# a candidate needs to clear.
_YEARS_EXPERIENCE_PATTERN = re.compile(
    r"(\d{1,2})\+?\s*(?:[-–to]{1,3}\s*\d{1,2}\+?\s*)?years?'?\s*"
    r"(?:of\s+)?(?:professional\s+|relevant\s+|proven\s+|working\s+|hands[- ]on\s+)?experience",
    re.IGNORECASE,
)


def exceeds_experience_requirement(text: str, max_years: int) -> bool:
    """True only if EVERY years-of-experience mention in the JD is above
    max_years — i.e. there's no qualifying reading of the requirement that
    a candidate with max_years (or fewer) would clear. A JD that mixes a
    role-level ask with a higher skill-specific one (e.g. "5+ years overall,
    8+ years in a lead capacity") is NOT excluded, since the 5+ reading
    still qualifies — this errs toward not hiding a real match over a noisy
    regex read. Returns False (don't exclude) if nothing matches at all,
    since most JDs don't state a number and absence of a stated minimum
    isn't evidence the role needs more than max_years."""
    if not text or not max_years:
        return False
    minimums = [int(m) for m in _YEARS_EXPERIENCE_PATTERN.findall(text)]
    if not minimums:
        return False
    return all(m > max_years for m in minimums)


def score_job(title: str, description: str, profile: dict) -> int:
    title_lc = title.lower()
    text = (title + " " + (description or "")).lower()
    score = 0

    strict_match = any(p in title_lc for p in _STRICT_TITLE_PATTERNS)
    generic_match = not strict_match and any(p in title_lc for p in _GENERIC_TITLE_PATTERNS)
    if not strict_match and not generic_match:
        return 0

    max_years = profile.get("target", {}).get("application_filters", {}).get("max_years_experience_required")
    if max_years and exceeds_experience_requirement(description or "", max_years):
        return 0

    matched = sum(1 for kw in SKILL_KEYWORDS if kw in text)
    if generic_match and matched < _GENERIC_TITLE_MIN_SKILL_MATCHES:
        return 0

    if strict_match:
        target_roles = [profile["target"]["primary_role"]] + profile["target"].get("secondary_roles", [])
        for role in target_roles:
            if role.lower() in title_lc:
                score += 3
                break
        if any(p in title_lc for p in ("data engineer", "analytics engineer", "data scientist",
                                        "data analyst", "bi developer", "bi engineer", "bi analyst",
                                        "business intelligence")):
            score += 1

    # No bonus for "senior/lead/principal/staff" in the title anymore — that
    # used to add +2, which structurally outranked plain/mid-level-titled
    # postings ("Data Engineer") against senior-titled ones regardless of
    # actual fit. Mid-level targeting now comes from primary_role no longer
    # being "Lead Data Engineer" (see profile.yml) plus the >max_years
    # exclusion above, not from a title-word scoring bonus.
    score += min(4, matched // 2)
    return min(score, 10)

def is_excluded(title: str) -> bool:
    return any(kw in title.lower() for kw in EXCLUDE_KEYWORDS)

def is_english(text: str) -> bool:
    """Best-effort English-language check on a job description. Used by
    --quick mode. Only imports langdetect when actually needed so the
    default run doesn't require it."""
    text = (text or "").strip()
    if len(text) < 40:
        return True  # too short to reliably detect — don't discard on a guess
    try:
        from langdetect import detect, LangDetectException
    except ImportError:
        return True  # langdetect not installed — don't gate on missing dep
    try:
        return detect(text) == "en"
    except Exception:
        return True  # detection failed — don't discard, let scoring/review decide

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
        url_key = (url.lower(), normalize_title(title))
        if url_key in seen_urls:
            return
        seen_urls.add(url_key)
        pair = (company.lower(), normalize_title(title))
        if pair in tracked_pairs:
            return
        tracked_pairs.add(pair)
        if is_excluded(title):
            return
        if desc and not is_english(desc):
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

    # ── Parallel raw fetch ────────────────────────────────────────────────────
    # Each board is an independent HTTP call to a developer-facing JSON API
    # (not a scraping-protected page), so these are safe and fast to run
    # concurrently. Dedup/scoring (_add) stays single-threaded afterward so
    # seen_urls/tracked_pairs never race across threads.

    def _fetch_greenhouse(slug):
        try:
            resp = requests.get(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                headers=_HEADERS, timeout=10,
            )
            if resp.status_code != 200:
                return []
            return resp.json().get("jobs", [])
        except Exception as e:
            print(f"   [WARN] Greenhouse {slug}: {e}")
            return []

    def _fetch_ashby(slug):
        try:
            resp = requests.post(
                "https://api.ashbyhq.com/posting-public/job-board",
                json={"organizationHostedJobsPageName": slug},
                headers=_HEADERS, timeout=10,
            )
            if resp.status_code != 200:
                return []
            return resp.json().get("jobPostings", [])
        except Exception as e:
            print(f"   [WARN] Ashby {slug}: {e}")
            return []

    def _fetch_lever(slug):
        try:
            resp = requests.get(
                f"https://api.lever.co/v0/postings/{slug}?mode=json",
                headers=_HEADERS, timeout=10,
            )
            if resp.status_code != 200:
                return []
            return resp.json()
        except Exception as e:
            print(f"   [WARN] Lever {slug}: {e}")
            return []

    boards = (
        [("greenhouse", name, slug) for name, slug in greenhouse_list] +
        [("ashby", name, slug) for name, slug in ashby_list] +
        [("lever", name, slug) for name, slug in lever_list]
    )
    board_workers = max(1, len(boards))
    print(f"\n>> Checking {len(boards)} ATS boards ({len(greenhouse_list)} Greenhouse, "
          f"{len(ashby_list)} Ashby, {len(lever_list)} Lever) — up to {board_workers} in parallel...")

    _FETCHERS = {"greenhouse": _fetch_greenhouse, "ashby": _fetch_ashby, "lever": _fetch_lever}
    raw = {}
    with ThreadPoolExecutor(max_workers=board_workers) as executor:
        futures = {
            executor.submit(_FETCHERS[kind], slug): (kind, name, slug)
            for kind, name, slug in boards
        }
        for future in as_completed(futures):
            kind, name, slug = futures[future]
            raw[(kind, name, slug)] = future.result()

    # ── Sequential processing (dedup + scoring) in a stable order ────────────
    for kind, name, slug in boards:
        for job in raw.get((kind, name, slug), []):
            if kind == "greenhouse":
                title  = job.get("title", "").strip()
                url    = job.get("absolute_url", "").strip()
                loc    = (job.get("location") or {}).get("name", "").strip()
                posted = (job.get("updated_at") or "")[:10]
                desc   = re.sub(r'<[^>]+>', ' ', job.get("content", "") or "")[:500]
                if not _is_de_location(loc):
                    continue
                _add(title, name, loc, url, posted, "greenhouse", desc)
            elif kind == "ashby":
                title   = job.get("title", "").strip()
                job_id  = job.get("id", "")
                url     = job.get("externalLink", "") or f"https://jobs.ashbyhq.com/{slug}/{job_id}"
                loc_raw = job.get("location") or {}
                loc     = (loc_raw.get("name", "") if isinstance(loc_raw, dict) else str(loc_raw)).strip()
                posted  = (job.get("publishedAt") or "")[:10]
                desc    = (job.get("descriptionPlain") or
                           re.sub(r'<[^>]+>', ' ', job.get("descriptionHtml", "") or ""))[:500]
                if not _is_de_location(loc):
                    continue
                _add(title, name, loc, url, posted, "ashby", desc)
            else:  # lever
                title  = job.get("text", "").strip()
                url    = job.get("hostedUrl", "").strip()
                cats   = job.get("categories", {})
                loc    = cats.get("location", "").strip()
                ts     = job.get("createdAt", 0)
                posted = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else "—"
                desc   = job.get("descriptionPlain", "")[:500]
                if not _is_de_location(loc):
                    continue
                _add(title, name, loc, url, posted, "lever", desc)

    return results


# ── Arbeitsagentur (German Federal Employment Agency) ──────────────────────

_BA_BASE    = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
_BA_HEADERS = {"User-Agent": "Mozilla/5.0", "X-API-Key": "jobboerse-jobsuche"}

def scrape_arbeitsagentur(profile, seen_urls, tracked_pairs, days_old: int = 1):
    """Query the Bundesagentur für Arbeit public REST API (no auth required).

    NOTE: unlike the other sources, this API's list endpoint returns no
    description text (only title/employer/location), so the English-language
    filter applied elsewhere can't run here without an extra per-job detail
    call. Left unfiltered by design rather than adding ~25 extra HTTP calls
    per run for a low-value/expensive check — many DE-market postings here
    are German-language regardless, which is expected for a Germany-specific
    source.
    """
    results = []
    cutoff  = (date.today() - timedelta(days=days_old)).isoformat()

    search_terms = [
        profile["target"]["primary_role"],
        "Data Analytics Engineer",
        "Analytics Engineer",
        "Cloud Data Engineer",
        "Data Architect",
    ]

    print(f"\n>> Arbeitsagentur: searching {len(search_terms)} terms (last {days_old} days), in parallel...")

    def _fetch_ba(term):
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
                return []
            return resp.json().get("stellenangebote", [])
        except Exception as e:
            print(f"   [WARN] Arbeitsagentur '{term}': {e}")
            return []

    raw = {}
    with ThreadPoolExecutor(max_workers=len(search_terms)) as executor:
        futures = {executor.submit(_fetch_ba, term): term for term in search_terms}
        for future in as_completed(futures):
            raw[futures[future]] = future.result()

    for term in search_terms:
        try:
            for job in raw.get(term, []):
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

                url_key = (url.lower(), normalize_title(title))
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

                url_key = (url.lower(), normalize_title(title))
                if url_key in seen_urls:
                    continue
                seen_urls.add(url_key)

                pair = (company.lower(), normalize_title(title))
                if pair in tracked_pairs:
                    continue
                tracked_pairs.add(pair)

                if desc and not is_english(desc):
                    continue

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
# NOTE (2026-07-23): confirmed via curl that stepstone.de/rss/stellenangebote.html
# now returns a flat HTTP 404 — StepStone appears to have removed this public feed
# entirely (not a transient block). Left in place since it degrades gracefully and
# costs nothing if it comes back; Google Jobs already aggregates most StepStone
# listings as a fallback in the jobspy pass above.

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

                url_key = (url.lower(), normalize_title(title))
                if url_key in seen_urls:
                    continue
                seen_urls.add(url_key)

                pair = (company.lower(), normalize_title(title))
                if pair in tracked_pairs:
                    continue
                tracked_pairs.add(pair)

                if desc and not is_english(desc):
                    continue

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


# ── NL staffing-agency job boards ───────────────────────────────────────────
# Netherlands-only regardless of search_countries, mirroring how Bundesagentur/
# StepStone are Germany-only above. All 8 sources were confirmed working via
# plain HTTP (no browser) as of 2026-08-09 — 3 are server-rendered HTML pages,
# 3 have an internal JSON API their own frontend calls (found via network
# capture), and 2 (jopportunity, youngcapital) need the search actually
# submitted (query string alone isn't enough / needs the right POST target).
# Each of these sites' own "keyword search" is fuzzy/semantic rather than a
# strict substring match — e.g. Manpower's API returns "Electromechanical
# Service Technician" for query "data" — so results here lean on score_job's
# title-pattern gate + skill-keyword scoring to do the real filtering, the
# same as scrape_arbeitnow does against an unfiltered feed.
#
# Deliberately skips is_english() — see the NL-title additions to
# _STRICT_TITLE_PATTERNS above. A hard Dutch-fluency requirement (if the JD
# text states one) is still a candidate-side judgment call at review time, not
# a scrape-time exclude, per project_job_search_scope.

_NL_SEARCH_TERM = "data"


def _looks_like_data_role(title: str) -> bool:
    """Cheap pre-check (title only, no network) mirroring score_job's title
    gate. Used to decide whether a detail-page fetch is worth the extra
    request — see _fetch_nl_detail_text."""
    title_lc = (title or "").lower()
    return any(p in title_lc for p in _STRICT_TITLE_PATTERNS) or \
           any(p in title_lc for p in _GENERIC_TITLE_PATTERNS)


def _fetch_nl_detail_text(url: str, max_chars: int = 6000) -> str:
    """Fetches a job detail page and returns its stripped plain text, for
    sources whose search-results listing carries no description (so
    score_job's skill-keyword matching would otherwise have nothing to work
    with beyond the bare title). Only called for titles that already pass
    _looks_like_data_role, to keep the extra-request count small — see call
    sites in _scrape_nl_uitzendbureau / _scrape_nl_youngcapital /
    _scrape_nl_tempoteam."""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; career-ops-bot/1.0)"},
            timeout=15,
        )
        if resp.status_code != 200:
            return ""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        return soup.get_text(" ", strip=True)[:max_chars]
    except Exception:
        return ""


def _finalize_nl_job(title, company, location, url, desc, posted, remote,
                      source, profile, seen_urls, tracked_pairs):
    """Shared dedup + exclude + score gate for all NL agency sources below.
    Returns a pipeline-row dict, or None if the job should be dropped."""
    title   = (title or "").strip()
    company = (company or "").strip()
    url     = (url or "").strip()
    if not title or not url:
        return None
    if is_excluded(title):
        return None

    url_key = (url.lower(), normalize_title(title))
    if url_key in seen_urls:
        return None
    seen_urls.add(url_key)

    pair = (company.lower(), normalize_title(title))
    if pair in tracked_pairs:
        return None
    tracked_pairs.add(pair)

    score = score_job(title, desc or "", profile)
    if score < 4:
        return None

    loc = location or "Netherlands"
    return {
        "title":       title,
        "company":     company or "—",
        "location":    loc,
        "score":       score,
        "job_url":     url,
        "is_remote":   bool(remote) or "remote" in loc.lower(),
        "source":      source,
        "date_posted": posted or "—",
    }


def _scrape_nl_randstad(profile, seen_urls, tracked_pairs):
    """Randstad.nl — server-rendered <article class="card item"> per job."""
    results = []
    try:
        resp = requests.get(
            "https://www.randstad.nl/vacatures",
            params={"vakgebied": "ICT", "afstand": 50, "zoekterm": _NL_SEARCH_TERM},
            headers={"User-Agent": "Mozilla/5.0 (compatible; career-ops-bot/1.0)"},
            timeout=20,
        )
        if resp.status_code != 200:
            return results
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        for art in soup.find_all("article", class_="card"):
            link = art.find("a", href=True)
            title_el = art.find("h2")
            if not link or not title_el:
                continue
            url = "https://www.randstad.nl" + link["href"] if link["href"].startswith("/") else link["href"]
            loc_el = art.find("span", class_="simplelist__item--text")
            desc_el = art.find("div", class_="card__description")
            job = _finalize_nl_job(
                title=title_el.get_text(strip=True),
                company="Randstad",
                location=loc_el.get_text(strip=True) if loc_el else "Netherlands",
                url=url,
                desc=desc_el.get_text(" ", strip=True) if desc_el else "",
                posted=None,
                remote=False,
                source="randstad-nl",
                profile=profile, seen_urls=seen_urls, tracked_pairs=tracked_pairs,
            )
            if job:
                results.append(job)
    except Exception as e:
        print(f"   [WARN] Randstad NL: {e}")
    return results


def _scrape_nl_olympia(profile, seen_urls, tracked_pairs):
    """Olympia.nl — server-rendered <li class="card card-body"> per job."""
    results = []
    try:
        resp = requests.get(
            "https://www.olympia.nl/vacatures/",
            params={"zoekterm": _NL_SEARCH_TERM},
            headers={"User-Agent": "Mozilla/5.0 (compatible; career-ops-bot/1.0)"},
            timeout=20,
        )
        if resp.status_code != 200:
            return results
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        for h3 in soup.find_all("h3", class_="mb-xxs"):
            link = h3.find("a", href=True)
            if not link:
                continue
            card = h3.find_parent("li")
            url = "https://www.olympia.nl" + link["href"] if link["href"].startswith("/") else link["href"]
            img = card.find("img", alt=True) if card else None
            loc = None
            if card:
                for li in card.find_all("li"):
                    if li.find("strong") and "Locatie" in li.find("strong").get_text():
                        loc = li.get_text(strip=True).replace("Locatie:", "").strip()
                        break
            desc_el = card.find("p", class_="no-margin") if card else None
            job = _finalize_nl_job(
                title=link.get_text(strip=True),
                company=img["alt"].strip() if img else "—",
                location=loc or "Netherlands",
                url=url,
                desc=desc_el.get_text(" ", strip=True) if desc_el else "",
                posted=None,
                remote=False,
                source="olympia-nl",
                profile=profile, seen_urls=seen_urls, tracked_pairs=tracked_pairs,
            )
            if job:
                results.append(job)
    except Exception as e:
        print(f"   [WARN] Olympia NL: {e}")
    return results


def _scrape_nl_uitzendbureau(profile, seen_urls, tracked_pairs):
    """Uitzendbureau.nl — Nuxt SSR; real recruiter/location shown per card."""
    results = []
    try:
        resp = requests.get(
            "https://www.uitzendbureau.nl/vacature",
            params={"s": _NL_SEARCH_TERM},
            headers={"User-Agent": "Mozilla/5.0 (compatible; career-ops-bot/1.0)"},
            timeout=20,
        )
        if resp.status_code != 200:
            return results
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.find_all("a", class_="job-search__result-list__result__title", href=True):
            title = link.get_text(strip=True)
            card = link.find_parent("div", class_="job-search__result-list__result")
            company_el = card.find("span", class_="cro-recruiter-name") if card else None
            loc_el = card.find("span", class_="cro-job-location") if card else None
            # Listing cards carry no description text — fetch the detail page
            # only for titles that already look like a data role, so score_job
            # has real skill-keyword text to score against (see
            # _fetch_nl_detail_text docstring).
            desc = _fetch_nl_detail_text(link["href"]) if _looks_like_data_role(title) else ""
            job = _finalize_nl_job(
                title=title,
                company=company_el.get_text(strip=True) if company_el else "—",
                location=loc_el.get_text(strip=True) if loc_el else "Netherlands",
                url=link["href"],
                desc=desc,
                posted=None,
                remote=False,
                source="uitzendbureau-nl",
                profile=profile, seen_urls=seen_urls, tracked_pairs=tracked_pairs,
            )
            if job:
                results.append(job)
    except Exception as e:
        print(f"   [WARN] Uitzendbureau NL: {e}")
    return results


def _scrape_nl_youngcapital(profile, seen_urls, tracked_pairs):
    """YoungCapital.nl — job cards carry data-job-opening-* attrs directly."""
    results = []
    try:
        resp = requests.get(
            "https://www.youngcapital.nl/vacatures",
            params={"search[keywords_scope]": _NL_SEARCH_TERM},
            headers={"User-Agent": "Mozilla/5.0 (compatible; career-ops-bot/1.0)"},
            timeout=20,
        )
        if resp.status_code != 200:
            return results
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", class_="job-opening__item", href=True):
            loc_span = a.find("span", class_="nyc-icon-location")
            loc = None
            if loc_span:
                icon_row = loc_span.find_parent("div", class_="flex-row")
                spans = icon_row.find_all("span") if icon_row else []
                loc = spans[-1].get_text(strip=True) if spans else None
            url = a["href"]
            if url.startswith("/"):
                url = "https://www.youngcapital.nl" + url
            title = a.get("data-job-opening-title") or a.get_text(strip=True)
            # Listing cards carry no description text — see uitzendbureau's
            # identical comment above.
            desc = _fetch_nl_detail_text(url) if _looks_like_data_role(title) else ""
            job = _finalize_nl_job(
                title=title,
                company=a.get("data-job-opening-item-brand") or "—",
                location=loc or "Netherlands",
                url=url,
                desc=desc,
                posted=None,
                remote=False,
                source="youngcapital-nl",
                profile=profile, seen_urls=seen_urls, tracked_pairs=tracked_pairs,
            )
            if job:
                results.append(job)
    except Exception as e:
        print(f"   [WARN] YoungCapital NL: {e}")
    return results


def _scrape_nl_manpower(profile, seen_urls, tracked_pairs):
    """Manpower.nl — internal JSON API (POST), found via network capture.
    NOTE: searchKeyword is honored loosely/semantically by their backend, not
    as a strict filter — real-world observed result for "data" included
    "Electromechanical Service Technician". score_job's title gate is what
    actually narrows this down, same as the rest of this module."""
    results = []
    try:
        resp = requests.post(
            "https://www.manpower.nl/api/services/Jobs/searchjobs",
            json={"filter": {
                "page": "1", "searchKeyword": _NL_SEARCH_TERM, "offset": 0,
                "totalCount": 0, "limit": 50, "searchkeyword": _NL_SEARCH_TERM,
                "haslocation": False, "language": "en",
            }},
            headers={"User-Agent": "Mozilla/5.0 (compatible; career-ops-bot/1.0)",
                     "Content-Type": "application/json"},
            timeout=20,
        )
        if resp.status_code != 200:
            return results
        for j in resp.json().get("jobsItems", []):
            title = j.get("jobTitle", "")
            url = j.get("jobURL", "")
            if url.startswith("/"):
                url = "https://www.manpower.nl" + url
            posted = (j.get("publishfromDate") or "")[:10] or None
            job = _finalize_nl_job(
                title=title,
                company=j.get("companyName") or "Manpower",
                location=j.get("jobLocation") or "Netherlands",
                url=url,
                desc=j.get("publicDescription", "") or j.get("openingParagraph", ""),
                posted=posted,
                remote=False,
                source="manpower-nl",
                profile=profile, seen_urls=seen_urls, tracked_pairs=tracked_pairs,
            )
            if job:
                results.append(job)
    except Exception as e:
        print(f"   [WARN] Manpower NL: {e}")
    return results


def _scrape_nl_luba(profile, seen_urls, tracked_pairs):
    """Luba.nl — internal JSON API on jobsite-luba.recruitnow.nl (POST),
    found via network capture."""
    results = []
    try:
        resp = requests.post(
            "https://jobsite-luba.recruitnow.nl/api/vacancies/search",
            json={
                "Facets": [], "Filters": [], "Ranges": [],
                "SearchQuery": _NL_SEARCH_TERM,
                "Pagination": {"Size": 50, "From": 0},
                "Location": {"Distance": 25, "Lat": 0, "Lon": 0},
                "Sorting": {"Sort": "Published", "Direction": "Descending"},
            },
            headers={"User-Agent": "Mozilla/5.0 (compatible; career-ops-bot/1.0)",
                     "Content-Type": "application/json",
                     "Origin": "https://www.luba.nl",
                     "Referer": f"https://www.luba.nl/vacature?query={_NL_SEARCH_TERM}"},
            timeout=20,
        )
        if resp.status_code != 200:
            return results
        for r in resp.json().get("results", []):
            meta = r.get("metaData", {})
            office = meta.get("office", {}) or {}
            address = office.get("address", {}) or {}
            descs = r.get("descriptions", {}) or {}
            desc = " ".join(filter(None, [
                descs.get("summary"), descs.get("functionDescription"),
                descs.get("requirementsDescription"),
            ]))
            posted = (meta.get("publicationDate") or "")[:10] or None
            job = _finalize_nl_job(
                title=r.get("title", ""),
                company=meta.get("agency", {}).get("title") or "Luba",
                location=address.get("city") or "Netherlands",
                url=meta.get("publicationUrl", ""),
                desc=desc,
                posted=posted,
                remote=False,
                source="luba-nl",
                profile=profile, seen_urls=seen_urls, tracked_pairs=tracked_pairs,
            )
            if job:
                results.append(job)
    except Exception as e:
        print(f"   [WARN] Luba NL: {e}")
    return results


def _scrape_nl_tempoteam(profile, seen_urls, tracked_pairs):
    """Tempo-Team.nl — internal Hippo CMS "resource" JSON endpoint (GET),
    found via network capture. aanvraagNummer + slugified jobNaam reconstructs
    the public job URL (the JSON itself carries no URL field)."""
    results = []
    try:
        resp = requests.get(
            "https://www.tempo-team.nl/vacatures",
            params={"_hn:type": "resource", "_hn:ref": "r280_r1_r1",
                    "pagina": 1, "zoekterm": _NL_SEARCH_TERM},
            headers={"User-Agent": "Mozilla/5.0 (compatible; career-ops-bot/1.0)",
                     "Accept": "application/json"},
            timeout=20,
        )
        if resp.status_code != 200:
            return results
        data = resp.json()
        jobs = data.get("relay42", {}).get("jobListing", [])
        for j in jobs:
            job_id = j.get("aanvraagNummer")
            title = j.get("jobNaam") or j.get("jobNaamMondriaan") or ""
            if not job_id or not title:
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            url = f"https://www.tempo-team.nl/vacatures/{job_id}/{slug}"
            # The resource JSON carries only category classifications, not a
            # real description — see uitzendbureau's identical comment above.
            desc = j.get("jobVakgebieden", "")
            if _looks_like_data_role(title):
                desc = (desc + " " + _fetch_nl_detail_text(url)).strip()
            job = _finalize_nl_job(
                title=title,
                company="Tempo-Team",
                location=j.get("jobPlaats") or "Netherlands",
                url=url,
                desc=desc,
                posted=None,
                remote=str(j.get("jobWorkfromhome", "")).lower() in ("ja", "yes", "true"),
                source="tempoteam-nl",
                profile=profile, seen_urls=seen_urls, tracked_pairs=tracked_pairs,
            )
            if job:
                results.append(job)
    except Exception as e:
        print(f"   [WARN] Tempo-Team NL: {e}")
    return results


def _scrape_nl_jopportunity(profile, seen_urls, tracked_pairs):
    """Jopportunity.nl — OTYS-based ATS portal. The bare search-page URL
    returns 0 results (no query applied); the real search is a POST to its
    smartsearch endpoint, found by reading the page's own <form>."""
    results = []
    try:
        resp = requests.post(
            "https://www.jopportunity.nl/index.php/page/smartsearch/bb/1",
            data={"smartq": _NL_SEARCH_TERM, "smartsearch_type": "and"},
            headers={"User-Agent": "Mozilla/5.0 (compatible; career-ops-bot/1.0)"},
            timeout=20,
        )
        if resp.status_code != 200:
            return results
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        for h2 in soup.find_all("h2"):
            link = h2.find("a", href=True)
            if not link or "/command/detail/" not in link["href"]:
                continue
            desc_el = h2.find_next_sibling("p")
            job = _finalize_nl_job(
                title=link.get_text(strip=True),
                company="—",
                location="Netherlands",
                url=link["href"],
                desc=desc_el.get_text(" ", strip=True) if desc_el else "",
                posted=None,
                remote=False,
                source="jopportunity-nl",
                profile=profile, seen_urls=seen_urls, tracked_pairs=tracked_pairs,
            )
            if job:
                results.append(job)
    except Exception as e:
        print(f"   [WARN] Jopportunity NL: {e}")
    return results


def scrape_nl_agencies(profile, seen_urls, tracked_pairs):
    """Orchestrates all 8 NL staffing-agency sources. Netherlands-only,
    regardless of search_countries — skipped entirely if "Netherlands" isn't
    in the configured target list. Each source is isolated in its own
    try/except above so one site breaking (layout/API change) doesn't take
    the others down."""
    if not any("netherlands" in c.lower() for c in profile.get("target", {}).get("search_countries", [])):
        return []

    print(f"\n>> NL agency boards: Randstad, Olympia, Uitzendbureau, YoungCapital, "
          f"Manpower, Luba, Tempo-Team, Jopportunity...")

    sources = [
        _scrape_nl_randstad, _scrape_nl_olympia, _scrape_nl_uitzendbureau,
        _scrape_nl_youngcapital, _scrape_nl_manpower, _scrape_nl_luba,
        _scrape_nl_tempoteam, _scrape_nl_jopportunity,
    ]
    results = []
    for fn in sources:
        jobs = fn(profile, seen_urls, tracked_pairs)
        if jobs:
            print(f"   + {len(jobs)} from {jobs[0]['source']}")
        results.extend(jobs)

    if results:
        print(f"   + {len(results)} total from NL agency boards")
    return results


# ── main ───────────────────────────────────────────────────────────────────

def main():
    hours_old = 24
    quick_run = "--quick" in sys.argv
    daily_only = "--daily" in sys.argv
    # Full multi-source coverage is the default now (was opt-in via --full) —
    # narrower coverage means missed roles, and an automated run costs
    # nothing extra to wait a few more minutes on. --full is still accepted
    # as an explicit no-op alias for this default. --daily opts back into
    # the old faster-but-narrower behavior.
    full_run = not quick_run and not daily_only
    for arg in sys.argv[1:]:
        if arg in ("--full", "--quick", "--daily"):
            continue
        try:
            hours_old = int(arg)
        except ValueError:
            pass
    if quick_run:
        mode = "quick (LinkedIn/EU only, single term, English descriptions only)"
    elif full_run:
        mode = "full (default)"
    else:
        mode = "daily (LinkedIn-only for the main jobspy pass)"
    print(f"Loading profile... (hours_old={hours_old}, mode={mode})")
    profile = load_profile()

    print("Loading tracked jobs for dedup...")
    tracked_urls = load_tracked_url_pairs()
    # Seeded with historical (company, title) pairs, not just this run's —
    # catches the same job already tracked under a different URL from a
    # different platform/scraper (see load_tracked_pairs docstring).
    session_pairs = load_tracked_pairs()
    print(f"   {len(tracked_urls)} tracked (url, title) pairs, {len(session_pairs)} tracked (company, title) pairs")

    # --quick: a single broad term is enough for a fast daily LinkedIn-only
    # check (formerly a separate script, scrape_linkedin_europe.py — folded
    # in here so there's one scraper, not two issuing overlapping LinkedIn/EU
    # calls back to back).
    search_terms = ["Data Engineer"] if quick_run else [
        profile["target"]["primary_role"],
        "Data Analytics Engineer",
        "Analytics Engineer",
        "Cloud Data Engineer",
        "Data Architect",
    ]

    # List of countries to search — add more here (or in profile.yml under
    # target.search_countries) to expand beyond Germany/Netherlands.
    search_countries = profile.get("target", {}).get("search_countries", ["Germany"])

    try:
        from jobspy import scrape_jobs
    except ImportError:
        print("ERROR: jobspy not installed. Run: pip install python-jobspy")
        sys.exit(1)
    patch_jobspy_country_parsing()
    patch_jobspy_quiet_glassdoor()

    all_jobs = []
    seen_urls = set(tracked_urls)

    # ── jobspy: LinkedIn + Indeed + Glassdoor + Google Jobs ─────────────────
    # Google Jobs aggregates StepStone, XING, and hundreds of other sources —
    # it is the most effective jailbreak for boards that block direct scraping.
    #
    # NOTE (2026-07-23): Glassdoor is included below but currently returns 0
    # results for German locations via jobspy — "Glassdoor response status
    # code 400 / location not parsed". This is an upstream jobspy/Glassdoor
    # issue (Glassdoor tightened anti-scraping), not a bug here. Left in the
    # site list since it's harmless (doesn't affect Indeed/Google) and will
    # silently start working again if/when jobspy patches it.

    def _process_df(df, all_jobs, seen_urls, session_pairs, profile, location_filter=None,
                     require_english=False):
        """Dedup + score + append rows from a jobspy result DataFrame. Single-
        threaded by design — called after all parallel fetches complete, so
        seen_urls/session_pairs never race across threads."""
        if df is None or df.empty:
            return
        for _, row in df.iterrows():
            title   = str(row.get("title", "")).strip()
            company = str(row.get("company", "")).strip()
            url     = str(row.get("job_url", "")).strip()
            loc     = str(row.get("location", "")).strip()
            desc    = str(row.get("description", "") or "")
            remote  = bool(row.get("is_remote", False))

            if not title or not company:
                continue
            if location_filter and not location_filter(loc):
                continue

            url_key = (url.lower(), normalize_title(title))
            if url_key in seen_urls:
                continue
            seen_urls.add(url_key)

            pair = (company.lower(), normalize_title(title))
            if pair in session_pairs:
                continue
            session_pairs.add(pair)

            if is_excluded(title):
                continue

            if require_english and not is_english(desc):
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

    # ── Phase A: LinkedIn, searched once per term across the European Union ──
    # jobspy's LinkedIn scraper accepts a free-text location and does its own
    # server-side geo resolution — "European Union" works directly (confirmed:
    # returns EU member states only, no UK/Switzerland/Norway/Turkey, matching
    # LinkedIn's own "European Union" geo entity, geoId=91000000). This
    # replaces what would otherwise be 13 separate per-country LinkedIn calls
    # (one per search_countries entry) with 5 (one per search term). Results
    # are still filtered down to just search_countries afterward as a second
    # safety net (e.g. against EU member states not yet in that list).
    print(f"\n>> LinkedIn: searching the European Union, {len(search_terms)} terms in parallel...")

    def _country_location_filter(loc):
        loc_l = loc.lower()
        return any(country.lower() in loc_l for country in search_countries)

    def _fetch_linkedin_europe(term):
        try:
            return scrape_jobs(
                site_name=["linkedin"],
                search_term=term,
                location="European Union",
                results_wanted=100 if quick_run else 75,
                hours_old=hours_old,
                # Need full descriptions to run the English-language filter below.
                linkedin_fetch_description=True,
                verbose=0,
            ), None
        except Exception as e:
            return None, e

    with ThreadPoolExecutor(max_workers=len(search_terms)) as executor:
        futures = {executor.submit(_fetch_linkedin_europe, t): t for t in search_terms}
        for future in as_completed(futures):
            term = futures[future]
            df, err = future.result()
            if err:
                print(f"   [WARN] LinkedIn/Europe '{term}': {err}")
                continue
            n_total = 0 if df is None else len(df)
            _process_df(df, all_jobs, seen_urls, session_pairs, profile,
                        location_filter=_country_location_filter,
                        require_english=True)
            print(f"   '{term}': {n_total} raw results across Europe "
                  f"(filtered to {', '.join(search_countries)})")

    if quick_run:
        print("\n>> --quick mode: skipping Indeed/Google/Glassdoor, ATS boards, "
              "Arbeitsagentur, Arbeitnow, and StepStone — LinkedIn/EU only.")

    # ── Phase B: Indeed + Google + Glassdoor, per country ────────────────────
    # These three don't support a broad "European Union" location the way
    # LinkedIn does (Indeed's country_indeed param has a strict per-country
    # enum, checked directly against jobspy's Country list), so
    # they stay looped per search_countries entry — but fetched in parallel.
    # Even parallelized this is the slow part (13 countries x 5 terms = 65
    # calls), so it's opt-in via --full. Default runs are LinkedIn-only,
    # which covers daily use fine on its own.
    if full_run:
        # max_workers is capped at 6 rather than firing all (country x term)
        # calls at once — the aim is to avoid too much concurrency from one
        # IP, which risks getting rate-limited/blocked rather than actually
        # going faster.
        tasks = [(c, t) for c in search_countries for t in search_terms]
        MAX_SCRAPE_WORKERS = min(6, len(tasks))
        print(f"\n>> Indeed/Google/Glassdoor: fetching {len(tasks)} (country, search term) "
              f"combinations across {MAX_SCRAPE_WORKERS} parallel workers...")

        def _fetch_jobspy(country, term):
            try:
                df = scrape_jobs(
                    site_name=["indeed", "google", "glassdoor"],
                    search_term=term,
                    location=country,
                    results_wanted=50,
                    country_indeed=country,
                    hours_old=hours_old,
                    verbose=0,
                )
                return df, None
            except Exception as e:
                return None, e

        fetched = {}
        with ThreadPoolExecutor(max_workers=MAX_SCRAPE_WORKERS) as executor:
            futures = {executor.submit(_fetch_jobspy, c, t): (c, t) for c, t in tasks}
            done = 0
            for future in as_completed(futures):
                country, term = futures[future]
                df, err = future.result()
                done += 1
                if err:
                    print(f"   [{done}/{len(tasks)}] [WARN] '{term}' in {country}: {err}")
                elif df is None or df.empty:
                    print(f"   [{done}/{len(tasks)}] '{term}' in {country}: no results")
                else:
                    print(f"   [{done}/{len(tasks)}] '{term}' in {country}: {len(df)} raw results")
                fetched[(country, term)] = df

        # Sequential dedup + scoring, in stable (country, term) order regardless
        # of fetch completion order, so results/dedup precedence stay deterministic.
        for country, term in tasks:
            _process_df(fetched.get((country, term)), all_jobs, seen_urls, session_pairs, profile,
                        require_english=True)
    else:
        print("\n>> Skipping Indeed/Google/Glassdoor per-country pass (daily mode). "
              "Run with --full for full multi-source coverage.")

    if not quick_run:
        # ── Company ATS boards (Greenhouse + Ashby + Lever) ──────────────────
        board_jobs = scrape_company_boards(profile, seen_urls, session_pairs)
        if board_jobs:
            all_jobs.extend(board_jobs)
            print(f"   + {len(board_jobs)} from company ATS boards")

        # ── Bundesagentur für Arbeit ──────────────────────────────────────────
        ba_jobs = scrape_arbeitsagentur(profile, seen_urls, session_pairs, days_old=1)
        all_jobs.extend(ba_jobs)

        # ── Arbeitnow (EU tech board) ─────────────────────────────────────────
        an_jobs = scrape_arbeitnow(profile, seen_urls, session_pairs)
        all_jobs.extend(an_jobs)

        # ── StepStone RSS (jailbreak attempt) ──────────────────────────────────
        ss_jobs = scrape_stepstone_rss(profile, seen_urls, session_pairs)
        all_jobs.extend(ss_jobs)

        # ── NL staffing-agency boards (Randstad, Olympia, Uitzendbureau, ────────
        # YoungCapital, Manpower, Luba, Tempo-Team, Jopportunity) ───────────────
        nl_jobs = scrape_nl_agencies(profile, seen_urls, session_pairs)
        all_jobs.extend(nl_jobs)

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
