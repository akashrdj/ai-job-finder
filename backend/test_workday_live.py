"""
Workday Live Connectivity Test
================================
Tests the fixed Workday adapter against all configured targets.
For each company that returns jobs, prints up to 7 role listings so you can:
  1. Confirm the adapter is actually hitting the right Workday board
  2. See the kind of titles coming back
  3. Spot any 422 / 401 / board-slug errors immediately

Usage:
    cd backend
    python test_workday_live.py

    # Test only specific companies:
    python test_workday_live.py accenture tcs infosys

    # Test with verbose description preview:
    python test_workday_live.py --desc
"""

import asyncio
import sys
import time
import httpx
from datetime import datetime
from typing import List, Dict, Optional

# ── inline constants so this script runs standalone (no DB needed) ────────────
INDIA_LOCATION_KEYWORDS = [
    "india", "bengaluru", "bangalore", "hyderabad", "pune", "mumbai",
    "delhi", "gurugram", "gurgaon", "noida", "chennai", "kolkata",
    "ahmedabad", "jaipur", "thiruvananthapuram", "kochi",
]
REMOTE_SIGNALS = ["remote", "work from home", "wfh", "anywhere", "worldwide", "hybrid", "virtual"]


def is_india(loc: str) -> bool:
    loc_l = loc.lower()
    return any(k in loc_l for k in INDIA_LOCATION_KEYWORDS)


def is_remote(loc: str, title: str = "") -> bool:
    combined = f"{loc} {title}".lower()
    return any(s in combined for s in REMOTE_SIGNALS)


