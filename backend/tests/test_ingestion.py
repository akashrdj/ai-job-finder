import pytest
from datetime import datetime
from app.ingestion.base import SourceAdapter, JobPosting
from app.ingestion.manager import IngestionManager
from app.database import AsyncSessionLocal, init_db
from sqlalchemy import select, delete
from app.models.job import Job

class MockAdapter(SourceAdapter):
    def __init__(self, name: str):
        super().__init__(name)

    async def fetch_new_postings(self, since=None):
        return [
            JobPosting(
                source_name="mock_source",
                external_id="job_001",
                title="Junior Backend Engineer",
                company="Acme Corp",
                location="Remote",
                is_remote=True,
                description="Looking for Python FastAPI developer",
                url="https://acme.com/jobs/1"
            ),
            JobPosting(
                source_name="mock_source",
                external_id="job_002",
                title="Junior Frontend Engineer",
                company="Acme Corp",
                location="Bengaluru",
                is_remote=False,
                description="Looking for React developer",
                url="https://acme.com/jobs/2"
            )
        ]

@pytest.mark.asyncio
async def test_ingestion_manager_deduplication():
    await init_db()
    async with AsyncSessionLocal() as db:
        # Clear existing jobs for this test
        await db.execute(delete(Job))
        await db.commit()

        mgr = IngestionManager()
        mgr.adapters = {"mock_source": MockAdapter("mock_source")}

        # First run: inserts 2 jobs
        new_jobs = await mgr.run_ingestion(db)
        assert len(new_jobs) == 2

        # Second run: 0 new jobs due to deduplication
        second_run_jobs = await mgr.run_ingestion(db)
        assert len(second_run_jobs) == 0

        # Verify DB records
        stmt = select(Job).where(Job.source_name == "mock_source")
        db_jobs = (await db.execute(stmt)).scalars().all()
        assert len(db_jobs) == 2
