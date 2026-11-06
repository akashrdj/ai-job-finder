"""
Workday Dynamic Discovery & Target Validation Engine
=====================================================
Autonomously expands and validates Workday career boards across enterprise MNCs:
1. Harvests apply URLs from incoming aggregator feeds (Adzuna, JSearch, Indeed, JobSpy).
2. Harvests from Common Crawl CDX index API for *.myworkdayjobs.com.
3. Validates candidates via Workday CXS POST API (.../wday/cxs/{tenant}/{board}/jobs).
4. Prunes stale/422/401/404 boards and stores working (tenant, domain, board) triples.
5. Filters for India/Remote posting availability to keep rate limits and bandwidth optimal.
"""

import asyncio
import json
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Any, Iterable
import httpx

logger = logging.getLogger(__name__)

WORKDAY_URL_PATTERN = re.compile(
    r'https?://(?P<tenant>[a-zA-Z0-9_\-]+)\.(?P<dc>wd\d+)\.myworkdayjobs\.com(?:/[a-zA-Z]{2}-[a-zA-Z]{2})?/(?P<site>[a-zA-Z0-9_\-]+)',
    re.IGNORECASE
)

VERIFIED_TARGETS_FILE = Path(__file__).parent / "workday_verified_targets.json"

INDIA_KEYWORDS = [
    "india", "bengaluru", "bangalore", "hyderabad", "pune", "mumbai",
    "delhi", "gurugram", "gurgaon", "noida", "chennai", "kolkata"
]


def extract_workday_triple(url: str) -> Optional[Dict[str, str]]:
    """
    Parse a raw apply or job URL to extract the Workday (tenant, domain, board) triple.
    Example:
        https://accenture.wd103.myworkdayjobs.com/en-US/AccentureCareers/job/...
        -> {"company": "accenture", "domain": "accenture.wd103.myworkdayjobs.com", "board": "AccentureCareers", "display": "Accenture"}
    """
    if not url or "myworkdayjobs.com" not in url:
        return None

    match = WORKDAY_URL_PATTERN.search(url)
    if not match:
        return None

    tenant = match.group("tenant").lower()
    dc = match.group("dc").lower()
    site = match.group("site")

    # Filter out common UI paths that are not board names
    if site.lower() in ("login", "userhome", "job", "jobs", "apply", "search"):
        # Some boards are literally named "jobs" (e.g. PayPal), so only reject login/userhome
        if site.lower() in ("login", "userhome"):
            return None

    domain = f"{tenant}.{dc}.myworkdayjobs.com"
    return {
        "company": tenant,
        "domain": domain,
        "board": site,
        "display": tenant.replace("-", " ").replace("_", " ").title()
    }


