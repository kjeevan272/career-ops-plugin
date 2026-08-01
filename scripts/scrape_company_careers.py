"""
Company career-page scraper for career-ops-plugin.
Separate PROCESS from scripts/scrape_jobs.py (LinkedIn/Indeed/ATS-board
scraper) — this one crawls a fixed list of company career pages directly
(data/company_career_pages.json) via a headless browser, plus direct public
APIs for Greenhouse/Ashby/Lever/Personio/Workable/BambooHR when a career
page redirects to one of those platforms. Kept as a separate script
deliberately (different concurrency model — asyncio/Playwright vs
threaded requests — and a much heavier Chromium dependency); see
scripts/full_scan.py for running both together.

Usage:
    python scripts/scrape_company_careers.py
    python scripts/scrape_company_careers.py <input_json> <output_json>

Matches are also routed into data/pipeline.md (same scoring/dedup/English-
filter logic as scrape_jobs.py, tagged source="company-crawl") so they show
up in the single pipeline-dashboard.html — run
`python scripts/generate_dashboard.py` afterward, or use scripts/full_scan.py
which does this automatically. data/scraped_company_jobs.json (raw output)
is kept for debugging.
"""

import asyncio
import concurrent.futures
import collections
import collections.abc
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import requests

if not hasattr(collections, "Callable"):
    collections.Callable = collections.abc.Callable

from bs4 import BeautifulSoup
from playwright.async_api import BrowserContext, async_playwright, Error as PlaywrightError

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"

INPUT_LINK_FILE = DATA_DIR / "company_career_pages.json"
OUTPUT_JOBS_FILE = DATA_DIR / "scraped_company_jobs.json"
DISCOVERED_CACHE_PATH = DATA_DIR / "company_career_discovered_cache.json"
WORKING_URL_CACHE_PATH = DATA_DIR / "company_career_working_url_cache.json"
TIMEOUT_CACHE_PATH = DATA_DIR / "company_career_timeout_cache.json"
# Separate from scrape_jobs.py's data/.last-run.json so the two scrapers never
# stomp each other's "what's new" state when run independently — full_scan.py
# merges the two after running both together.
LAST_RUN_PATH = DATA_DIR / ".last-run-company.json"

sys.path.insert(0, str(Path(__file__).parent))
from scrape_jobs import (  # noqa: E402
    load_profile, load_tracked_url_pairs, load_tracked_pairs, normalize_title,
    score_job, append_to_pipeline,
)

# fetch_jobs_async always tries a plain HTTP GET first and only falls back to
# a real browser page if that fails to turn up jobs (see fetch_jobs_async).
# Previously ALL 513 companies — including the ones that resolve via the fast
# HTTP-only path and never touch the browser — were gated behind the same
# 20-slot semaphore meant to protect Chromium page/memory usage, so the cheap
# majority of the crawl was waiting on the same bottleneck as the expensive
# minority. MAX_CONCURRENT_HTTP now bounds the cheap path (just HTTP calls,
# safe to run much higher); MAX_CONCURRENT_PAGES separately bounds only the
# actual browser-page renders.
MAX_CONCURRENT_HTTP = 60
MAX_CONCURRENT_PAGES = 20
PAGE_GOTO_TIMEOUT_MS = 10000
PAGE_IDLE_TIMEOUT_MS = 2500
# Measured bottleneck: with no cap, a single company with 3-4 dead/slow
# candidate URLs can chain through all of them sequentially (each up to
# ~PAGE_GOTO_TIMEOUT_MS + PAGE_IDLE_TIMEOUT_MS) before giving up — 60-90+s
# for one company, which the whole batch then waits on. This bounds the
# worst case per company regardless of how many candidates it has; a
# skipped company just tries again (from the URL cache) next run.
PER_COMPANY_TIMEOUT_S = 30
# A company that has never resolved to a working URL has nothing in
# working_url_cache, so the "will retry from cache next run" message at the
# timeout site doesn't actually apply to it — every run re-tries the same
# dead/slow candidates and re-burns the full PER_COMPANY_TIMEOUT_S budget for
# no gain (measured: 31/513 companies as of 2026-08, ~15+ wasted minutes/run).
# TIMEOUT_CACHE_PATH records the last timeout per company so those can be
# skipped outright until the cooldown elapses, instead of retried every run.
TIMEOUT_COOLDOWN_DAYS = 3
# Matches a daily run cadence — "recent" = since yesterday's run, not a
# rolling 7-day window that mostly re-flags jobs already seen.
RECENT_DAYS = 1

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; JobScraper/1.0)"
}

