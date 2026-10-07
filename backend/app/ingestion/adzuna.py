import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import httpx
from app.ingestion.base import SourceAdapter, JobPosting
from app.ingestion.constants import (
    FRESHER_SEARCH_QUERIES, is_tech_role, is_remote, is_senior_title,
)
from app.config import settings

logger = logging.getLogger(__name__)

# Adzuna API — global job search engine with India coverage
# Free tier: 1000 calls/month
# Docs: https://developer.adzuna.com/
ADZUNA_BASE_URL = "https://api.adzuna.com/v1/api/jobs"
ADZUNA_COUNTRY = "in"  # India


class AdzunaAdapter(SourceAdapter):
    """
    Adzuna Job Search API adapter — India-focused.
    Secondary aggregator providing additional coverage beyond JSearch.
    Free tier: 1000 API calls/month.
    """

    def __init__(self, name: str = "adzuna", config: Optional[Dict[str, Any]] = None):
        super().__init__(name, config)
        self.app_id = self.config.get("app_id") or settings.ADZUNA_APP_ID
        self.app_key = self.config.get("app_key") or settings.ADZUNA_APP_KEY
        self.max_queries = self.config.get("max_queries", 8)
        self.search_queries = self.config.get(
            "search_queries",
            FRESHER_SEARCH_QUERIES[:self.max_queries]
        )

    async def _search_jobs(
        self, client: httpx.AsyncClient, query: str, page: int = 1
    ) -> List[Dict[str, Any]]:
        """Execute a single Adzuna API search."""
        url = f"{ADZUNA_BASE_URL}/{ADZUNA_COUNTRY}/search/{page}"
        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "what": query,
            "results_per_page": "20",
            "max_days_old": "7",           # Only last 7 days
            "sort_by": "date",             # Most recent first
            "content-type": "application/json",
            "category": "it-jobs",         # IT/Tech category
        }

        try:
            resp = await client.get(url, params=params, timeout=15.0)
            if resp.status_code == 401:
                logger.error("Adzuna API credentials invalid. Check ADZUNA_APP_ID and ADZUNA_APP_KEY.")
                return []
            if resp.status_code == 429:
                logger.warning("Adzuna API rate limit reached.")
                return []
            if resp.status_code != 200:
                logger.warning(f"Adzuna API returned {resp.status_code} for query '{query}'")
                return []

            data = resp.json()
            return data.get("results", [])

        except Exception as e:
            logger.warning(f"Adzuna API error for query '{query}': {e}")
            return []

    def _parse_job(self, item: Dict[str, Any]) -> Optional[JobPosting]:
        """Parse a single Adzuna API result into a JobPosting."""
        title = item.get("title", "").strip()
        company_obj = item.get("company", {})
        company = company_obj.get("display_name", "Unknown Company") if isinstance(company_obj, dict) else str(company_obj)
        
        location_obj = item.get("location", {})
        location_parts = []
        if isinstance(location_obj, dict):
            display_name = location_obj.get("display_name", "")
            area = location_obj.get("area", [])
            if display_name:
                location_parts.append(display_name)
            elif area:
                location_parts = area
        location = ", ".join(location_parts) if location_parts else "India"

        description = item.get("description", "")

        # Tech role check
        if not is_tech_role(title):
            return None

        apply_url = item.get("redirect_url", "")
        adzuna_id = item.get("id", "")
        external_id = f"adzuna_{adzuna_id}" if adzuna_id else f"adzuna_{hash(title + company) & 0xffffffff:x}"

        # Remote detection
        is_wfh = is_remote(location, title, description)

        # Posted date
        posted_date = None
        created_str = item.get("created")
        if created_str:
            try:
                posted_date = datetime.fromisoformat(
                    created_str.replace("Z", "+00:00")
                ).replace(tzinfo=None)
            except Exception:
                pass

        # Salary
        salary_min = item.get("salary_min")
        salary_max = item.get("salary_max")

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
            salary_currency="INR",
            posted_date=posted_date or datetime.utcnow(),
            raw_metadata={
                "source_api": "adzuna",
                "adzuna_id": adzuna_id,
                "category": item.get("category", {}).get("label", ""),
                "contract_type": item.get("contract_type", ""),
                "is_senior": is_senior,
                "work_type": "wfh" if is_wfh else "onsite",
            }
        )

    async def fetch_new_postings(self, since: Optional[datetime] = None) -> List[JobPosting]:
        if not self.app_id or not self.app_key:
            logger.warning(
                "Adzuna API credentials not configured (ADZUNA_APP_ID / ADZUNA_APP_KEY). "
                "Get free keys at https://developer.adzuna.com/"
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

                logger.info(f"Adzuna '{query}': {len(items)} results, {len(all_postings)} total unique")

        logger.info(f"Adzuna total: {len(all_postings)} tech jobs from India")
        return all_postings
