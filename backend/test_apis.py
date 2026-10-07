"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           AI JOB FINDER — API HEALTH & EXTRACTION TEST SCRIPT               ║
║                                                                              ║
║  Tests all 4 job source adapters:                                            ║
║    1. Greenhouse  (boards-api.greenhouse.io)                                 ║
║    2. RemoteOK    (remoteok.com/api)                                         ║
║    3. Workday     (*.myworkdayjobs.com)                                      ║
║    4. Lever       (api.lever.co)                                             ║
║                                                                              ║
║  For each source it checks:                                                  ║
║    ✓ API reachability (HTTP status)                                          ║
║    ✓ Response format is parseable                                            ║
║    ✓ At least some raw jobs are returned                                     ║
║    ✓ Jobs pass through the adapter filters correctly                         ║
║    ✓ JobPosting objects are properly constructed                             ║
╚══════════════════════════════════════════════════════════════════════════════╝

Usage (from backend/ directory):
    python test_apis.py               # run all tests
    python test_apis.py greenhouse    # run only greenhouse
    python test_apis.py remoteok lever # run two sources
    python test_apis.py --no-adapter  # skip adapter integration tests
"""

import asyncio
import json
import sys
import time
from datetime import datetime
from typing import List, Dict, Any

import httpx

# ── Colour helpers (works on Windows 10+ with ANSI) ──────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):   print(f"  {GREEN}✓{RESET}  {msg}")
def fail(msg): print(f"  {RED}✗{RESET}  {msg}")
def warn(msg): print(f"  {YELLOW}⚠{RESET}  {msg}")
def info(msg): print(f"  {CYAN}ℹ{RESET}  {msg}")

# ── Shared User-Agent ─────────────────────────────────────────────────────────
UA = "AIJobFinder-Client/1.0 (Job Matching Review Bot; contact@aijobfinder.local)"
HEADERS = {"User-Agent": UA}

# ═════════════════════════════════════════════════════════════════════════════
# GREENHOUSE
# ═════════════════════════════════════════════════════════════════════════════
GREENHOUSE_TEST_BOARDS = [
    "github",
    "gitlab",
    "canonical",
    "razorpay",
    "postman",
]

async def test_greenhouse(client: httpx.AsyncClient) -> Dict[str, Any]:
    print(f"\n{BOLD}{CYAN}━━━ GREENHOUSE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
    print(f"  Endpoint: https://boards-api.greenhouse.io/v1/boards/{{board}}/jobs?content=true")
    print(f"  Testing {len(GREENHOUSE_TEST_BOARDS)} boards: {', '.join(GREENHOUSE_TEST_BOARDS)}\n")

    results = {}
    total_raw = 0
    total_filtered = 0

    for board in GREENHOUSE_TEST_BOARDS:
        url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
        t0 = time.monotonic()
        try:
            resp = await client.get(url, headers=HEADERS, timeout=15.0)
            elapsed = time.monotonic() - t0

            if resp.status_code == 404:
                warn(f"[{board}] Board not found (404) — company may not use Greenhouse")
                results[board] = {"status": "not_found", "raw_jobs": 0, "filtered_jobs": 0}
                continue

            if resp.status_code != 200:
                fail(f"[{board}] HTTP {resp.status_code} ({elapsed:.2f}s)")
                results[board] = {"status": f"http_{resp.status_code}", "raw_jobs": 0, "filtered_jobs": 0}
                continue

            data = resp.json()
            raw_jobs = data.get("jobs", [])
            total_raw += len(raw_jobs)

            # Apply our filters inline (mirrors the actual adapter logic)
            tech_keywords = ["engineer", "developer", "software", "sde", "backend", "frontend",
                             "data", "ml", "devops", "cloud", "mobile", "intern", "junior", "graduate"]
            senior_keywords = ["senior", "sr.", "lead ", "staff ", "principal", "director",
                               "head of", "vp ", "architect", "manager", "cto"]
            india_keywords = ["india", "bengaluru", "bangalore", "hyderabad", "pune", "mumbai",
                              "delhi", "gurugram", "remote", "anywhere", "worldwide", "wfh", "hybrid"]

            filtered = []
            for j in raw_jobs:
                title = j.get("title", "").lower()
                loc = j.get("location", {})
                location = (loc.get("name", "") if isinstance(loc, dict) else "").lower()

                is_tech = any(kw in title for kw in tech_keywords)
                is_senior = any(kw in title for kw in senior_keywords)
                is_india = any(kw in location for kw in india_keywords)

                if is_tech and not is_senior and is_india:
                    filtered.append(j.get("title"))

            total_filtered += len(filtered)

            ok(f"[{board}] {resp.status_code} OK | {len(raw_jobs)} raw jobs | "
               f"{len(filtered)} India/junior tech jobs | {elapsed:.2f}s")

            if filtered:
                for t in filtered[:3]:
                    info(f"      -> {t}")
                if len(filtered) > 3:
                    info(f"      ... and {len(filtered) - 3} more")

            results[board] = {
                "status": "ok",
                "http_status": resp.status_code,
                "raw_jobs": len(raw_jobs),
                "filtered_jobs": len(filtered),
                "sample": filtered[:3],
                "response_time_s": round(elapsed, 2)
            }

        except httpx.TimeoutException:
            fail(f"[{board}] TIMEOUT after 15s")
            results[board] = {"status": "timeout", "raw_jobs": 0, "filtered_jobs": 0}
        except Exception as e:
            fail(f"[{board}] ERROR — {e}")
            results[board] = {"status": f"error: {e}", "raw_jobs": 0, "filtered_jobs": 0}

    print(f"\n  {BOLD}Greenhouse summary: {total_raw} total raw jobs, "
          f"{total_filtered} matched India/junior tech{RESET}")
    return {"source": "greenhouse", "boards_tested": len(GREENHOUSE_TEST_BOARDS),
            "total_raw": total_raw, "total_filtered": total_filtered, "details": results}


# ═════════════════════════════════════════════════════════════════════════════
# REMOTEOK
# ═════════════════════════════════════════════════════════════════════════════
async def test_remoteok(client: httpx.AsyncClient) -> Dict[str, Any]:
    print(f"\n{BOLD}{CYAN}━━━ REMOTEOK ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
    url = "https://remoteok.com/api"
    print(f"  Endpoint: {url}\n")

    t0 = time.monotonic()
    try:
        resp = await client.get(url, headers=HEADERS, timeout=20.0)
        elapsed = time.monotonic() - t0

        if resp.status_code != 200:
            fail(f"HTTP {resp.status_code} ({elapsed:.2f}s)")
            return {"source": "remoteok", "status": f"http_{resp.status_code}",
                    "raw_jobs": 0, "filtered_jobs": 0}

        ok(f"HTTP {resp.status_code} OK | {elapsed:.2f}s")

        data = resp.json()
        job_items = [item for item in data if isinstance(item, dict) and "id" in item]
        info(f"Raw items in response: {len(data)} | Job objects (with 'id'): {len(job_items)}")

        tech_keywords = ["engineer", "developer", "software", "backend", "frontend",
                         "fullstack", "data", "ml", "devops", "cloud", "python",
                         "javascript", "react", "node", "intern", "junior"]
        senior_keywords = ["senior", "sr.", "lead ", "staff ", "principal", "director",
                           "head of", "vp ", "architect", "manager", "cto"]
        tech_tags = {"python", "javascript", "typescript", "react", "node.js", "developer", "engineer"}

        filtered = []
        for item in job_items:
            title = item.get("position", "")
            tags  = [t.lower() for t in item.get("tags", [])]
            title_lower = title.lower()
            is_tech   = any(kw in title_lower for kw in tech_keywords) or bool(tech_tags.intersection(tags))
            is_senior = any(kw in title_lower for kw in senior_keywords)
            if is_tech and not is_senior:
                filtered.append({
                    "title": title,
                    "company": item.get("company", "?"),
                    "salary": f"${item.get('salary_min', '?')}–${item.get('salary_max', '?')}",
                    "tags": tags[:5]
                })

        ok(f"Raw jobs: {len(job_items)} | Filtered tech jobs: {len(filtered)}")

        if filtered:
            print()
            for j in filtered[:5]:
                info(f"  -> {j['title']} @ {j['company']} | Salary: {j['salary']} | Tags: {j['tags']}")
            if len(filtered) > 5:
                info(f"  ... and {len(filtered) - 5} more")

        return {
            "source": "remoteok",
            "status": "ok",
            "http_status": resp.status_code,
            "raw_jobs": len(job_items),
            "filtered_jobs": len(filtered),
            "sample": filtered[:5],
            "response_time_s": round(elapsed, 2)
        }

    except httpx.TimeoutException:
        fail("TIMEOUT after 20s")
        return {"source": "remoteok", "status": "timeout", "raw_jobs": 0, "filtered_jobs": 0}
    except Exception as e:
        fail(f"ERROR — {e}")
        return {"source": "remoteok", "status": f"error: {e}", "raw_jobs": 0, "filtered_jobs": 0}


# ═════════════════════════════════════════════════════════════════════════════
# WORKDAY
# ═════════════════════════════════════════════════════════════════════════════
WORKDAY_TEST_TARGETS = [
    {"company": "cisco",   "domain": "cisco.wd3.myworkdayjobs.com",      "board": "Cisco_Jobs",               "display": "Cisco"},
    {"company": "nvidia",  "domain": "nvidia.wd5.myworkdayjobs.com",      "board": "NVIDIAExternalCareerSite", "display": "NVIDIA"},
    {"company": "wipro",   "domain": "wipro.wd3.myworkdayjobs.com",       "board": "Wipro_Careers",            "display": "Wipro"},
    {"company": "adobe",   "domain": "adobe.wd5.myworkdayjobs.com",       "board": "external_experienced",     "display": "Adobe"},
    {"company": "intuit",  "domain": "intuit.wd1.myworkdayjobs.com",      "board": "jobs",                     "display": "Intuit"},
]

async def test_workday(client: httpx.AsyncClient) -> Dict[str, Any]:
    print(f"\n{BOLD}{CYAN}━━━ WORKDAY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
    print(f"  Endpoint: https://{{domain}}/wday/cxs/{{company}}/{{board}}/jobs  [POST]")
    print(f"  Testing {len(WORKDAY_TEST_TARGETS)} targets\n")

    wd_headers = {
        "Content-Type": "application/json",
        "User-Agent": UA
    }

    india_kw  = ["india", "bengaluru", "bangalore", "hyderabad", "pune", "mumbai",
                 "delhi", "gurugram", "remote"]
    tech_kw   = ["engineer", "developer", "software", "data", "analyst", "intern",
                 "technology", "devops", "cloud", "sde"]
    senior_kw = ["senior", "sr.", "lead", "staff", "principal", "director",
                 "manager", "architect", "vp", "head of"]

    results = {}
    total_raw = 0
    total_filtered = 0

    for target in WORKDAY_TEST_TARGETS:
        domain, company, board, display = (
            target["domain"], target["company"], target["board"], target["display"]
        )
        url = f"https://{domain}/wday/cxs/{company}/{board}/jobs"
        payload = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "software engineer"}

        t0 = time.monotonic()
        try:
            resp = await client.post(url, json=payload, headers=wd_headers, timeout=15.0)
            elapsed = time.monotonic() - t0

            if resp.status_code not in (200,):
                fail(f"[{display}] HTTP {resp.status_code} ({elapsed:.2f}s) — endpoint may need authentication or changed")
                results[display] = {"status": f"http_{resp.status_code}", "raw_jobs": 0}
                continue

            data = resp.json()
            items = data.get("jobPostings", [])
            total_raw += len(items)

            filtered = []
            for item in items:
                title = item.get("title", "")
                loc   = item.get("locationsText", "")
                t_low = title.lower()
                l_low = loc.lower()
                is_tech   = any(kw in t_low for kw in tech_kw)
                is_senior = any(kw in t_low for kw in senior_kw)
                is_india  = any(kw in l_low for kw in india_kw)
                if is_tech and not is_senior and is_india:
                    filtered.append({"title": title, "location": loc})

            total_filtered += len(filtered)
            ok(f"[{display}] HTTP {resp.status_code} | {len(items)} raw | "
               f"{len(filtered)} India tech jobs | {elapsed:.2f}s")

            for j in filtered[:3]:
                info(f"      -> {j['title']} | {j['location']}")

            results[display] = {
                "status": "ok",
                "http_status": resp.status_code,
                "raw_jobs": len(items),
                "filtered_jobs": len(filtered),
                "sample": filtered[:3],
                "response_time_s": round(elapsed, 2)
            }

        except httpx.TimeoutException:
            fail(f"[{display}] TIMEOUT after 15s")
            results[display] = {"status": "timeout", "raw_jobs": 0}
        except Exception as e:
            fail(f"[{display}] ERROR — {e}")
            results[display] = {"status": f"error: {e}", "raw_jobs": 0}

    print(f"\n  {BOLD}Workday summary: {total_raw} raw listings, "
          f"{total_filtered} matched India tech{RESET}")
    return {"source": "workday", "targets_tested": len(WORKDAY_TEST_TARGETS),
            "total_raw": total_raw, "total_filtered": total_filtered, "details": results}


# ═════════════════════════════════════════════════════════════════════════════
# LEVER
# ═════════════════════════════════════════════════════════════════════════════
LEVER_TEST_COMPANIES = [
    "razorpay",
    "swiggy",
    "cred",
    "postman",
    "linear",
    "browserstack",
]

async def test_lever(client: httpx.AsyncClient) -> Dict[str, Any]:
    print(f"\n{BOLD}{CYAN}━━━ LEVER ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
    print(f"  Endpoint: https://api.lever.co/v0/postings/{{company}}?mode=json")
    print(f"  Testing {len(LEVER_TEST_COMPANIES)} companies: {', '.join(LEVER_TEST_COMPANIES)}\n")

    tech_kw   = ["engineer", "developer", "software", "sde", "backend", "frontend",
                 "fullstack", "data", "devops", "cloud", "mobile", "intern", "junior"]
    senior_kw = ["senior", "sr.", "lead ", "staff ", "principal", "director",
                 "head of", "vp ", "architect", "manager", "cto"]
    india_kw  = ["india", "bengaluru", "bangalore", "hyderabad", "pune", "mumbai",
                 "delhi", "gurugram", "remote", "anywhere", "worldwide", "wfh"]

    results = {}
    total_raw = 0
    total_filtered = 0

    for company in LEVER_TEST_COMPANIES:
        url = f"https://api.lever.co/v0/postings/{company}?mode=json"
        t0 = time.monotonic()
        try:
            resp = await client.get(url, headers=HEADERS, timeout=15.0)
            elapsed = time.monotonic() - t0

            if resp.status_code == 404:
                warn(f"[{company}] Not found (404) — company may not use Lever")
                results[company] = {"status": "not_found", "raw_jobs": 0}
                continue

            if resp.status_code != 200:
                fail(f"[{company}] HTTP {resp.status_code} ({elapsed:.2f}s)")
                results[company] = {"status": f"http_{resp.status_code}", "raw_jobs": 0}
                continue

            jobs = resp.json()
            if not isinstance(jobs, list):
                warn(f"[{company}] Unexpected response format: {type(jobs)}")
                results[company] = {"status": "unexpected_format", "raw_jobs": 0}
                continue

            total_raw += len(jobs)

            filtered = []
            for j in jobs:
                title = j.get("text", "")
                cats  = j.get("categories", {})
                loc   = cats.get("location", "")
                t_low = title.lower()
                l_low = loc.lower()

                is_tech   = any(kw in t_low for kw in tech_kw)
                is_senior = any(kw in t_low for kw in senior_kw)
                is_india  = any(kw in l_low for kw in india_kw)

                if is_tech and not is_senior and is_india:
                    filtered.append({"title": title, "location": loc,
                                     "url": j.get("hostedUrl", "")})

            total_filtered += len(filtered)
            ok(f"[{company}] HTTP {resp.status_code} | {len(jobs)} raw | "
               f"{len(filtered)} India/remote tech | {elapsed:.2f}s")

            for j in filtered[:3]:
                info(f"      -> {j['title']} | {j['location']}")

            results[company] = {
                "status": "ok",
                "http_status": resp.status_code,
                "raw_jobs": len(jobs),
                "filtered_jobs": len(filtered),
                "sample": filtered[:3],
                "response_time_s": round(elapsed, 2)
            }

        except httpx.TimeoutException:
            fail(f"[{company}] TIMEOUT after 15s")
            results[company] = {"status": "timeout", "raw_jobs": 0}
        except Exception as e:
            fail(f"[{company}] ERROR — {e}")
            results[company] = {"status": f"error: {e}", "raw_jobs": 0}

    print(f"\n  {BOLD}Lever summary: {total_raw} raw jobs, "
          f"{total_filtered} matched India/remote tech{RESET}")
    return {"source": "lever", "companies_tested": len(LEVER_TEST_COMPANIES),
            "total_raw": total_raw, "total_filtered": total_filtered, "details": results}


# ═════════════════════════════════════════════════════════════════════════════
# ADAPTER INTEGRATION TEST (imports the actual adapter classes)
# ═════════════════════════════════════════════════════════════════════════════
async def test_adapter_integration(source: str) -> None:
    """
    Run the actual adapter class and show the first 3 JobPosting objects,
    confirming fields are correctly populated.
    """
    print(f"\n{BOLD}{CYAN}━━━ ADAPTER INTEGRATION: {source.upper()} ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
    try:
        if source == "greenhouse":
            from app.ingestion.greenhouse import GreenhouseAdapter
            adapter = GreenhouseAdapter(config={"boards": ["github", "gitlab", "canonical"]})
        elif source == "remoteok":
            from app.ingestion.remoteok import RemoteOKAdapter
            adapter = RemoteOKAdapter()
        elif source == "workday":
            from app.ingestion.workday import WorkdayAdapter
            adapter = WorkdayAdapter(config={"targets": WORKDAY_TEST_TARGETS[:2]})
        elif source == "lever":
            from app.ingestion.lever import LeverAdapter
            adapter = LeverAdapter(config={"companies": LEVER_TEST_COMPANIES[:3]})
        else:
            warn(f"Unknown source: {source}")
            return

        print(f"  Running adapter.fetch_new_postings() ...")
        t0 = time.monotonic()
        postings = await adapter.fetch_new_postings()
        elapsed = time.monotonic() - t0

        if postings:
            ok(f"Adapter returned {len(postings)} JobPosting objects in {elapsed:.1f}s")
            print(f"\n  {BOLD}Sample postings (first 3):{RESET}")
            for i, p in enumerate(postings[:3], 1):
                title_disp = p.title if hasattr(p, "title") else str(p)
                print(f"\n  [{i}] {BOLD}{title_disp}{RESET}")
                if hasattr(p, "company"):   print(f"      Company  : {p.company}")
                if hasattr(p, "location"):  print(f"      Location : {p.location}")
                if hasattr(p, "is_remote"): print(f"      Remote   : {p.is_remote}")
                if hasattr(p, "url"):
                    url_disp = p.url[:80] + "..." if len(p.url) > 80 else p.url
                    print(f"      URL      : {url_disp}")
                if hasattr(p, "posted_date"):   print(f"      Posted   : {p.posted_date}")
                if hasattr(p, "source_name"):   print(f"      Source   : {p.source_name}")
                if hasattr(p, "external_id"):   print(f"      ID       : {p.external_id[:50]}")
        else:
            warn(f"Adapter returned 0 postings after {elapsed:.1f}s "
                 f"(all jobs were filtered out, or board is empty)")

    except ImportError as e:
        warn(f"Cannot import adapter — are you running from the backend/ directory? ({e})")
    except Exception as e:
        fail(f"Adapter integration error: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# MAIN RUNNER
# ═════════════════════════════════════════════════════════════════════════════
SOURCE_TESTS = {
    "greenhouse": test_greenhouse,
    "remoteok":   test_remoteok,
    "workday":    test_workday,
    "lever":      test_lever,
}

async def main(sources_to_test: List[str]) -> None:
    print(f"\n{BOLD}{'='*70}")
    print(f"  AI JOB FINDER — API CONNECTIVITY & EXTRACTION TEST")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}{RESET}\n")

    # Enable ANSI colours on Windows
    import os
    if os.name == "nt":
        os.system("color")

    all_results = []

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for source in sources_to_test:
            fn = SOURCE_TESTS.get(source)
            if fn:
                result = await fn(client)
                all_results.append(result)
            else:
                warn(f"Unknown source '{source}' — skipping")

    # ── Adapter integration tests ─────────────────────────────────────────
    if "--no-adapter" not in sys.argv:
        for source in sources_to_test:
            await test_adapter_integration(source)

    # ── Summary table ─────────────────────────────────────────────────────
    print(f"\n{BOLD}{'='*70}")
    print(f"  FINAL SUMMARY")
    print(f"{'='*70}{RESET}")
    print(f"\n  {'Source':<14} {'Raw Jobs':>10} {'Filtered':>10} {'Working?':>10}")
    print(f"  {'-'*14} {'-'*10} {'-'*10} {'-'*10}")

    for r in all_results:
        raw      = r.get("total_raw", 0)
        filtered = r.get("total_filtered", 0)
        working  = f"{GREEN}YES{RESET}" if raw > 0 else f"{RED}NO{RESET}"
        print(f"  {r['source']:<14} {raw:>10} {filtered:>10}     {working}")

    print()

    # Save JSON report
    report_path = "api_test_report.json"
    with open(report_path, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "sources_tested": sources_to_test,
            "results": all_results
        }, f, indent=2, default=str)
    print(f"  {CYAN}Full report saved to: {report_path}{RESET}\n")


if __name__ == "__main__":
    # Determine which sources to test from CLI args
    valid_sources = list(SOURCE_TESTS.keys())
    requested = [a.lower() for a in sys.argv[1:] if not a.startswith("--")]

    if not requested:
        sources = valid_sources  # test all
    else:
        sources = [s for s in requested if s in valid_sources]
        unknown = [s for s in requested if s not in valid_sources]
        if unknown:
            print(f"{YELLOW}Unknown sources ignored: {unknown}{RESET}")
            print(f"Valid sources: {valid_sources}")
        if not sources:
            sys.exit(1)

    asyncio.run(main(sources))
