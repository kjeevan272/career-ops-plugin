"""
Orchestrator: runs scrape_jobs.py and scrape_company_careers.py in parallel
as separate subprocesses, then merges their "what's new" state and
regenerates the single pipeline dashboard.

Deliberately does NOT merge the two scrapers into one process — they have
incompatible concurrency models (threaded requests vs asyncio/Playwright)
and very different runtimes (~1-6 min vs ~3-10 min). Running them as
independent processes means a hang/crash in one never blocks the other, and
neither has to carry the other's dependencies. See the module docstrings on
each script for the full reasoning.

Usage:
    python scripts/full_scan.py            # scrape_jobs.py daily mode
    python scripts/full_scan.py --full     # scrape_jobs.py --full mode
    python scripts/full_scan.py --quick    # scrape_jobs.py --quick mode
    (scrape_company_careers.py has no modes — it always runs its one pass)
"""

import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT               = Path(__file__).parent
JOBS_LAST_RUN      = ROOT.parent / "data" / ".last-run.json"
COMPANY_LAST_RUN   = ROOT.parent / "data" / ".last-run-company.json"
COMBINED_LAST_RUN  = JOBS_LAST_RUN  # generate_dashboard.py reads this one


def _tee(proc: subprocess.Popen, label: str) -> None:
    for line in proc.stdout:
        print(f"[{label}] {line}", end="")


def main() -> None:
    mode_flag = next((a for a in sys.argv[1:] if a in ("--quick", "--full")), None)
    scrape_cmd = [sys.executable, str(ROOT / "scrape_jobs.py")] + ([mode_flag] if mode_flag else [])
    crawl_cmd = [sys.executable, str(ROOT / "scrape_company_careers.py")]

    print(">> Launching scrape_jobs.py and scrape_company_careers.py in parallel...")
    p1 = subprocess.Popen(scrape_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    p2 = subprocess.Popen(crawl_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

    # Stream both concurrently via threads so neither's output blocks the other.
    import threading
    t1 = threading.Thread(target=_tee, args=(p1, "scrape_jobs"))
    t2 = threading.Thread(target=_tee, args=(p2, "company_crawl"))
    t1.start(); t2.start()
    t1.join(); t2.join()
    rc1, rc2 = p1.wait(), p2.wait()

    if rc1 != 0:
        print(f"[WARN] scrape_jobs.py exited with code {rc1}")
    if rc2 != 0:
        print(f"[WARN] scrape_company_careers.py exited with code {rc2}")

    print("\n>> Merging run state so the dashboard shows new roles from both...")
    urls = set()
    for path in (JOBS_LAST_RUN, COMPANY_LAST_RUN):
        if path.exists():
            try:
                urls.update(json.loads(path.read_text(encoding="utf-8")).get("urls", []))
            except Exception:
                pass

    COMBINED_LAST_RUN.write_text(json.dumps({
        "date":      date.today().isoformat(),
        "timestamp": datetime.now().isoformat(),
        "count":     len(urls),
        "urls":      sorted(urls),
    }, indent=2), encoding="utf-8")
    print(f"   {len(urls)} new job(s) combined across both scrapers")

    print("\n>> Regenerating dashboard...")
    subprocess.run([sys.executable, str(ROOT / "generate_dashboard.py")], check=False)


if __name__ == "__main__":
    main()