# ── Workday targets (must match workday.py) ───────────────────────────────────
DEFAULT_WORKDAY_TARGETS = [
    # Enterprise Tech
    {"company": "nvidia",       "domain": "nvidia.wd5.myworkdayjobs.com",        "board": "NVIDIAExternalCareerSite"},
    {"company": "adobe",        "domain": "adobe.wd5.myworkdayjobs.com",         "board": "external_experienced"},
    {"company": "salesforce",   "domain": "salesforce.wd12.myworkdayjobs.com",   "board": "External_Career_Site"},
    {"company": "microsoft",    "domain": "microsoft.wd5.myworkdayjobs.com",     "board": "MSFTExternalCareers"},
    {"company": "oracle",       "domain": "oracle.wd1.myworkdayjobs.com",        "board": "OracleExternalCareers"},
    {"company": "servicenow",   "domain": "servicenow.wd1.myworkdayjobs.com",    "board": "Careers"},
    {"company": "uber",         "domain": "uber.wd5.myworkdayjobs.com",          "board": "uberExternalCareerSite"},
    {"company": "cisco",        "domain": "cisco.wd5.myworkdayjobs.com",         "board": "Cisco-University-Careers"},
    {"company": "intel",        "domain": "intel.wd1.myworkdayjobs.com",         "board": "External"},
    {"company": "mastercard",   "domain": "mastercard.wd1.myworkdayjobs.com",    "board": "CorporateCareers"},
    {"company": "visa",         "domain": "visa.wd5.myworkdayjobs.com",          "board": "SearchJobs"},
    {"company": "paypal",       "domain": "paypal.wd1.myworkdayjobs.com",        "board": "jobs"},
    {"company": "dell",         "domain": "dell.wd1.myworkdayjobs.com",          "board": "External"},
    {"company": "vmware",       "domain": "vmware.wd1.myworkdayjobs.com",        "board": "VMwareCareers"},
    # Indian MNCs (new)
    {"company": "accenture",    "domain": "accenture.wd103.myworkdayjobs.com",   "board": "AccentureCareers"},
    {"company": "tcs",          "domain": "tcs.wd5.myworkdayjobs.com",           "board": "TCS"},
    {"company": "infosys",      "domain": "infosys.wd3.myworkdayjobs.com",       "board": "Infosys"},
    {"company": "cognizant",    "domain": "cognizant.wd5.myworkdayjobs.com",     "board": "CognizantCareers"},
    {"company": "capgemini",    "domain": "capgemini.wd3.myworkdayjobs.com",     "board": "Capgemini"},
    {"company": "hcl",          "domain": "hcltech.wd3.myworkdayjobs.com",       "board": "HCLTechCareers"},
    {"company": "ltimindtree",  "domain": "ltimindtree.wd3.myworkdayjobs.com",   "board": "LTIMindtreeCareers"},
    {"company": "mphasis",      "domain": "mphasis.wd3.myworkdayjobs.com",       "board": "MphasisCareers"},
    {"company": "intuit",       "domain": "intuit.wd5.myworkdayjobs.com",        "board": "Intuit-Careers"},
    # Global Tech
    {"company": "samsung",      "domain": "samsung.wd3.myworkdayjobs.com",       "board": "Global"},
    {"company": "qualcomm",     "domain": "qualcomm.wd5.myworkdayjobs.com",      "board": "External"},
    {"company": "sap",          "domain": "sap.wd3.myworkdayjobs.com",           "board": "SAPCareers"},
    {"company": "siemens",      "domain": "siemens.wd3.myworkdayjobs.com",       "board": "SiemensCareers"},
    {"company": "micron",       "domain": "micron.wd1.myworkdayjobs.com",        "board": "External"},
    {"company": "amdocs",       "domain": "amdocs.wd3.myworkdayjobs.com",        "board": "AmDocsCareers"},
    # FinTech / Banking
    {"company": "jpmc",         "domain": "jpmc.wd5.myworkdayjobs.com",          "board": "JPMC"},
    {"company": "barclays",     "domain": "barclays.wd3.myworkdayjobs.com",      "board": "BarclaysCareers"},
    {"company": "citi",         "domain": "citi.wd5.myworkdayjobs.com",          "board": "CitiCareers"},
    {"company": "aexp",         "domain": "aexp.wd3.myworkdayjobs.com",          "board": "AmexCareers"},
    {"company": "blackrock",    "domain": "blackrock.wd1.myworkdayjobs.com",     "board": "BlackRock_Professional_Careers"},
    {"company": "morganstanley","domain": "morganstanley.wd5.myworkdayjobs.com", "board": "External"},
    {"company": "wellsfargo",   "domain": "wellsfargo.wd1.myworkdayjobs.com",    "board": "WellsFargoJobs"},
    {"company": "fidelity",     "domain": "fidelity.wd1.myworkdayjobs.com",      "board": "FidelityCareers"},
    {"company": "bnymellon",    "domain": "bnymellon.wd5.myworkdayjobs.com",     "board": "BNYMellonCareers"},
    {"company": "deutschebank", "domain": "deutschebank.wd3.myworkdayjobs.com",  "board": "DeutscheBankCareers"},
]

# Use these terms only for the connectivity test (broader than prod to get max hits)
TEST_SEARCH_TERMS = [
    "software engineer", "data", "associate", "analyst",
    "machine learning", "artificial intelligence",
]

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "AIJobFinder-TestBot/1.0",
}

# ANSI colours
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