COOKIE_ACCEPT_SELECTORS = [
    # OneTrust
    "#onetrust-accept-btn-handler",
    # Cookiebot
    "#CybotCookiebotDialogBodyButtonAccept",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    # Usercentrics
    "button[data-testid='uc-accept-all-button']",
    "#usercentrics-root button[data-testid='uc-accept-all-button']",
    # Didomi
    "#didomi-notice-agree-button",
    ".didomi-continue-without-agreeing",
    # Quantcast Choice
    "button.qc-cmp2-summary-buttons > button[mode='primary']",
    # TrustArc
    "#truste-consent-button",
    # Generic text matches, English
    "button:has-text('Accept all')",
    "button:has-text('Accept All')",
    "button:has-text('Accept all cookies')",
    "button:has-text('Allow all')",
    "button:has-text('Allow all cookies')",
    "button:has-text('I agree')",
    "button:has-text('I accept')",
    "button:has-text('Agree')",
    "button:has-text('Got it')",
    "button:has-text('OK')",
    "button:has-text('Accept')",
    # Generic text matches, German
    "button:has-text('Alle akzeptieren')",
    "button:has-text('Alle Cookies akzeptieren')",
    "button:has-text('Akzeptieren')",
    "button:has-text('Zustimmen')",
    "button:has-text('Einverstanden')",
    "button:has-text('Ich stimme zu')",
]

JOB_LINK_KEYWORDS = ["career", "careers", "jobs", "job", "recruit", "apply", "stellen", "karriere", "bewerb"]
AGGREGATOR_DOMAINS = [
    "linkedin.com", "indeed.", "glassdoor.", "stepstone.", "xing.com",
    "kununu.com", "monster.", "meinestadt.de",
]
DATA_ENGINEER_TERMS = [
    "data engineer", "data engineering", "dateningenieur", "etl engineer",
    "etl developer", "data pipeline", "big data engineer", "data platform engineer",
    "data infrastructure engineer", "analytics engineer", "database engineer",
    "data analyst", "data analytics", "data analysis", "datenanalyst",
    "cloud engineer", "cloud platform engineer", "cloud data engineer",
    "cloud architect", "platform engineer", "data platform",
    "data scientist", "data science", "datenwissenschaft",
    "business intelligence", "bi developer", "bi analyst", "bi engineer", "bi consultant",
]
DATA_TECH_SKILLS = [
    "etl", "elt", "spark", "pyspark", "hadoop", "kafka", "airflow", "dbt",
    "snowflake", "bigquery", "redshift", "databricks", "data pipeline",
    "data warehouse", "data lake", "aws glue", "azure data factory",
    "data modeling", "data infrastructure", "aws", "azure", "gcp",
    "google cloud", "kubernetes", "terraform", "data analytics",
    "power bi", "tableau", "looker", "qlik", "sap", "salesforce",
    "business intelligence", "machine learning", "sql",
]
GENERIC_ROLE_WORDS = [
    "engineer", "developer", "entwickler", "ingenieur",
    "analyst", "platform", "cloud", "architect", "scientist", "consultant",
]
NOISE_URL_PATTERNS = ["/blogarticle/", "/article/", "/blog/", "/stories/", "/news/"]
NOISE_TITLE_PATTERNS = [
    r"^\w+[:,]\s",
    r"\bday in the life\b",
    r"\bmeet\b",
    r"\bmy journey\b",
]
NAV_TITLE_WORDS = {
    "about", "blog", "contact", "datenschutz", "deutsch", "english", "home",
    "impressum", "info", "jobs", "karriere", "kontakt", "login", "menu",
    "news", "privacy", "search", "stellenangebote", "team",
}


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def is_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def build_candidate_urls(base_url: str) -> List[str]:
    from urllib.parse import urlparse
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        return [base_url]

    root = f"{parsed.scheme}://{parsed.netloc}"
    candidates = [base_url, f"{root}/"]
    for suffix in ["/jobs", "/careers", "/karriere", "/stellenangebote"]:
        candidates.append(f"{root}{suffix}")

    return list(dict.fromkeys(candidates))