class WorkdayDiscoveryService:
    """Discovers, validates, and maintains the verified Workday target registry."""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or VERIFIED_TARGETS_FILE
        self.client_headers = {
            "Content-Type": "application/json",
            "User-Agent": "AIJobFinder-Harvester/1.0 (+https://github.com/akashrdj/ai-job-finder)"
        }

    # ── Source 1: Harvest from SQLite DB ─────────────────────────────────────
    def harvest_from_sqlite(self, db_path: str) -> List[Dict[str, str]]:
        """Harvest Workday apply links collected by other aggregators in SQLite DB."""
        if not os.path.exists(db_path):
            return []

        harvested: Dict[str, Dict[str, str]] = {}
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute("SELECT url FROM jobs WHERE url LIKE '%myworkdayjobs.com%'")
            for (raw_url,) in c.fetchall():
                triple = extract_workday_triple(raw_url or "")
                if triple:
                    key = f"{triple['domain']}|{triple['board']}".lower()
                    harvested[key] = triple
            conn.close()
        except Exception as e:
            logger.warning(f"Error harvesting Workday links from SQLite: {e}")

        logger.info(f"Harvested {len(harvested)} unique Workday boards from local DB.")
        return list(harvested.values())

    # ── Source 2: Harvest from Common Crawl CDX API ──────────────────────────
    async def harvest_from_common_crawl(
        self, client: httpx.AsyncClient, limit: int = 300, timeout: float = 20.0
    ) -> List[Dict[str, str]]:
        """
        Query Common Crawl's CDX index for *.myworkdayjobs.com to surface boards.
        Free, community-accessible public web archive.
        """
        harvested: Dict[str, Dict[str, str]] = {}
        # Try latest indexes or fallback
        indexes = [
            "CC-MAIN-2024-51-index",
            "CC-MAIN-2024-46-index",
            "CC-MAIN-2024-38-index",
        ]

        for idx in indexes:
            cdx_url = (
                f"https://index.commoncrawl.org/{idx}"
                f"?url=myworkdayjobs.com&matchType=domain&output=json&fl=url&limit={limit}"
            )
            try:
                resp = await client.get(cdx_url, timeout=timeout)
                if resp.status_code == 200:
                    for line in resp.text.strip().split("\n"):
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                            u = record.get("url", "")
                            triple = extract_workday_triple(u)
                            if triple:
                                key = f"{triple['domain']}|{triple['board']}".lower()
                                harvested[key] = triple
                        except Exception:
                            continue
                    if harvested:
                        logger.info(f"Common Crawl ({idx}) yielded {len(harvested)} Workday boards.")
                        break
            except Exception as e:
                logger.debug(f"Common Crawl index '{idx}' attempt note: {e}")
                continue

        return list(harvested.values())

    # ── Source 3: Register URLs dynamically during live ingestion ───────────
    def register_urls(self, urls: Iterable[str]) -> List[Dict[str, str]]:
        """Extract and return any Workday triples found in an incoming batch of URLs."""
        found: Dict[str, Dict[str, str]] = {}
        for u in urls:
            triple = extract_workday_triple(u or "")
            if triple:
                key = f"{triple['domain']}|{triple['board']}".lower()
                found[key] = triple
        return list(found.values())

    # ── Target Validation & Health Checking ──────────────────────────────────
    async def validate_candidate(
        self, client: httpx.AsyncClient, target: Dict[str, str], timeout: float = 12.0
    ) -> Optional[Dict[str, Any]]:
        """
        Validate candidate board by sending POST /wday/cxs/{company}/{board}/jobs.
        Checks:
        1. HTTP 200 response
        2. Valid 'total' count returned
        3. Probes for India jobs availability
        """
        domain = target["domain"]
        company = target["company"]
        board = target["board"]
        display = target.get("display", company.title())
        url = f"https://{domain}/wday/cxs/{company}/{board}/jobs"

        # Probe 1: Total open roles on board
        payload_general = {"appliedFacets": {}, "limit": 5, "offset": 0, "searchText": ""}
        try:
            resp = await client.post(url, json=payload_general, headers=self.client_headers, timeout=timeout)
            if resp.status_code != 200:
                logger.debug(f"Candidate {company} ({board}) failed: HTTP {resp.status_code}")
                return None

            data = resp.json()
            total_jobs = data.get("total", 0)
            if not isinstance(total_jobs, int) or total_jobs == 0:
                # Board exists but has 0 jobs
                return None

            # Probe 2: Check for India presence
            payload_india = {"appliedFacets": {}, "limit": 10, "offset": 0, "searchText": "India"}
            india_jobs = 0
            has_india_jobs = False

            try:
                resp_in = await client.post(url, json=payload_india, headers=self.client_headers, timeout=timeout)
                if resp_in.status_code == 200:
                    data_in = resp_in.json()
                    in_postings = data_in.get("jobPostings", [])
                    for p in in_postings:
                        loc = p.get("locationsText") or " ".join([str(b) for b in p.get("bulletFields", [])] + [p.get("externalPath", "")])
                        if any(kw in loc.lower() for kw in INDIA_KEYWORDS):
                            india_jobs += 1
                    if india_jobs > 0:
                        has_india_jobs = True
            except Exception:
                pass

            return {
                "company": company,
                "domain": domain,
                "board": board,
                "display": display,
                "total_jobs": total_jobs,
                "india_jobs_sample": india_jobs,
                "has_india_presence": has_india_jobs,
                "status": "active",
                "last_verified": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.debug(f"Candidate {company} error during probe: {e}")
            return None

    async def validate_batch(
        self, candidates: List[Dict[str, str]], concurrency: int = 6
    ) -> List[Dict[str, Any]]:
        """Validate candidate list concurrently with controlled concurrency."""
        sem = asyncio.Semaphore(concurrency)
        verified: List[Dict[str, Any]] = []

        async with httpx.AsyncClient() as client:
            async def _worker(cand: Dict[str, str]):
                async with sem:
                    res = await self.validate_candidate(client, cand)
                    if res:
                        verified.append(res)
                        logger.info(f"✅ Verified Workday Board: {res['display']} ({res['total_jobs']} jobs, India: {res['has_india_presence']})")

            tasks = [_worker(c) for c in candidates]
            await asyncio.gather(*tasks)

        return verified

    # ── Persistence & Loading ────────────────────────────────────────────────
    def save_verified_targets(self, targets: List[Dict[str, Any]]):
        """Save verified targets to JSON storage."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(targets, f, indent=2)
        logger.info(f"Saved {len(targets)} verified Workday targets to {self.storage_path}")

    def load_verified_targets(self) -> List[Dict[str, Any]]:
        """Load verified targets from JSON storage."""
        if not self.storage_path.exists():
            return []
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error loading verified targets: {e}")
            return []


# ── Standalone CLI Runner ────────────────────────────────────────────────────
async def main():
    service = WorkdayDiscoveryService()
    db_file = Path(__file__).parents[2] / "job_finder.db"

    print("=" * 72)
    print("  WORKDAY DYNAMIC DISCOVERY & VALIDATION ENGINE")
    print("=" * 72)

    # 1. Harvest from DB
    db_candidates = service.harvest_from_sqlite(str(db_file))
    print(f"📦 Harvested from DB: {len(db_candidates)} candidates")

    # 2. Add baseline targets from workday.py
    from app.ingestion.workday import DEFAULT_WORKDAY_TARGETS
    all_candidates: Dict[str, Dict[str, str]] = {}
    for t in DEFAULT_WORKDAY_TARGETS:
        key = f"{t['domain']}|{t['board']}".lower()
        all_candidates[key] = t

    for t in db_candidates:
        key = f"{t['domain']}|{t['board']}".lower()
        if key not in all_candidates:
            all_candidates[key] = t

    print(f"🔍 Total candidates queued for validation: {len(all_candidates)}")
    print("⏳ Validating targets via CXS POST API...")

    verified = await service.validate_batch(list(all_candidates.values()))
    service.save_verified_targets(verified)

    india_verified = [v for v in verified if v.get("has_india_presence")]

    print("\n" + "=" * 72)
    print(f"  VALIDATION SUMMARY")
    print("=" * 72)
    print(f"  Total Candidates Checked : {len(all_candidates)}")
    print(f"  ✅ Confirmed Active      : {len(verified)}")
    print(f"  🇮🇳 With India Presence  : {len(india_verified)}")
    print(f"  📁 Saved Registry        : {service.storage_path}")
    print("=" * 72)


if __name__ == "__main__":
    asyncio.run(main())