async def probe_target(
    client: httpx.AsyncClient,
    target: Dict,
    show_desc: bool = False,
    max_display: int = 7,
) -> Dict:
    """
    Hit ONE Workday CXS target with TEST_SEARCH_TERMS.
    Returns a result dict with status, job count, and sample listings.
    """
    company = target["company"]
    domain  = target["domain"]
    board   = target["board"]
    url     = f"https://{domain}/wday/cxs/{company}/{board}/jobs"

    all_jobs: List[Dict] = []
    seen_ids: set = set()
    last_http_status: Optional[int] = None
    error_msg: Optional[str] = None
    t0 = time.time()

    for term in TEST_SEARCH_TERMS:
        payload = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": term}
        try:
            resp = await client.post(url, json=payload, headers=HEADERS, timeout=12.0)
            last_http_status = resp.status_code
            if resp.status_code != 200:
                # Don't stop — try next term in case some terms work
                continue
            data = resp.json()
            for item in data.get("jobPostings", []):
                path  = item.get("externalPath", "")
                title = item.get("title", "Untitled")
                raw_loc = item.get("locationsText")
                if not raw_loc or raw_loc.strip() == "" or raw_loc == "Not Specified":
                    bullets = " ".join([str(b) for b in item.get("bulletFields", [])])
                    loc = f"{bullets} {path}".strip()
                else:
                    loc = raw_loc
                posted = item.get("postedOn", "")

                uid = f"{company}_{path}"
                if uid in seen_ids:
                    continue
                seen_ids.add(uid)

                all_jobs.append({
                    "title": title,
                    "location": loc,
                    "posted": posted,
                    "url": f"https://{domain}/en-US/{board}{path}",
                    "india": is_india(loc),
                    "remote": is_remote(loc, title),
                })
        except httpx.TimeoutException:
            error_msg = "TIMEOUT"
            break
        except Exception as e:
            error_msg = str(e)[:80]
            break

    elapsed = round(time.time() - t0, 2)

    # Separate India/Remote jobs from pure international
    india_remote = [j for j in all_jobs if j["india"] or j["remote"]]
    international = [j for j in all_jobs if not j["india"] and not j["remote"]]

    return {
        "company":     company,
        "domain":      domain,
        "board":       board,
        "url":         url,
        "http_status": last_http_status,
        "error":       error_msg,
        "elapsed_s":   elapsed,
        "total_raw":   len(all_jobs),
        "india_remote": india_remote,
        "international": international,
        "show_desc":   show_desc,
        "max_display": max_display,
    }


def print_result(r: Dict):
    company = r["company"].upper()
    status  = r["http_status"]
    total   = r["total_raw"]
    ir_jobs = r["india_remote"]
    intl    = r["international"]

    # ── header ──────────────────────────────────────────────────────────────
    if r["error"] == "TIMEOUT":
        status_str = f"{RED}⏱  TIMEOUT{RESET}"
    elif status is None:
        status_str = f"{RED}✗ CONNECTION ERROR{RESET}"
    elif status == 200 and total > 0:
        status_str = f"{GREEN}✅ HTTP 200 — {total} raw jobs found{RESET}"
    elif status == 200 and total == 0:
        status_str = f"{YELLOW}⚠️  HTTP 200 but 0 jobs returned (board slug OK, no matching postings){RESET}"
    elif status == 422:
        status_str = f"{RED}✗ HTTP 422 — WRONG BOARD SLUG → {r['board']!r}{RESET}"
    elif status == 401:
        status_str = f"{RED}✗ HTTP 401 — AUTH REQUIRED (board may be gated){RESET}"
    elif status == 404:
        status_str = f"{RED}✗ HTTP 404 — DOMAIN NOT FOUND → {r['domain']!r}{RESET}"
    else:
        status_str = f"{RED}✗ HTTP {status}{RESET}"

    if r["error"] and r["error"] != "TIMEOUT":
        status_str += f"  [{RED}{r['error']}{RESET}]"

    print(f"\n{'─'*72}")
    print(f"  {BOLD}{CYAN}{company}{RESET}  ({r['elapsed_s']}s)")
    print(f"  Endpoint: {r['url']}")
    print(f"  Status:   {status_str}")

    # ── India/Remote listings ────────────────────────────────────────────────
    if ir_jobs:
        print(f"\n  {GREEN}🇮🇳 India / Remote Roles ({len(ir_jobs)} total, showing up to {r['max_display']}){RESET}")
        for idx, job in enumerate(ir_jobs[:r["max_display"]], 1):
            tag = "🇮🇳" if job["india"] else "🌐"
            print(f"    [{idx}] {tag} {job['title']}")
            print(f"        📍 {job['location']}   📅 {job.get('posted','')}")
            print(f"        🔗 {job['url'][:90]}")
    elif total > 0:
        # Jobs exist but all international
        print(f"\n  {YELLOW}⚠️  {total} jobs found but NONE in India/Remote.{RESET}")
        print(f"      Showing first {min(r['max_display'], len(intl))} international listings as proof-of-life:")
        for idx, job in enumerate(intl[:r["max_display"]], 1):
            print(f"    [{idx}] 🌍 {job['title']} — {job['location']}")


