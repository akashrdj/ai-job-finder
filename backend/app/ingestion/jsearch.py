import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import httpx
from app.ingestion.base import SourceAdapter, JobPosting
from app.ingestion.constants import (
    FRESHER_SEARCH_QUERIES, is_india_or_remote, is_remote,
    is_tech_role, is_senior_title,
)
from app.config import settings

logger = logging.getLogger(__name__)

# JSearch API via RapidAPI — aggregates Google for Jobs
# Covers: LinkedIn, Indeed, Glassdoor, Naukri, company career pages, and more
# Free tier: 500 requests/month
JSEARCH_BASE_URL = "https://jsearch.p.rapidapi.com/search"


class JSearchAdapter(SourceAdapter):
    """
    JSearch (Google for Jobs aggregator) adapter via RapidAPI.
    This is the primary broad-coverage source — it pulls from LinkedIn,
    Indeed, Glassdoor, Naukri, and direct company career pages.
    Searches for fresher-specific role titles in India.
    """

    def __init__(self, name: str = "jsearch", config: Optional[Dict[str, Any]] = None):
        super().__init__(name, config)
        self.api_key = self.config.get("api_key") or settings.JSEARCH_API_KEY
        self.max_queries = self.config.get("max_queries", 10)  # Limit queries per run to conserve free tier
        self.search_queries = self.config.get(
            "search_queries",
            FRESHER_SEARCH_QUERIES[:self.max_queries]
        )

    async def _search_jobs(
        self, client: httpx.AsyncClient, query: str, page: int = 1
    ) -> List[Dict[str, Any]]:
        """Execute a single JSearch API query."""
        headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": "jsearch.p.rapidapi.com",
        }
        params = {
            "query": f"{query} in India",
            "page": str(page),
            "num_pages": "1",
            "date_posted": "week",       # Only jobs from last 7 days
            "country": "in",             # India
            "language": "en",
        }

        try:
            resp = await client.get(
                JSEARCH_BASE_URL, headers=headers, params=params, timeout=20.0
            )
            if resp.status_code == 429:
                logger.warning("JSearch API rate limit reached. Skipping remaining queries.")
                return []
            if resp.status_code == 403:
                logger.error("JSearch API key invalid or expired. Check JSEARCH_API_KEY.")
                return []
            if resp.status_code != 200:
                logger.warning(f"JSearch API returned {resp.status_code} for query '{query}'")
                return []

            data = resp.json()
            return data.get("data", [])

        except Exception as e:
            logger.warning(f"JSearch API error for query '{query}': {e}")
            return []

    def _parse_job(self, item: Dict[str, Any]) -> Optional[JobPosting]:
        """Parse a single JSearch API result into a JobPosting."""
        title = item.get("job_title", "").strip()
        company = item.get("employer_name", "Unknown Company")
        city = item.get("job_city", "")
        state = item.get("job_state", "")
        country = item.get("job_country", "")

        # Build location string
        location_parts = [p for p in [city, state, country] if p]
        location = ", ".join(location_parts) or "India"

        # Description
        description = item.get("job_description", "")

        # Check if tech role (broad match)
        if not is_tech_role(title):
            return None

        # Apply URL
        apply_url = (
            item.get("job_apply_link")
            or item.get("job_google_link")
            or ""
        )

        # Job ID
        job_id = item.get("job_id", "")
        external_id = f"jsearch_{job_id}" if job_id else f"jsearch_{hash(title + company) & 0xffffffff:x}"

        # Remote detection
        is_wfh = item.get("job_is_remote", False) or is_remote(location, title, description)

        # Posted date
        posted_date = None
        posted_str = item.get("job_posted_at_datetime_utc")
        if posted_str:
            try:
                posted_date = datetime.fromisoformat(
                    posted_str.replace("Z", "+00:00")
                ).replace(tzinfo=None)
            except Exception:
                pass

        # Salary
        salary_min = item.get("job_min_salary")
        salary_max = item.get("job_max_salary")
        salary_currency = item.get("job_salary_currency", "INR")

        # Seniority flag (for scoring, not filtering)
        is_senior = is_senior_title(title)

        return JobPosting(
            source_name=self.name,
            external_id=external_id,
            title=title,
            company=company,
            location=location,
            is_remote=is_wfh,
            description=description,
            url=apply_url,
            salary_min=float(salary_min) if salary_min else None,
            salary_max=float(salary_max) if salary_max else None,
            salary_currency=salary_currency,
            posted_date=posted_date or datetime.utcnow(),
            raw_metadata={
                "source_api": "jsearch",
                "job_id": job_id,
                "employer_website": item.get("employer_website", ""),
                "employment_type": item.get("job_employment_type", ""),
                "is_senior": is_senior,
                "work_type": "wfh" if is_wfh else "onsite",
                "job_publisher": item.get("job_publisher", ""),
            }
        )

    async def fetch_new_postings(self, since: Optional[datetime] = None) -> List[JobPosting]:
        if not self.api_key:
            logger.warning(
                "JSearch API key not configured (JSEARCH_API_KEY). "
                "Get a free key at https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch"
            )
            return []

        all_postings: List[JobPosting] = []
        seen_ids: set = set()

        async with httpx.AsyncClient() as client:
            for query in self.search_queries:
                items = await self._search_jobs(client, query)
                if not items:
                    continue

                for item in items:
                    posting = self._parse_job(item)
                    if posting and posting.external_id not in seen_ids:
                        seen_ids.add(posting.external_id)
                        all_postings.append(posting)

                logger.info(f"JSearch '{query}': {len(items)} results, {len(all_postings)} total unique")

        logger.info(f"JSearch total: {len(all_postings)} tech jobs from Google for Jobs aggregator")
        return all_postings
