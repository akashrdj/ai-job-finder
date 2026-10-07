import pytest
import app.database as app_db
from app.database import init_db
from app.models.user_profile import UserProfile
from app.models.job import Job
from app.models.match_score import MatchScore
from app.models.application_draft import ApplicationDraft
from app.api.profile import DEFAULT_CANDIDATE_DATA
from app.scheduler.scheduler_service import scheduler_service
from app.ingestion.base import SourceAdapter, JobPosting
from sqlalchemy import select, delete

class MockE2EAdapter(SourceAdapter):
    def __init__(self, name: str):
        super().__init__(name)

    async def fetch_new_postings(self, since=None):
        return [
            JobPosting(
                source_name="e2e_source",
                external_id="e2e_001",
                title="Python Backend Software Engineer (0-1 YOE)",
                company="Stripe FastTech",
                location="Remote",
                is_remote=True,
                description="We are seeking an entry-level Python & FastAPI software engineer to build scalable REST APIs with PostgreSQL and Redis.",
                url="https://example.com/apply/e2e1"
            ),
            JobPosting(
                source_name="e2e_source",
                external_id="e2e_002",
                title="Senior Director of Nursing",
                company="Hospital Corp",
                location="Onsite",
                is_remote=False,
                description="Medical healthcare nursing leadership 10+ years.",
                url="https://example.com/apply/e2e2"
            )
        ]

@pytest.mark.asyncio
async def test_full_pipeline_e2e():
    await init_db()

    # 1. Ensure clean slate and Profile exists
    async with app_db.AsyncSessionLocal() as db:
        await db.execute(delete(ApplicationDraft))
        await db.execute(delete(MatchScore))
        await db.execute(delete(Job))
        await db.commit()

        stmt = select(UserProfile).where(UserProfile.is_active == True)
        profile = (await db.execute(stmt)).scalars().first()
        if not profile:
            profile = UserProfile(**DEFAULT_CANDIDATE_DATA)
            db.add(profile)
            await db.commit()

    # 2. Inject mock adapter into scheduler
    scheduler_service.ingestion_manager.adapters = {"e2e_source": MockE2EAdapter("e2e_source")}

    # 3. Execute full pipeline
    stats = await scheduler_service.execute_full_pipeline()
    assert stats["status"] == "success"
    assert stats["new_jobs_found"] >= 2
    assert stats["jobs_scored"] >= 2
    assert stats["drafts_created"] >= 1 # High-fit Python job must be drafted

    # 4. Verify DB draft record
    async with app_db.AsyncSessionLocal() as db:
        stmt = select(ApplicationDraft).join(Job).where(Job.external_id == "e2e_001")
        draft = (await db.execute(stmt)).scalars().first()
        assert draft is not None
        assert draft.claim_validation_status == "PASSED"
        assert draft.outreach_kit is not None
        assert "linkedin_pitch" in draft.outreach_kit
        assert "search_recruiters" in draft.outreach_kit["linkedin_search_links"]