def print_summary(results: List[Dict]):
    working     = [r for r in results if r["http_status"] == 200 and r["total_raw"] > 0]
    empty_200   = [r for r in results if r["http_status"] == 200 and r["total_raw"] == 0]
    http_422    = [r for r in results if r["http_status"] == 422]
    http_401    = [r for r in results if r["http_status"] == 401]
    http_404    = [r for r in results if r["http_status"] == 404]
    errors      = [r for r in results if r["http_status"] is None or r["error"] == "TIMEOUT"]
    total_india = sum(len(r["india_remote"]) for r in working)

    print(f"\n{'='*72}")
    print(f"  {BOLD}WORKDAY CONNECTIVITY SUMMARY{RESET}")
    print(f"{'='*72}")
    print(f"  Targets tested     : {len(results)}")
    print(f"  {GREEN}✅ Working (200+jobs) : {len(working)}{RESET}  →  {', '.join(r['company'] for r in working)}")
    print(f"  {YELLOW}⚠️  Empty (200+0 jobs) : {len(empty_200)}{RESET}  →  {', '.join(r['company'] for r in empty_200)}")
    print(f"  {RED}✗ HTTP 422 (bad slug): {len(http_422)}{RESET}  →  {', '.join(r['company'] for r in http_422)}")
    print(f"  {RED}✗ HTTP 401 (gated)   : {len(http_401)}{RESET}  →  {', '.join(r['company'] for r in http_401)}")
    print(f"  {RED}✗ HTTP 404 (no domain): {len(http_404)}{RESET}  →  {', '.join(r['company'] for r in http_404)}")
    print(f"  {RED}✗ Errors/Timeouts    : {len(errors)}{RESET}  →  {', '.join(r['company'] for r in errors)}")
    print(f"\n  {BOLD}India/Remote jobs found this run: {total_india}{RESET}")
    print(f"{'='*72}\n")

    if http_422:
        print(f"  {YELLOW}FIX NEEDED for 422 companies:{RESET}")
        for r in http_422:
            print(f"    {r['company']}: visit https://{r['domain']}/en-US/job and check the board name in the URL")

    if http_401:
        print(f"\n  {YELLOW}NOTE on 401 companies:{RESET}")
        for r in http_401:
            print(f"    {r['company']}: board may require auth or uses a different ATS (not Workday)")


async def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    show_desc = "--desc" in sys.argv

    # Filter targets if company names passed as args
    targets = DEFAULT_WORKDAY_TARGETS
    if args:
        targets = [t for t in DEFAULT_WORKDAY_TARGETS if t["company"] in args]
        if not targets:
            print(f"{RED}No matching companies found for: {args}{RESET}")
            print(f"Available: {[t['company'] for t in DEFAULT_WORKDAY_TARGETS]}")
            sys.exit(1)
        print(f"\n{CYAN}Testing {len(targets)} target(s): {[t['company'] for t in targets]}{RESET}")
    else:
        print(f"\n{CYAN}Testing ALL {len(targets)} Workday targets...{RESET}")
        print(f"  Tip: Pass company names to test a subset, e.g.:  python test_workday_live.py accenture tcs infosys")
        print(f"  Tip: Add --desc to also preview job descriptions\n")

    async with httpx.AsyncClient() as client:
        # Run all probes concurrently — faster than sequential
        tasks = [probe_target(client, t, show_desc) for t in targets]
        results = await asyncio.gather(*tasks)

    for r in results:
        print_result(r)

    print_summary(list(results))


if __name__ == "__main__":
    asyncio.run(main())

