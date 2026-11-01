import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from urllib.parse import quote_plus
import httpx
from bs4 import BeautifulSoup

from app.ingestion.base import SourceAdapter, JobPosting

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

DEFAULT_SEARCH_QUERIES = [
    "Software Engineer",
    "Python Developer",
    "Backend Developer",
    "Full Stack Developer",
    "AI Engineer"
]

class LinkedInGuestScraperAdapter(SourceAdapter):
    """
    Direct LinkedIn Guest Job Scraper.
    Scrapes the freshest jobs posted within the last 24 hours (f_TPR=r86400).
    Requires NO login, NO session cookies, and NO paid API tokens.
    Extracts full job descriptions directly from LinkedIn's public guest endpoints.
    """

    def __init__(self, name: str = "linkedin_scraper", config: Optional[Dict[str, Any]] = None):
        super().__init__(name, config)
        self.location = self.config.get("location", "India")
        self.queries = self.config.get("queries", DEFAULT_SEARCH_QUERIES)
        self.time_filter = self.config.get("time_filter", "r86400") # r86400 = Past 24 hours
        self.max_jobs_per_query = self.config.get("max_jobs_per_query", 10)
        self.headers = {
            "User-Agent": USER_AGENTS[0],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def _fetch_full_description(self, client: httpx.AsyncClient, job_id: str) -> str:
        """Fetch complete job description text from LinkedIn public guest endpoint."""
        url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
        try:
            resp = await client.get(url, headers=self.headers, timeout=10.0)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                desc_div = soup.find("div", class_="show-more-less-html__markup")
                if desc_div:
                    return desc_div.get_text(separator="\n", strip=True)
                article = soup.find("article")
                if article:
                    return article.get_text(separator="\n", strip=True)
            elif resp.status_code == 429:
                logger.debug(f"LinkedIn detail rate-limit hit (429) for job {job_id}. Using card summary fallback.")
        except Exception as e:
            logger.debug(f"Could not fetch full JD for LinkedIn job {job_id}: {e}")
        return ""

    async def _scrape_query(self, client: httpx.AsyncClient, query: str) -> List[JobPosting]:
        encoded_query = quote_plus(query)
        encoded_loc = quote_plus(self.location)
        url = (
            f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"
            f"keywords={encoded_query}&location={encoded_loc}&f_TPR={self.time_filter}&start=0"
        )

        postings: List[JobPosting] = []
        try:
            resp = await client.get(url, headers=self.headers, timeout=15.0)
            if resp.status_code != 200:
                logger.warning(f"LinkedIn search for '{query}' returned HTTP {resp.status_code}")
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.find_all("li")
            logger.info(f"LinkedIn query '{query}' returned {len(cards)} candidate cards.")

            for card in cards[:self.max_jobs_per_query]:
                title_elem = card.find("h3", class_="base-search-card__title")
                company_elem = card.find("h4", class_="base-search-card__subtitle")
                loc_elem = card.find("span", class_="job-search-card__location")
                link_elem = card.find("a", class_="base-card__full-link")
                time_elem = card.find("time")

                if not title_elem or not link_elem:
                    continue

                title = title_elem.get_text(strip=True)
                company = company_elem.get_text(strip=True) if company_elem else "Hiring Company"
                location = loc_elem.get_text(strip=True) if loc_elem else self.location
                raw_url = link_elem.get("href", "")
                clean_url = raw_url.split("?")[0] if raw_url else ""

                # Extract Job ID
                job_id_match = re.search(r"(\d{8,12})", raw_url)
                job_id = job_id_match.group(1) if job_id_match else f"li_{hash(clean_url or title)}"

                # Check remote status
                is_remote = any(k in (title + " " + location).lower() for k in ["remote", "work from home", "wfh"])

                # Parse date
                posted_date = datetime.utcnow()
                if time_elem and time_elem.get("datetime"):
                    try:
                        posted_date = datetime.fromisoformat(time_elem["datetime"])
                    except Exception:
                        posted_date = datetime.utcnow()

                # Fetch full description
                description = await self._fetch_full_description(client, job_id)
                if not description:
                    description = f"{title} at {company} in {location}. Posted on LinkedIn."

                postings.append(
                    JobPosting(
                        source_name="linkedin_scraper",
                        external_id=str(job_id),
                        title=title,
                        company=company,
                        location=location,
                        is_remote=is_remote,
                        description=description,
                        url=clean_url or raw_url,
                        posted_date=posted_date,
                        raw_metadata={
                            "query": query,
                            "scraped_at": datetime.utcnow().isoformat(),
                            "source_tier": "direct_linkedin_guest"
                        }
                    )
                )

                # Polite spacing between detailed JD fetches
                await asyncio.sleep(1.0)

        except Exception as e:
            logger.error(f"Error scraping LinkedIn query '{query}': {e}", exc_info=True)

        return postings

    async def fetch_new_postings(self, since: Optional[datetime] = None) -> List[JobPosting]:
        all_postings: List[JobPosting] = []
        seen_ids = set()

        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            for query in self.queries:
                logger.info(f"Scraping latest LinkedIn jobs for '{query}' in '{self.location}' (past 24h)...")
                postings = await self._scrape_query(client, query)
                for p in postings:
                    if p.external_id not in seen_ids:
                        seen_ids.add(p.external_id)
                        all_postings.append(p)
                # Jitter pause between search queries
                await asyncio.sleep(2.0)

        logger.info(f"LinkedInGuestScraperAdapter collected {len(all_postings)} unique postings.")
        return all_postings
