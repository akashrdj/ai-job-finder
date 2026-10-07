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

logger = logging.getLogger(__name__)

class IngestionManager:
    def __init__(self):
        self.adapters: Dict[str, SourceAdapter] = {
            # Aggregator APIs — broadest coverage (all companies)
            "jsearch": JSearchAdapter(),
            "adzuna": AdzunaAdapter(),
            # ATS-specific APIs — curated company lists
            "greenhouse": GreenhouseAdapter(),
            "remoteok": RemoteOKAdapter(),
            "lever": LeverAdapter(),
            "workday": WorkdayAdapter(),
            "portal_tracker": CompanyPortalTrackerAdapter(),
            "scraper_fallback": ScraperFallbackAdapter()
        }

    def register_adapter(self, name: str, adapter: SourceAdapter):
        self.adapters[name] = adapter

    async def run_ingestion(self, db: AsyncSession, source_names: Optional[List[str]] = None) -> List[Job]:
        """
        Run ingestion across specified or all active sources.
        Saves new non-duplicate postings into DB and returns newly inserted Job records.
        """
        active_adapters = [
            (name, adapter) for name, adapter in self.adapters.items()
            if (not source_names or name in source_names)
        ]

        logger.info(f"Starting ingestion across {len(active_adapters)} adapters...")

        # Run all adapters concurrently
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
        else:
            logger.info("No new unique jobs to save (all duplicates or up-to-date).")

        return newly_saved_jobs