def normalize_date(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if match:
        return match.group(0)
    match = re.search(r"\d{1,2}\.\d{1,2}\.\d{2,4}", text)
    return match.group(0) if match else text


def make_job(company: str, title: str, date: str, link: str, source_url: str = "", description: str = "") -> Dict[str, Any]:
    return {
        "company": clean_text(company),
        "title": clean_text(title),
        "posted_or_updated_date": normalize_date(date),
        "apply_link": clean_text(link),
        "source_url": clean_text(source_url or link),
        "description": clean_text(description)[:500],
    }


def is_probable_scraped_title(title: str, link: str) -> bool:
    normalized = clean_text(title).lower()
    if not normalized or normalized in NAV_TITLE_WORDS:
        return False
    if len(normalized) < 4:
        return False
    return any(keyword in link.lower() for keyword in JOB_LINK_KEYWORDS) or re.search(r"\(m/?w/?d\)|m/w/d|f/m/d|w/m/d", normalized) is not None


def dedupe_jobs(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    unique_jobs: List[Dict[str, Any]] = []
    for job in jobs:
        key = (
            (job.get("company") or "").lower(),
            (job.get("title") or "").lower(),
            (job.get("apply_link") or "").lower(),
        )
        if key in seen or not job.get("apply_link"):
            continue
        seen.add(key)
        unique_jobs.append(job)
    return unique_jobs


def is_blog_or_story(job: Dict[str, Any]) -> bool:
    link = (job.get("apply_link") or "").lower()
    if any(pattern in link for pattern in NOISE_URL_PATTERNS):
        return True

    title = job.get("title") or ""
    return any(re.search(pattern, title, re.IGNORECASE) for pattern in NOISE_TITLE_PATTERNS)


def is_match(job: Dict[str, Any]) -> bool:
    title = (job.get("title") or "").lower()
    if not title:
        return False

    if is_blog_or_story(job):
        return False

    normalized_title = re.sub(r"[^a-z0-9]+", " ", title).strip()
    if any(term in normalized_title for term in DATA_ENGINEER_TERMS):
        return True

    if not any(word in normalized_title for word in GENERIC_ROLE_WORDS):
        return False

    description = (job.get("description") or "").lower()
    return any(skill in description for skill in DATA_TECH_SKILLS)


def is_recent(job: Dict[str, Any], days: int = RECENT_DAYS) -> bool:
    date_text = job.get("posted_or_updated_date") or ""
    parsed = None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            parsed = datetime.strptime(date_text, fmt)
            break
        except ValueError:
            continue
    if not parsed:
        return False
    return parsed >= datetime.now() - timedelta(days=days)


def extract_date_from_card(card: Any) -> str:
    for selector in ["time[datetime]", "time", "[datetime]", ".date", ".posted", ".updated"]:
        el = card.select_one(selector)
        if not el:
            continue
        value = el.get("datetime") or el.get_text(" ", strip=True)
        if value:
            return normalize_date(value)

    text = card.get_text(" ", strip=True)
    match = re.search(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}\.\d{1,2}\.\d{2,4}\b", text)
    return match.group(0) if match else ""


def iter_jsonld_items(value: Any) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if isinstance(value, dict):
        item_type = value.get("@type")
        if item_type == "JobPosting" or (isinstance(item_type, list) and "JobPosting" in item_type):
            items.append(value)
        for nested in value.values():
            items.extend(iter_jsonld_items(nested))
    elif isinstance(value, list):
        for nested in value:
            items.extend(iter_jsonld_items(nested))
    return items


def extract_jsonld_jobs(soup: BeautifulSoup, url: str, fallback_company: str) -> List[Dict[str, Any]]:
    from urllib.parse import urljoin
    jobs: List[Dict[str, Any]] = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.string or script.get_text() or "{}")
        except json.JSONDecodeError:
            continue

        for item in iter_jsonld_items(payload):
            organization = item.get("hiringOrganization") or {}
            if isinstance(organization, list):
                organization = organization[0] if organization else {}
            company = organization.get("name") if isinstance(organization, dict) else ""
            apply_link = item.get("url") or item.get("sameAs") or url
            jobs.append(make_job(
                company or fallback_company,
                item.get("title") or "",
                item.get("datePosted") or item.get("dateModified") or item.get("validThrough") or "",
                urljoin(url, apply_link),
                url,
                clean_text(item.get("description") or ""),
            ))
    return [job for job in jobs if job["title"]]


def extract_jobs_from_html(html: str, candidate_url: str, fallback_company: str) -> List[Dict[str, Any]]:
    from urllib.parse import urljoin
    soup = BeautifulSoup(html, "html.parser")
    jsonld_jobs = extract_jsonld_jobs(soup, candidate_url, fallback_company)
    if jsonld_jobs:
        return dedupe_jobs(jsonld_jobs)

    jobs: List[Dict[str, Any]] = []
    card_selectors = (
        '[class*="job"]', '[data-testid*="job"]', 'article', 'li', '.result', '.card',
    )
    for card in soup.select(", ".join(card_selectors)):
        title = ""
        for selector in ["h1", "h2", "h3", ".title", ".job-title", '[class*="title"]', "a"]:
            el = card.select_one(selector)
            if el and el.get_text(strip=True):
                title = clean_text(el.get_text(" ", strip=True))
                break
        if not title or len(title) < 4:
            continue

        company = fallback_company
        for selector in [".company", ".employer", ".org", ".company-name", '[class*="company"]']:
            el = card.select_one(selector)
            if el and el.get_text(strip=True):
                company = clean_text(el.get_text(" ", strip=True))
                break

        card_links = [(link.get("href") or "").strip() for link in card.select("a[href]")]
        card_links = [href for href in card_links if href and href != "#"]

        career_link = ""
        for href in card_links:
            if re.search(r"(job|position|posting|req|vacancy)[-_]?(id)?=\d+|/\d{4,}(/|$|\?)", href.lower()):
                career_link = urljoin(candidate_url, href)
                break
        if not career_link:
            for href in card_links:
                if any(keyword in href.lower() for keyword in JOB_LINK_KEYWORDS):
                    resolved = urljoin(candidate_url, href)
                    if resolved.rstrip("/") != candidate_url.rstrip("/"):
                        career_link = resolved
                        break
        if not career_link and card_links:
            career_link = urljoin(candidate_url, card_links[0])

        description = card.get_text(" ", strip=True)
        if not is_probable_scraped_title(title, career_link or candidate_url):
            continue
        if career_link and title not in description[:400]:
            continue
        jobs.append(make_job(company, title, extract_date_from_card(card), career_link or candidate_url, candidate_url, description))

    return dedupe_jobs(jobs)


def discover_career_urls(company: str, limit: int = 3) -> List[str]:
    from urllib.parse import unquote
    if not company:
        return []

    try:
        response = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": f"{company} careers jobs"},
            headers=HEADERS,
            timeout=15,
        )
        response.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    urls: List[str] = []
    for a in soup.select("a.result__a"):
        href = a.get("href") or ""
        match = re.search(r"uddg=([^&]+)", href)
        if not match:
            continue
        target = unquote(match.group(1))
        if not is_url(target):
            continue
        if any(domain in target.lower() for domain in AGGREGATOR_DOMAINS):
            continue
        urls.append(target)
        if len(urls) >= limit:
            break
    return urls


