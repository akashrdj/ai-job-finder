"""
JobSpy Multi-Board Scraper Adapter
================================================================================
Uses python-jobspy (open-source) to scrape jobs from LinkedIn, Indeed,
Glassdoor, Google, and Naukri simultaneously.

Cost: $0.00 (100% free, no API keys, no tokens)

Supports:
  • site_name: linkedin, indeed, glassdoor, google, naukri
  • hours_old: filter to jobs posted within last N hours
  • results_wanted: cap on number of results per board
  • Proxy support (optional) for avoiding rate limits

Note: JobSpy uses requests (sync), so we run it in an executor thread
to avoid blocking the async event loop.
================================================================================
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import List, Optional, Dict, Any

from app.ingestion.base import SourceAdapter, JobPosting

logger = logging.getLogger(__name__)

# Thread pool for running sync JobSpy calls without blocking asyncio
_jobspy_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jobspy")

# Default search queries aligned with user's profile
DEFAULT_JOBSPY_QUERIES = [
    "Python Developer",
    "Software Engineer",
    "Full Stack Developer",
    "Backend Developer",
    "AI Engineer",
]

# Sites to scrape — all free, no API key needed
DEFAULT_SITES = ["linkedin", "indeed", "glassdoor", "google"]


def _check_jobspy_available() -> bool:
    """Check if python-jobspy is installed."""
    try:
        from jobspy import scrape_jobs  # noqa: F401
        return True
    except ImportError:
        return False


def _run_jobspy_sync(
    search_term: str,
    location: str,
    sites: List[str],
    results_wanted: int,
    hours_old: int,
    country_indeed: str,
) -> List[Dict[str, Any]]:
    """
    Synchronous wrapper around jobspy.scrape_jobs.
    Returns a list of dicts (from DataFrame rows).
    """
    from jobspy import scrape_jobs

    try:
        df = scrape_jobs(
            site_name=sites,
            search_term=search_term,
            location=location,
            results_wanted=results_wanted,
            hours_old=hours_old,
            country_indeed=country_indeed,
        )

        if df is None or df.empty:
            return []

        # Convert DataFrame to list of dicts, handling NaN values
        records = df.where(df.notnull(), None).to_dict(orient="records")
        return records

    except Exception as e:
        logger.error(f"JobSpy scrape_jobs error for '{search_term}': {e}", exc_info=True)
        return []


class JobSpyAdapter(SourceAdapter):
    """
    Multi-board job scraper using python-jobspy (open-source).
    Scrapes LinkedIn, Indeed, Glassdoor, Google, and Naukri simultaneously.
    100% free — no API keys, no tokens, no paid credits.

    Designed to complement the LinkedIn Guest Scraper by covering Indeed,
    Glassdoor, and Google that the guest scraper cannot reach.
    """

    def __init__(self, name: str = "jobspy", config: Optional[Dict[str, Any]] = None):
        super().__init__(name, config)
        self.queries = self.config.get("queries", DEFAULT_JOBSPY_QUERIES)
        self.location = self.config.get("location", "India")
        self.sites = self.config.get("sites", DEFAULT_SITES)
        self.results_per_query = self.config.get("results_per_query", 10)
        self.hours_old = self.config.get("hours_old", 24)  # Past 24 hours
        self.country_indeed = self.config.get("country_indeed", "India")

    async def fetch_new_postings(self, since: Optional[datetime] = None) -> List[JobPosting]:
        if not _check_jobspy_available():
            logger.warning(
                "JobSpyAdapter: python-jobspy is not installed. "
                "Install it with: pip install -U python-jobspy"
            )
            return []

        all_postings: List[JobPosting] = []
        seen_ids = set()
        loop = asyncio.get_event_loop()

        for query in self.queries:
            logger.info(
                f"[JobSpy] Scraping '{query}' across {self.sites} | "
                f"location={self.location} | hours_old={self.hours_old}"
            )

            try:
                # Run sync JobSpy in thread executor to not block asyncio
                records = await loop.run_in_executor(
                    _jobspy_executor,
                    _run_jobspy_sync,
                    query,
                    self.location,
                    self.sites,
                    self.results_per_query,
                    self.hours_old,
                    self.country_indeed,
                )

                logger.info(f"[JobSpy] Query '{query}' returned {len(records)} results.")

                for record in records:
                    # Normalize the JobSpy DataFrame columns to our JobPosting schema
                    title = str(record.get("title") or "").strip()
                    company = str(record.get("company_name") or record.get("company") or "Unknown").strip()
                    location = str(record.get("location") or self.location).strip()
                    job_url = str(record.get("job_url") or record.get("link") or "").strip()
                    site = str(record.get("site") or "jobspy").strip()
                    description = str(record.get("description") or "").strip()

                    # Generate stable external ID
                    external_id = str(
                        record.get("id")
                        or record.get("job_url_direct")
                        or f"jobspy_{site}_{hash(job_url or title)}"
                    )

                    if not title or external_id in seen_ids:
                        continue
                    seen_ids.add(external_id)

                    # Remote detection
                    is_remote = bool(record.get("is_remote")) or "remote" in f"{title} {location}".lower()

                    # Salary extraction
                    salary_min = None
                    salary_max = None
                    salary_currency = None
                    if record.get("min_amount") is not None:
                        try:
                            salary_min = float(record["min_amount"])
                        except (ValueError, TypeError):
                            pass
                    if record.get("max_amount") is not None:
                        try:
                            salary_max = float(record["max_amount"])
                        except (ValueError, TypeError):
                            pass
                    if record.get("currency"):
                        salary_currency = str(record["currency"])

                    # Date parsing
                    posted_date = datetime.utcnow()
                    raw_date = record.get("date_posted")
                    if raw_date:
                        try:
                            if isinstance(raw_date, str):
                                posted_date = datetime.fromisoformat(raw_date)
                            elif hasattr(raw_date, "isoformat"):
                                posted_date = datetime.fromisoformat(raw_date.isoformat())
                        except Exception:
                            posted_date = datetime.utcnow()

                    all_postings.append(
                        JobPosting(
                            source_name=f"jobspy_{site}",
                            external_id=external_id,
                            title=title,
                            company=company,
                            location=location,
                            is_remote=is_remote,
                            description=description if description else f"{title} at {company}",
                            url=job_url,
                            salary_min=salary_min,
                            salary_max=salary_max,
                            salary_currency=salary_currency,
                            posted_date=posted_date,
                            raw_metadata={
                                "jobspy_site": site,
                                "query": query,
                                "scraped_at": datetime.utcnow().isoformat(),
                                "source_tier": "jobspy_free",
                            }
                        )
                    )

            except Exception as e:
                logger.error(f"[JobSpy] Error scraping query '{query}': {e}", exc_info=True)

            # Small pause between queries to be polite
            await asyncio.sleep(1.5)

        logger.info(f"[JobSpy] Total unique postings collected: {len(all_postings)}")
        return all_postings
