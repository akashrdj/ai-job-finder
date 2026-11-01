"""
Apify Cloud Scraper Adapter — COST-OPTIMIZED for $5/month Free Tier
================================================================================
Budget Strategy:
  • 1 run/day at 6 PM IST (30 runs/month = ~$1.50 in compute)
  • Memory capped at 512 MB (vs default 4096 MB = 8x savings)
  • Hard timeout of 60 seconds (vs unlimited = prevents runaway billing)
  • Row cap of 15 items per run (fast execution, minimal proxy bandwidth)
  • Only past-24h postings (publishedAt: r86400)

Monthly cost estimate at 1 run/day:
  • 30 runs × 60s × 512MB = ~0.25 CU = ~$0.63/month
  • Proxy data: ~2 MB × 30 = 60 MB = ~$0.18/month
  • Total: ~$0.81/month (well within $5 free credit)
================================================================================
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
import httpx

from app.config import settings
from app.ingestion.base import SourceAdapter, JobPosting

logger = logging.getLogger(__name__)

# Cost guard: absolute max items per actor run
MAX_SAFE_ITEMS = 20
# Cost guard: actor memory in MB (512 MB = cheapest viable)
ACTOR_MEMORY_MB = 512
# Cost guard: hard timeout in seconds for the actor execution
ACTOR_TIMEOUT_SECONDS = 60


class ApifyJobScraperAdapter(SourceAdapter):
    """
    Apify Cloud Scraper Adapter — cost-optimized for the $5/month free tier.

    Executes Apify Actors (e.g. 'curious_coder/linkedin-jobs-scraper')
    with strict memory, timeout, and row caps to prevent runaway billing.

    This adapter is designed to run ONCE PER DAY (at 6 PM IST) via the scheduler.
    The free LinkedIn guest scraper handles the frequent polling.
    """

    def __init__(self, name: str = "apify_scraper", config: Optional[Dict[str, Any]] = None):
        super().__init__(name, config)
        self.api_token = self.config.get("api_token") or settings.APIFY_API_TOKEN
        self.actor_id = self.config.get("actor_id") or settings.APIFY_ACTOR_ID or "curious_coder/linkedin-jobs-scraper"
        self.keywords = self.config.get("keywords", ["Software Engineer", "Python Developer", "Full Stack Developer"])
        self.location = self.config.get("location", "India")
        # Cost guard: cap items at safe maximum
        self.max_items = min(
            self.config.get("max_items", 15),
            MAX_SAFE_ITEMS
        )

    def is_configured(self) -> bool:
        return bool(self.api_token and self.api_token.strip())

    async def fetch_new_postings(self, since: Optional[datetime] = None) -> List[JobPosting]:
        if not self.is_configured():
            logger.info(
                "ApifyJobScraperAdapter: APIFY_API_TOKEN not set. Skipping. "
                "(Get free $5/mo at https://console.apify.com)"
            )
            return []

        actor_id_clean = self.actor_id.replace("/", "~")

        # Cost-optimized API call:
        # - timeout: 60s hard cap (prevents runaway actor consuming credits)
        # - memory: 512 MB (minimum viable, 8x cheaper than default 4096 MB)
        url = (
            f"https://api.apify.com/v2/acts/{actor_id_clean}/run-sync-get-dataset-items"
            f"?token={self.api_token}"
            f"&timeout={ACTOR_TIMEOUT_SECONDS}"
            f"&memory={ACTOR_MEMORY_MB}"
        )

        # Payload for LinkedIn job scraper actors
        run_input = {
            "title": " OR ".join(self.keywords),
            "location": self.location,
            "rows": self.max_items,
            "publishedAt": "r86400",  # Past 24 hours only
            "remote": False,
        }

        logger.info(
            f"[APIFY $-GUARD] Triggering '{self.actor_id}' | "
            f"memory={ACTOR_MEMORY_MB}MB | timeout={ACTOR_TIMEOUT_SECONDS}s | "
            f"max_rows={self.max_items} | keywords={self.keywords}"
        )

        postings: List[JobPosting] = []
        try:
            # HTTP timeout slightly longer than actor timeout to capture results
            async with httpx.AsyncClient(timeout=float(ACTOR_TIMEOUT_SECONDS + 30)) as client:
                resp = await client.post(url, json=run_input)
                if resp.status_code not in (200, 201):
                    error_preview = resp.text[:300] if resp.text else "No body"
                    logger.error(f"Apify API error: HTTP {resp.status_code} - {error_preview}")
                    return []

                items = resp.json()
                if not isinstance(items, list):
                    logger.warning(f"Apify returned unexpected structure: {type(items)}")
                    return []

                logger.info(f"[APIFY] Received {len(items)} items from '{self.actor_id}'.")

                for item in items:
                    if not isinstance(item, dict):
                        continue

                    # Normalize across different actor output schemas
                    title = item.get("title") or item.get("jobTitle") or item.get("position") or ""
                    company = (
                        item.get("companyName")
                        or item.get("company")
                        or (item.get("company", {}).get("name") if isinstance(item.get("company"), dict) else "")
                        or "Unknown Company"
                    )
                    location = item.get("location") or item.get("jobLocation") or self.location
                    job_url = item.get("link") or item.get("jobUrl") or item.get("url") or ""
                    external_id = (
                        str(item.get("id") or item.get("jobId") or item.get("linkedinJobId") or "")
                        or f"apify_{hash(job_url or title)}"
                    )
                    description = (
                        item.get("description")
                        or item.get("jobDescription")
                        or item.get("text")
                        or f"{title} at {company} ({location})"
                    )
                    is_remote = item.get("isRemote", False) or "remote" in f"{title} {location}".lower()

                    posted_date = datetime.utcnow()
                    raw_date = item.get("postedDate") or item.get("publishedAt") or item.get("date")
                    if raw_date:
                        try:
                            posted_date = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
                        except Exception:
                            posted_date = datetime.utcnow()

                    if title:
                        postings.append(
                            JobPosting(
                                source_name="apify_scraper",
                                external_id=external_id,
                                title=title.strip(),
                                company=company.strip() if isinstance(company, str) else str(company),
                                location=location.strip() if isinstance(location, str) else str(location),
                                is_remote=is_remote,
                                description=description.strip(),
                                url=job_url,
                                posted_date=posted_date,
                                raw_metadata={
                                    "apify_actor": self.actor_id,
                                    "scraped_at": datetime.utcnow().isoformat(),
                                    "cost_guard": {
                                        "memory_mb": ACTOR_MEMORY_MB,
                                        "timeout_s": ACTOR_TIMEOUT_SECONDS,
                                        "max_rows": self.max_items,
                                    },
                                    "raw_item": {
                                        k: v for k, v in item.items()
                                        if k not in ("description", "jobDescription")
                                    }
                                }
                            )
                        )

        except httpx.TimeoutException:
            logger.warning(f"[APIFY $-GUARD] Actor timed out after {ACTOR_TIMEOUT_SECONDS}s. No billing runaway.")
        except Exception as e:
            logger.error(f"Error executing Apify actor '{self.actor_id}': {e}", exc_info=True)

        logger.info(f"[APIFY] Final result: {len(postings)} postings extracted.")
        return postings