async def dismiss_cookie_banner(page) -> None:
    for selector in COOKIE_ACCEPT_SELECTORS:
        try:
            await page.locator(selector).first.click(timeout=1200)
            return
        except Exception:
            continue

    # Some CMPs (Sourcepoint, Quantcast) render the banner inside an iframe,
    # unreachable via page-level locators.
    for frame in page.frames:
        for selector in COOKIE_ACCEPT_SELECTORS:
            try:
                await frame.locator(selector).first.click(timeout=800)
                return
            except Exception:
                continue


async def render_html(context: BrowserContext, url: str) -> tuple[str, str]:
    page = await context.new_page()
    try:
        await page.goto(url, timeout=PAGE_GOTO_TIMEOUT_MS, wait_until="domcontentloaded")
        await dismiss_cookie_banner(page)
        try:
            await page.wait_for_load_state("networkidle", timeout=PAGE_IDLE_TIMEOUT_MS)
        except Exception:
            pass
        return page.url, await page.content()
    finally:
        await page.close()


# ── ATS direct APIs (Greenhouse / Ashby / Lever / Personio / Workable / BambooHR) ──
# When a company's career page is hosted on (or redirects to) one of these
# platforms, their public job-board API gives structured data with a real
# per-job apply link — far more reliable than scraping rendered HTML.

