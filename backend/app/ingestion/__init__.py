from app.ingestion.base import SourceAdapter, JobPosting
from app.ingestion.greenhouse import GreenhouseAdapter
from app.ingestion.lever import LeverAdapter
from app.ingestion.remoteok import RemoteOKAdapter
from app.ingestion.workday import WorkdayAdapter
from app.ingestion.scraper_fallback import ScraperFallbackAdapter
from app.ingestion.jsearch import JSearchAdapter
from app.ingestion.adzuna import AdzunaAdapter
from app.ingestion.manager import IngestionManager

__all__ = [
    "SourceAdapter", "JobPosting",
    "GreenhouseAdapter", "LeverAdapter", "RemoteOKAdapter", "WorkdayAdapter", "ScraperFallbackAdapter",
    "JSearchAdapter", "AdzunaAdapter",
    "IngestionManager"
]
