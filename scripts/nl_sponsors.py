"""
Netherlands IND "Erkend Referent" (Recognized Sponsor) register.

Public register of ~13,000 organizations authorized by the Dutch immigration
service (IND) to sponsor non-EU workers, including Highly Skilled Migrant
(kennismigrant) visas. Checked against robots.txt (allowed) and the register
is a single server-rendered HTML table — no pagination, no JS, no API key
needed. Cached locally and refreshed monthly, matching the IND's own update
cadence ("de openbare registers worden maandelijks bijgewerkt").

Source: https://ind.nl/nl/openbaar-register-erkende-referenten/openbaar-register-arbeid
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import requests

ROOT         = Path(__file__).parent.parent
CACHE_PATH   = ROOT / "data" / ".ind-sponsors-cache.json"
REGISTER_URL = "https://ind.nl/nl/openbaar-register-erkende-referenten/openbaar-register-arbeid"
CACHE_MAX_AGE_DAYS = 30

DUTCH_LOCATION_HINTS = (
    "netherlands", "nederland", ", nl", "(nl)",
    "amsterdam", "rotterdam", "the hague", "den haag", "utrecht",
    "eindhoven", "groningen", "tilburg", "almere", "breda", "nijmegen",
    "haarlem", "arnhem", "leiden", "delft", "maastricht", "zwolle",
)

_LEGAL_SUFFIXES = re.compile(
    r'\b(b\.?v\.?|n\.?v\.?|holding|group|gmbh|ltd|inc|corp|co|ag|se|plc|llc)\b',
    re.IGNORECASE,
)


def normalize_company(name: str) -> str:
    """Lowercase, strip legal suffixes and punctuation for fuzzy matching."""
    n = name.lower()
    n = _LEGAL_SUFFIXES.sub(' ', n)
    n = re.sub(r'[^\w\s]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n


def is_netherlands_location(location: str) -> bool:
    loc = (location or "").lower()
    return any(hint in loc for hint in DUTCH_LOCATION_HINTS)


def _fetch_register():
    """Download and parse the full IND sponsor table. Returns list of raw company names."""
    resp = requests.get(
        REGISTER_URL,
        headers={"User-Agent": "career-ops-plugin/1.0 (personal job search tool)"},
        timeout=30,
    )
    resp.raise_for_status()
    html = resp.text

    names = []
    for row_match in re.finditer(
        r'<th scope="row">(.*?)</th>\s*<td>(\d+)</td>', html, re.DOTALL
    ):
        name = re.sub(r'<[^>]+>', '', row_match.group(1)).strip()
        if name:
            names.append(name)
    return names


def load_sponsor_set(force_refresh=False):
    """Returns a set of normalized recognized-sponsor company names, using a
    30-day local cache to avoid hammering ind.nl on every scrape/dashboard run."""
    if not force_refresh and CACHE_PATH.exists():
        try:
            cached = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(cached["fetched_at"])
            if datetime.now() - fetched_at < timedelta(days=CACHE_MAX_AGE_DAYS):
                return set(cached["normalized_names"])
        except Exception:
            pass  # corrupt/missing cache — fall through to refetch

    try:
        raw_names = _fetch_register()
    except Exception as e:
        print(f"   [WARN] Could not fetch IND sponsor register: {e}")
        if CACHE_PATH.exists():
            cached = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            return set(cached["normalized_names"])
        return set()

    normalized = sorted({normalize_company(n) for n in raw_names if n})
    CACHE_PATH.write_text(
        json.dumps({
            "fetched_at": datetime.now().isoformat(),
            "source": REGISTER_URL,
            "company_count": len(raw_names),
            "normalized_names": normalized,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return set(normalized)


def is_recognized_sponsor(company_name: str, sponsor_set: set) -> bool:
    return normalize_company(company_name) in sponsor_set


if __name__ == "__main__":
    sponsors = load_sponsor_set(force_refresh="--refresh" in __import__("sys").argv)
    print(f"Loaded {len(sponsors)} recognized NL sponsors (cache: {CACHE_PATH})")
