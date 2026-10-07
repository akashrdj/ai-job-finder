import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from app.ingestion.base import SourceAdapter, JobPosting
from app.ingestion.constants import (
    is_india_or_remote, is_tech_role, is_senior_title, is_remote
)

logger = logging.getLogger(__name__)

# Ashby ATS boards active in India fintech and high-growth tech
DEFAULT_ASHBY_COMPANIES = [
    "cred",
    "groww",
    "fampay",
    "slice",
    "navi",
    "postman",
    "browserstack",
    "juspay",
]


class CompanyPortalTrackerAdapter(SourceAdapter):
    """
    Direct zero-cost JSON API tracker for companies not easily scraped or using non-Workday ATS.
    Targets:
    1. Apple Careers (Official public JSON search API)
    2. Ashby ATS (Public JSON API for top Indian fintechs & unicorns)
    Zero browser overhead, 0 Apify cost, polite rate limiting.
    """

    def __init__(self, name: str = "portal_tracker", config: Optional[Dict[str, Any]] = None):
        super().__init__(name, config)
        self.ashby_companies = self.config.get("ashby_companies", DEFAULT_ASHBY_COMPANIES)
        self.headers = {
            "User-Agent": "AIJobFinder-ReviewBot/1.0 (+https://github.com/akashrdj/ai-job-finder; fresher review bot)",
            "Accept": "application/json",
        }

    async def _fetch_apple_jobs(self, client: httpx.AsyncClient) -> List[JobPosting]:
        """Fetch tech and fresher roles from Apple's public career search API."""
        url = "https://jobs.apple.com/api/v1/job/search"
        postings: List[JobPosting] = []
        payload = {
            "query": "Engineer",
            "filters": {
                "postingpostLocation": ["postLocation-IN"]
            },
            "page": 1,
            "locale": "en-in",
            "sort": "relevance"
        }

        try:
            resp = await client.post(url, json=payload, headers=self.headers, timeout=12.0)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("searchResults", [])
                for item in results:
                    title = item.get("postingTitle", "").strip()
                    if not is_tech_role(title):
                        continue

                    job_id = item.get("id", "")
                    location = item.get("locations", [{}])[0].get("name", "India")
                    desc = item.get("jobSummary", "") or f"Apple {title} in {location}"
                    apply_url = f"https://jobs.apple.com/en-in/details/{job_id}"

                    postings.append(JobPosting(
                        source_name="apple_careers",
                        external_id=f"apple_{job_id}",
                        title=title,
                        company="Apple",
                        location=location,
                        is_remote=is_remote(location, title, desc),
                        description=desc,
                        url=apply_url,
                        posted_date=datetime.utcnow(),
                        raw_metadata={"company": "Apple", "source": "apple_careers_api"}
                    ))
        except Exception as e:
            logger.debug(f"Apple careers API note: {e}")

        return postings

    async def _fetch_ashby_board(self, client: httpx.AsyncClient, company: str) -> List[JobPosting]:
        """Fetch tech jobs from an Ashby ATS public job board."""
        url = f"https://api.ashbyhq.com/posting-api/job-board/{company}"
        postings: List[JobPosting] = []

        try:
            resp = await client.get(url, headers=self.headers, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                job_list = data.get("jobs", [])
                for item in job_list:
                    title = item.get("title", "")
                    if not is_tech_role(title):
                        continue

                    location = item.get("location", "") or "India"
                    if not is_india_or_remote(location, title):
                        continue

                    desc_html = item.get("descriptionHtml", "")
                    desc_plain = item.get("descriptionPlain", "")
                    desc = desc_plain or (
                        BeautifulSoup(desc_html, "html.parser").get_text(separator="\n", strip=True)
                        if desc_html else f"{title} at {company}"
                    )

                    job_id = item.get("id", "")
                    apply_url = item.get("jobUrl", f"https://jobs.ashbyhq.com/{company}/{job_id}")

                    postings.append(JobPosting(
                        source_name=f"ashby_{company}",
                        external_id=f"ashby_{company}_{job_id}",
                        title=title,
                        company=company.title(),
                        location=location,
                        is_remote=item.get("isRemote", False) or is_remote(location, title),
                        description=desc,
                        url=apply_url,
                        posted_date=datetime.utcnow(),
                        raw_metadata={"company": company, "ats": "ashby"}
                    ))
        except Exception as e:
            logger.debug(f"Ashby board note for '{company}': {e}")

        return postings

    async def fetch_new_postings(self, since: Optional[datetime] = None) -> List[JobPosting]:
        all_postings: List[JobPosting] = []
        async with httpx.AsyncClient(follow_redirects=True) as client:
            # 1. Apple Careers
            apple_jobs = await self._fetch_apple_jobs(client)
            all_postings.extend(apple_jobs)

            # 2. Ashby Fintech & Startup Boards
            for comp in self.ashby_companies:
                ashby_jobs = await self._fetch_ashby_board(client, comp)
                all_postings.extend(ashby_jobs)

        logger.info(f"PortalTracker: Ingested {len(all_postings)} direct tech jobs (Apple + Ashby Fintechs).")
        return all_postings
