"""
Ingestion Manager — Three-Tier Architecture
================================================================================
TIER 1 — FREE FREQUENT (every 15 min):
    LinkedIn Guest Scraper, JobSpy, JSearch, Adzuna, ATS adapters
    Zero cost. Runs on every fast-lane discovery cycle.

TIER 2 — FREE MODERATE (every 2 hours):
    Company Portal Tracker, Scraper Fallback
    Zero cost but heavier HTTP. Runs less frequently.

TIER 3 — PAID DAILY (once/day at 6 PM IST):
    Apify Cloud Scraper ($5/mo budget)
    Cost-guarded: 512 MB memory, 60s timeout, 15 rows max.
================================================================================
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.job import Job
from app.models.source import Source
from app.ingestion.base import SourceAdapter, JobPosting
from app.ingestion.greenhouse import GreenhouseAdapter
from app.ingestion.lever import LeverAdapter
from app.ingestion.remoteok import RemoteOKAdapter
from app.ingestion.workday import WorkdayAdapter
from app.ingestion.scraper_fallback import ScraperFallbackAdapter
from app.ingestion.jsearch import JSearchAdapter
from app.ingestion.adzuna import AdzunaAdapter
from app.ingestion.company_portal_tracker import CompanyPortalTrackerAdapter
from app.ingestion.linkedin_scraper import LinkedInGuestScraperAdapter
from app.ingestion.apify_scraper import ApifyJobScraperAdapter
from app.ingestion.jobspy_scraper import JobSpyAdapter

logger = logging.getLogger(__name__)

# ── Adapter tiers for cost-aware scheduling ──────────────────────────────────

# TIER 1: Free, lightweight — run every 15 minutes
FREE_FREQUENT_ADAPTERS = [
    "linkedin_scraper",   # $0 — direct LinkedIn guest API
    "jobspy",             # $0 — scrapes LinkedIn + Indeed + Glassdoor + Google
    "jsearch",            # $0 — RapidAPI free tier (500 req/mo)
    "adzuna",             # $0 — Adzuna free tier (250 req/mo)
    "greenhouse",         # $0 — public ATS API
    "remoteok",           # $0 — public API
    "lever",              # $0 — public ATS API
    "workday",            # $0 — public ATS API
]

# TIER 2: Free but heavier — run every 2 hours
FREE_MODERATE_ADAPTERS = [
    "portal_tracker",     # $0 — custom career page crawling
    "scraper_fallback",   # $0 — generic schema.org extraction
]

# TIER 3: Paid — run once/day at 6 PM IST only
PAID_DAILY_ADAPTERS = [
    "apify_scraper",      # ~$0.81/mo at 1 run/day (within $5 free)
]


class IngestionManager:
    def __init__(self):
        self.adapters: Dict[str, SourceAdapter] = {
            # TIER 1 — Free Frequent (every 15 min)
            "linkedin_scraper": LinkedInGuestScraperAdapter(),
            "jobspy": JobSpyAdapter(),
            "jsearch": JSearchAdapter(),
            "adzuna": AdzunaAdapter(),
            "greenhouse": GreenhouseAdapter(),
            "remoteok": RemoteOKAdapter(),
            "lever": LeverAdapter(),
            "workday": WorkdayAdapter(),
            # TIER 2 — Free Moderate (every 2 hours)
            "portal_tracker": CompanyPortalTrackerAdapter(),
            "scraper_fallback": ScraperFallbackAdapter(),
            # TIER 3 — Paid Daily (6 PM IST only)
            "apify_scraper": ApifyJobScraperAdapter(),
        }

    def register_adapter(self, name: str, adapter: SourceAdapter):
        self.adapters[name] = adapter

    def get_tier_adapters(self, tier: str) -> List[str]:
        """Get adapter names for a specific tier."""
        if tier == "free_frequent":
            return FREE_FREQUENT_ADAPTERS
        elif tier == "free_moderate":
            return FREE_MODERATE_ADAPTERS
        elif tier == "paid_daily":
            return PAID_DAILY_ADAPTERS
        elif tier == "all_free":
            return FREE_FREQUENT_ADAPTERS + FREE_MODERATE_ADAPTERS
        elif tier == "all":
            return FREE_FREQUENT_ADAPTERS + FREE_MODERATE_ADAPTERS + PAID_DAILY_ADAPTERS
        else:
            return list(self.adapters.keys())

    async def run_ingestion(self, db: AsyncSession, source_names: Optional[List[str]] = None) -> List[Job]:
        """
        Run ingestion across specified or all active sources.
        Saves new non-duplicate postings into DB and returns newly inserted Job records.

        Args:
            db: Database session
            source_names: List of specific adapter names to run. If None, runs ALL adapters.
                          Use get_tier_adapters() for cost-aware selection.
        """
        active_adapters = [
            (name, adapter) for name, adapter in self.adapters.items()
            if (not source_names or name in source_names)
        ]

        tier_label = "ALL" if not source_names else f"selected ({len(active_adapters)})"
        logger.info(f"Starting ingestion across {len(active_adapters)} adapters [{tier_label}]...")

        # Run all selected adapters concurrently
        async def fetch_with_adapter(name: str, adapter: SourceAdapter) -> List[JobPosting]:
            try:
                postings = await adapter.fetch_new_postings()
                logger.info(f"Source '{name}' returned {len(postings)} postings.")
                return postings
            except Exception as e:
                logger.error(f"Error in adapter '{name}': {e}", exc_info=True)
                return []

        tasks = [fetch_with_adapter(name, adapter) for name, adapter in active_adapters]
        results = await asyncio.gather(*tasks)

        all_incoming: List[JobPosting] = []
        for res in results:
            all_incoming.extend(res)

        logger.info(f"Total incoming postings before deduplication: {len(all_incoming)}")

        # Deduplication against database
        newly_saved_jobs: List[Job] = []
        for posting in all_incoming:
            # Check if (source_name, external_id) exists
            stmt = select(Job).where(
                Job.source_name == posting.source_name,
                Job.external_id == posting.external_id
            )
            existing = (await db.execute(stmt)).scalars().first()
            if existing:
                continue

            # Create new job entry
            job = Job(
                source_name=posting.source_name,
                external_id=posting.external_id,
                title=posting.title,
                company=posting.company,
                location=posting.location,
                is_remote=posting.is_remote,
                description=posting.description,
                url=posting.url,
                salary_min=posting.salary_min,
                salary_max=posting.salary_max,
                salary_currency=posting.salary_currency,
                posted_date=posting.posted_date,
                raw_metadata=posting.raw_metadata,
                fetched_at=datetime.utcnow()
            )
            db.add(job)
            newly_saved_jobs.append(job)

        if newly_saved_jobs:
            await db.commit()
            for j in newly_saved_jobs:
                await db.refresh(j)
            logger.info(f"Successfully saved {len(newly_saved_jobs)} new jobs to database.")

            # Auto-harvest newly discovered Workday boards from incoming job URLs (Adzuna, JSearch, JobSpy, etc.)
            workday_urls = [j.url for j in newly_saved_jobs if j.url and "myworkdayjobs.com" in j.url]
            if workday_urls:
                try:
                    from app.ingestion.workday_discovery import WorkdayDiscoveryService
                    disc = WorkdayDiscoveryService()
                    new_candidates = disc.register_urls(workday_urls)
                    if new_candidates:
                        logger.info(f"Auto-harvested {len(new_candidates)} new Workday target candidate(s) from fresh job URLs.")
                except Exception as e:
                    logger.debug(f"Workday auto-harvest note: {e}")
        else:
            logger.info("No new unique jobs to save (all duplicates or up-to-date).")

        return newly_saved_jobs
