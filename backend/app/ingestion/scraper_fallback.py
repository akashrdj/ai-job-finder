"""
================================================================================
LEGAL & ETHICAL COMPLIANCE SPECIFICATION FOR SCRAPER FALLBACK ADAPTER
================================================================================
1. Legal Basis:
   - This adapter operates strictly as a fallback mechanism for public web pages 
     lacking official programmatic APIs, subject to public availability without authentication.
   - Operates in compliance with robots.txt directives evaluated dynamically via
     urllib.robotparser prior to fetching any target URL.
   - Zero credential storage / zero session hijacking / zero bypass of authentication gates.

2. Rate Limiting & Politeness:
   - Mandatory minimum backoff of 3.0 seconds (plus random jitter) between requests per domain.
   - Identifies transparently via User-Agent:
     'AIJobFinder-ReviewBot/1.0 (+https://github.com/user/ai-job-finder; compliant review bot)'

3. Data Ingestion:
   - Prioritizes standard Schema.org 'JobPosting' structured JSON-LD embedded by employers.
================================================================================
"""

import asyncio
import json
import logging
import random
import urllib.robotparser
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from app.ingestion.base import SourceAdapter, JobPosting

logger = logging.getLogger(__name__)

USER_AGENT = "AIJobFinder-ReviewBot/1.0 (+https://github.com/user/ai-job-finder; compliant bot)"

class ScraperFallbackAdapter(SourceAdapter):
    """
    Ethical, robots.txt-compliant web scraper fallback.
    Extracts schema.org 'JobPosting' JSON-LD metadata from target career pages.
    """

    def __init__(self, name: str = "scraper_fallback", config: Optional[Dict[str, Any]] = None):
        super().__init__(name, config)
        self.target_urls = self.config.get("target_urls", [])
        self.min_delay_seconds = self.config.get("min_delay_seconds", 3.0)
        self._robots_cache: Dict[str, urllib.robotparser.RobotFileParser] = {}

    async def _check_robots_txt(self, target_url: str) -> bool:
        """
        Verify if automated crawling is permitted under target domain's robots.txt.
        """
        parsed = urlparse(target_url)
        base_domain = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = f"{base_domain}/robots.txt"

        if base_domain in self._robots_cache:
            rp = self._robots_cache[base_domain]
            return rp.can_fetch(USER_AGENT, target_url)

        rp = urllib.robotparser.RobotFileParser()
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(robots_url, headers={"User-Agent": USER_AGENT})
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                else:
                    # If 404 or no robots.txt, default allow per standard
                    rp.allow_all = True
        except Exception as e:
            logger.info(f"Could not fetch robots.txt from {robots_url}: {e}. Defaulting to polite allow.")
            rp.allow_all = True

        self._robots_cache[base_domain] = rp
        allowed = rp.can_fetch(USER_AGENT, target_url)
        logger.info(f"Robots.txt check for '{target_url}': {'ALLOWED' if allowed else 'DISALLOWED'}")
        return allowed

    def _extract_json_ld(self, html_content: str, source_url: str) -> List[JobPosting]:
        soup = BeautifulSoup(html_content, "html.parser")
        scripts = soup.find_all("script", type="application/ld+json")
        postings: List[JobPosting] = []

        for script in scripts:
            try:
                data = json.loads(script.string or "{}")
                # Can be a single dict or @graph array
                items = data.get("@graph", [data]) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    item_type = item.get("@type")
                    if item_type == "JobPosting":
                        title = item.get("title", "")
                        org = item.get("hiringOrganization", {})
                        company = org.get("name", "Startup") if isinstance(org, dict) else str(org)
                        desc = BeautifulSoup(item.get("description", ""), "html.parser").get_text(separator="\n", strip=True)
                        
                        location = "Not Specified"
                        loc_obj = item.get("jobLocation", {})
                        if isinstance(loc_obj, dict):
                            addr = loc_obj.get("address", {})
                            if isinstance(addr, dict):
                                location = f"{addr.get('addressLocality', '')}, {addr.get('addressCountry', '')}".strip(", ")
                        
                        is_remote = "remote" in location.lower() or "remote" in title.lower()
                        apply_url = item.get("url") or source_url

                        external_id = f"scrape_{hash(title + company + source_url) & 0xffffffff:x}"

                        postings.append(JobPosting(
                            source_name=self.name,
                            external_id=external_id,
                            title=title,
                            company=company,
                            location=location,
                            is_remote=is_remote,
                            description=desc,
                            url=apply_url,
                            posted_date=datetime.utcnow(),
                            raw_metadata={"scraped_url": source_url, "schema_type": "JobPosting"}
                        ))
            except Exception as e:
                logger.debug(f"JSON-LD parse error: {e}")

        return postings

    async def fetch_new_postings(self, since: Optional[datetime] = None) -> List[JobPosting]:
        all_postings: List[JobPosting] = []
        if not self.target_urls:
            return all_postings

        headers = {"User-Agent": USER_AGENT}

        async with httpx.AsyncClient(headers=headers, timeout=15.0, follow_redirects=True) as client:
            for url in self.target_urls:
                # 1. Robots.txt check
                is_allowed = await self._check_robots_txt(url)
                if not is_allowed:
                    logger.warning(f"Skipping scraping {url} per robots.txt restriction.")
                    continue

                # 2. Rate-limit politeness backoff
                jitter = random.uniform(0.5, 2.0)
                await asyncio.sleep(self.min_delay_seconds + jitter)

                # 3. Fetch
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        postings = self._extract_json_ld(resp.text, url)
                        all_postings.extend(postings)
                except Exception as e:
                    logger.warning(f"Error scraping {url}: {e}")

        return all_postings