def detect_ats(url: str) -> tuple[str, str] | None:
    lower = url.lower()
    match = re.search(r"boards\.greenhouse\.io/([^/?#]+)", lower)
    if match:
        return "greenhouse", match.group(1)
    match = re.search(r"job-boards(?:\.[a-z]{2})?\.greenhouse\.io/([^/?#]+)", lower)
    if match:
        return "greenhouse", match.group(1)
    match = re.search(r"jobs\.ashbyhq\.com/([^/?#]+)", lower)
    if match:
        return "ashby", match.group(1)
    match = re.search(r"jobs(?:\.[a-z]{2})?\.lever\.co/([^/?#]+)", lower)
    if match:
        return "lever", match.group(1)
    match = re.search(r"([a-z0-9-]+)\.jobs\.personio\.(?:de|com)", lower)
    if match:
        return "personio", match.group(1)
    match = re.search(r"apply\.workable\.com/([^/?#]+)", lower)
    if match:
        return "workable", match.group(1)
    match = re.search(r"([a-z0-9-]+)\.bamboohr\.com", lower)
    if match:
        return "bamboohr", match.group(1)
    return None


def fetch_ats_jobs(platform: str, slug: str, company: str) -> List[Dict[str, Any]]:
    try:
        if platform == "greenhouse":
            resp = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                return []
            jobs = resp.json().get("jobs", [])
            return [
                make_job(
                    company, job.get("title", ""), (job.get("updated_at") or "")[:10],
                    job.get("absolute_url", ""), job.get("absolute_url", ""),
                    (job.get("location") or {}).get("name", ""),
                )
                for job in jobs if job.get("title") and job.get("absolute_url")
            ]
        if platform == "ashby":
            resp = requests.post(
                "https://api.ashbyhq.com/posting-public/job-board",
                json={"organizationHostedJobsPageName": slug}, headers=HEADERS, timeout=10,
            )
            if resp.status_code != 200:
                return []
            jobs = resp.json().get("jobPostings", [])
            return [
                make_job(
                    company, job.get("title", ""), (job.get("publishedAt") or "")[:10],
                    job.get("externalLink") or f"https://jobs.ashbyhq.com/{slug}/{job.get('id', '')}",
                    job.get("externalLink") or f"https://jobs.ashbyhq.com/{slug}",
                )
                for job in jobs if job.get("title")
            ]
        if platform == "lever":
            resp = requests.get(f"https://api.lever.co/v0/postings/{slug}?mode=json", headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                return []
            jobs = resp.json()
            return [
                make_job(
                    company, job.get("text", ""),
                    datetime.fromtimestamp(job["createdAt"] / 1000).strftime("%Y-%m-%d") if job.get("createdAt") else "",
                    job.get("hostedUrl", ""), job.get("hostedUrl", ""),
                    (job.get("descriptionPlain") or "")[:500],
                )
                for job in jobs if job.get("text") and job.get("hostedUrl")
            ]
        if platform == "personio":
            resp = requests.get(f"https://{slug}.jobs.personio.de/xml", headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                return []
            root = ET.fromstring(resp.content)
            jobs = []
            for position in root.findall("position"):
                job_id = (position.findtext("id") or "").strip()
                title = (position.findtext("name") or "").strip()
                created = (position.findtext("createdAt") or "")[:10]
                if not job_id or not title:
                    continue
                url = f"https://{slug}.jobs.personio.de/job/{job_id}"
                jobs.append(make_job(company, title, created, url, url))
            return jobs
        if platform == "workable":
            resp = requests.get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}", headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                return []
            jobs = resp.json().get("jobs", [])
            return [
                make_job(
                    company, job.get("title", ""), job.get("published_on", ""),
                    job.get("application_url") or job.get("url", ""), job.get("url", ""),
                )
                for job in jobs if job.get("title") and job.get("url")
            ]
        if platform == "bamboohr":
            resp = requests.get(f"https://{slug}.bamboohr.com/careers/list", headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                return []
            jobs = resp.json().get("result", [])
            return [
                make_job(
                    company, job.get("jobOpeningName", ""), "",
                    f"https://{slug}.bamboohr.com/careers/{job.get('id', '')}",
                    f"https://{slug}.bamboohr.com/careers/{job.get('id', '')}",
                )
                for job in jobs if job.get("jobOpeningName") and job.get("id")
            ]
    except Exception:
        return []
    return []


async def resolve_career_urls(company: str, cached_links: Dict[str, List[str]]) -> List[str]:
    if not company:
        return []
    cached = cached_links.get(company.lower())
    if cached:
        return cached
    return await asyncio.to_thread(discover_career_urls, company)


def fetch_static_html(url: str) -> tuple[str, str]:
    """Plain HTTP GET — much faster than a headless browser, and sufficient
    for the many career pages that are server-rendered rather than JS-only."""
    resp = requests.get(url, headers=HEADERS, timeout=8, allow_redirects=True)
    resp.raise_for_status()
    return resp.url, resp.text


async def fetch_jobs_async(
    context: BrowserContext, company: str, apply_link: str, discovered_urls: List[str],
    browser_semaphore: asyncio.Semaphore,
    cached_url: str = "",
) -> tuple[List[Dict[str, Any]], str]:
    candidates = ([cached_url] if cached_url else []) + discovered_urls + build_candidate_urls(apply_link)
    candidates = list(dict.fromkeys(url for url in candidates if is_url(url)))

    for candidate_url in candidates:
        # Fast path: try a plain HTTP GET first, skip the browser entirely if it works.
        # Deliberately NOT gated by browser_semaphore — it never touches Chromium.
        try:
            final_url, html = await asyncio.to_thread(fetch_static_html, candidate_url)
            ats = detect_ats(final_url) or detect_ats(candidate_url)
            if ats:
                platform, slug = ats
                ats_jobs = await asyncio.to_thread(fetch_ats_jobs, platform, slug, company)
                if ats_jobs:
                    return ats_jobs, candidate_url
            jobs = extract_jobs_from_html(html, candidate_url, company)
            if jobs:
                return jobs, candidate_url
        except Exception:
            pass

        # Slow path: fall back to a real headless browser for JS-rendered pages.
        # Only this step competes for the smaller browser-page concurrency budget.
        try:
            async with browser_semaphore:
                final_url, html = await render_html(context, candidate_url)
        except Exception:
            continue

        ats = detect_ats(final_url) or detect_ats(candidate_url)
        if ats:
            platform, slug = ats
            ats_jobs = await asyncio.to_thread(fetch_ats_jobs, platform, slug, company)
            if ats_jobs:
                return ats_jobs, candidate_url

        jobs = extract_jobs_from_html(html, candidate_url, company)
        if jobs:
            return jobs, candidate_url

    return [], ""


def extract_sources_from_file(path: Path) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    raw_items: List[Dict[str, Any]] = []
    if isinstance(payload, dict):
        raw_items = [item for item in payload.get("Bewerbungen", []) if isinstance(item, dict)]
    elif isinstance(payload, list):
        raw_items = [item for item in payload if isinstance(item, dict)]

    sources: List[Dict[str, Any]] = []
    for item in raw_items:
        link = clean_text(item.get("careers") or item.get("career_link") or item.get("Link"))
        if not is_url(link):
            continue
        sources.append({
            "company": clean_text(item.get("Firma") or item.get("name") or item.get("company")),
            "title": clean_text(item.get("Tätigkeit") or item.get("title")),
            "posted_or_updated_date": normalize_date(item.get("Datum") or item.get("posted_or_updated_date")),
            "apply_link": link,
        })
    return sources


def load_sources(path: Path) -> List[Dict[str, Any]]:
    sources: List[Dict[str, Any]] = []
    seen = set()
    if not path.exists():
        return sources
    for source in extract_sources_from_file(path):
        key = (source["company"].lower(), source["apply_link"].lower())
        if key in seen:
            continue
        seen.add(key)
        sources.append(source)
    return sources


def save_jobs(jobs: List[Dict[str, Any]], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False)


def save_discovered_cache(entries: List[Dict[str, Any]], path: Path = DISCOVERED_CACHE_PATH) -> None:
    seen = set()
    unique_entries: List[Dict[str, Any]] = []

    for entry in entries:
        company = (entry.get("company") or "").strip()
        career_link = (entry.get("career_link") or "").strip()
        if not company or not career_link:
            continue

        key = (company.lower(), career_link.lower())
        if key in seen:
            continue

        seen.add(key)
        unique_entries.append({"company": company, "career_link": career_link})

    with open(path, "w", encoding="utf-8") as f:
        json.dump(unique_entries, f, indent=2, ensure_ascii=False)


def load_discovered_cache(path: Path = DISCOVERED_CACHE_PATH) -> Dict[str, List[str]]:
    if not path.exists():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    links_by_company: Dict[str, List[str]] = {}
    for entry in entries:
        company = (entry.get("company") or "").strip().lower()
        career_link = (entry.get("career_link") or "").strip()
        if not company or not career_link:
            continue
        links_by_company.setdefault(company, [])
        if career_link not in links_by_company[company]:
            links_by_company[company].append(career_link)

    return links_by_company


def load_working_url_cache(path: Path = WORKING_URL_CACHE_PATH) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_working_url_cache(cache: Dict[str, str], path: Path = WORKING_URL_CACHE_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def load_timeout_cache(path: Path = TIMEOUT_CACHE_PATH) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_timeout_cache(cache: Dict[str, str], path: Path = TIMEOUT_CACHE_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def in_timeout_cooldown(company: str, timeout_cache: Dict[str, str]) -> bool:
    last_timeout = timeout_cache.get(company.lower())
    if not last_timeout:
        return False
    try:
        last_date = datetime.strptime(last_timeout, "%Y-%m-%d").date()
    except ValueError:
        return False
    return date.today() - last_date < timedelta(days=TIMEOUT_COOLDOWN_DAYS)


async def collect_jobs_for_source(
    context: BrowserContext,
    source: Dict[str, Any],
    http_semaphore: asyncio.Semaphore,
    browser_semaphore: asyncio.Semaphore,
    cached_links: Dict[str, List[str]],
    working_url_cache: Dict[str, str],
    timeout_cache: Dict[str, str],
) -> tuple[List[Dict[str, Any]], List[str], str]:
    company = source.get("company", "")
    discovered: List[str] = []

    # A company with no working_url_cache entry that timed out recently has
    # nowhere to "retry from cache" — skip the attempt entirely instead of
    # re-burning the full PER_COMPANY_TIMEOUT_S budget on the same dead
    # candidates every run. Cleared automatically once the run below succeeds.
    if not working_url_cache.get(company.lower()) and in_timeout_cooldown(company, timeout_cache):
        print(f"Skipping {source.get('apply_link')}: timed out on {timeout_cache.get(company.lower())}, "
              f"cooling down for {TIMEOUT_COOLDOWN_DAYS}d before retrying")
        return [], [], ""

    async with http_semaphore:
        try:
            # Skip the DuckDuckGo discovery lookup entirely when we already have
            # a curated apply_link — it's the common case here, and the discovery
            # step exists only for sources that arrive with no known URL at all.
            apply_link = source.get("apply_link", "")
            discovered = [] if apply_link else await resolve_career_urls(company, cached_links)
            jobs, winning_url = await asyncio.wait_for(
                fetch_jobs_async(
                    context, company, apply_link, discovered, browser_semaphore,
                    cached_url=working_url_cache.get(company.lower(), ""),
                ),
                timeout=PER_COMPANY_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            print(f"Skipping {source.get('apply_link')}: exceeded {PER_COMPANY_TIMEOUT_S}s budget "
                  f"(dead/slow candidate URLs) — will retry from cache next run")
            return [], [], ""
        except Exception as exc:
            print(f"Skipping {source.get('apply_link')}: {exc}")
            return [], [], ""

    return jobs, discovered, winning_url


def route_to_pipeline(matched_jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Dedup matched_jobs against tracked history, score them the same way
    scrape_jobs.py does (for sorting/dashboard filtering), then append ALL
    of them to data/pipeline.md — score/title/language are shown, not used
    to drop results, since the dashboard already has filters for score and
    the user would rather see everything the crawl found than have it
    silently decided for them."""
    profile = load_profile()
    # Composite (url, title) key: some company career pages have no stable
    # per-job permalink and return the SAME generic URL for every listing
    # (e.g. Infosys's search-results page) — URL-only dedup would then treat
    # distinct job postings as duplicates of each other and drop all but one.
    seen_urls = load_tracked_url_pairs()
    # Seeded with historical pairs so a job already found via LinkedIn/Indeed/
    # ATS boards (a different URL) doesn't get re-added here under this
    # crawler's own URL for the same company+title.
    session_pairs = load_tracked_pairs()
    pipeline_matches = []

    for job in matched_jobs:
        title = (job.get("title") or "").strip()
        company = (job.get("company") or "").strip()
        url = (job.get("apply_link") or job.get("source_url") or "").strip()
        desc = job.get("description") or ""

        if not title or not company or not url:
            continue

        url_key = (url.lower(), normalize_title(title))
        if url_key in seen_urls:
            continue
        seen_urls.add(url_key)

        pair = (company.lower(), normalize_title(title))
        if pair in session_pairs:
            continue
        session_pairs.add(pair)

        score = score_job(title, desc, profile)

        pipeline_matches.append({
            "title":       title,
            "company":     company,
            "location":    "—",  # not tracked by this crawler today
            "score":       score,
            "job_url":     url,
            "is_remote":   "remote" in (title + " " + desc).lower(),
            "source":      "company-crawl",
            "date_posted": job.get("posted_or_updated_date") or "—",
        })

    pipeline_matches.sort(key=lambda x: x["score"], reverse=True)
    append_to_pipeline(pipeline_matches)

    LAST_RUN_PATH.write_text(json.dumps({
        "date":      date.today().isoformat(),
        "timestamp": datetime.now().isoformat(),
        "count":     len(pipeline_matches),
        "urls":      [m["job_url"] for m in pipeline_matches],
    }, indent=2), encoding="utf-8")

    return pipeline_matches


def _quiet_orphaned_playwright_errors(loop, context) -> None:
    """PER_COMPANY_TIMEOUT_S cancels a company's task mid-flight, which can
    happen while a Playwright operation (e.g. a cookie-banner click inside
    dismiss_cookie_banner) is still waiting on the browser. Playwright's
    internal per-command future then resolves after the page/context is
    already closed, and asyncio logs "Future exception was never retrieved"
    since nothing is left awaiting it. This is the expected result of an
    intentional timeout, not a real error — filter just this pattern;
    anything else still goes to the default handler so real bugs aren't
    hidden."""
    exception = context.get("exception")
    if isinstance(exception, PlaywrightError):
        return
    loop.default_exception_handler(context)


async def run(input_path: Path = INPUT_LINK_FILE, output_path: Path = OUTPUT_JOBS_FILE) -> None:
    sources = load_sources(input_path)
    cached_links = load_discovered_cache()
    working_url_cache = load_working_url_cache()

    asyncio.get_event_loop().set_exception_handler(_quiet_orphaned_playwright_errors)

    # asyncio.to_thread() (used by fetch_static_html/fetch_ats_jobs/resolve_career_urls)
    # runs on the event loop's default executor, which defaults to only
    # min(32, cpu_count+4) worker threads — that ceiling would silently cap
    # the fast HTTP path's real concurrency well below MAX_CONCURRENT_HTTP
    # regardless of the semaphore size. Raise it explicitly.
    asyncio.get_event_loop().set_default_executor(
        concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT_HTTP)
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=HEADERS["User-Agent"], ignore_https_errors=True)
        http_semaphore = asyncio.Semaphore(MAX_CONCURRENT_HTTP)
        browser_semaphore = asyncio.Semaphore(MAX_CONCURRENT_PAGES)

        results = await asyncio.gather(
            *(collect_jobs_for_source(context, source, http_semaphore, browser_semaphore, cached_links, working_url_cache)
              for source in sources)
        )

        await browser.close()

    all_jobs: List[Dict[str, Any]] = [job for jobs, _, _ in results for job in jobs]

    link_entries = [
        {"company": source.get("company", ""), "career_link": url}
        for source, (_, discovered, _) in zip(sources, results)
        for url in discovered
    ]
    save_discovered_cache(link_entries)

    for source, (_, _, winning_url) in zip(sources, results):
        company = (source.get("company") or "").lower()
        if company and winning_url:
            working_url_cache[company] = winning_url
    save_working_url_cache(working_url_cache)

    matched_jobs = [job for job in dedupe_jobs(all_jobs) if is_match(job)]
    for job in matched_jobs:
        job["is_recent"] = is_recent(job)
    recent_count = sum(1 for job in matched_jobs if job["is_recent"])
    save_jobs(matched_jobs, output_path)

    print(f"Loaded {len(sources)} source links")
    print(f"Found {len(matched_jobs)} data engineer/analytics/BI jobs, {recent_count} posted in the last {RECENT_DAYS} days")
    print(f"Saved {len(matched_jobs)} jobs to {output_path}")
    print(f"Cached {len(link_entries)} discovered career links to {DISCOVERED_CACHE_PATH}")

    pipeline_matches = route_to_pipeline(matched_jobs)
    print(f"Routed {len(pipeline_matches)} of {len(matched_jobs)} into data/pipeline.md "
          f"(rest: already tracked, excluded title, non-English, or below score threshold)")


def main() -> None:
    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else INPUT_LINK_FILE
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else OUTPUT_JOBS_FILE
    asyncio.run(run(input_path, output_path))


if __name__ == "__main__":
    main()
