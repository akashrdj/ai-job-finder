import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.config import settings
from app.database import init_db
import app.database as app_db
from app.models.user_profile import UserProfile
from app.api.profile import DEFAULT_CANDIDATE_DATA
from app.api import profile_router, jobs_router, matches_router, drafts_router, ingestion_router, gap_router, outreach_router
from app.scheduler.scheduler_service import scheduler_service

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    await init_db()

    # Ensure default candidate profile exists
    async with app_db.AsyncSessionLocal() as db:
        stmt = select(UserProfile).where(UserProfile.is_active == True)
        existing_profile = (await db.execute(stmt)).scalars().first()
        if not existing_profile:
            logger.info("Seeding default candidate profile with 4 Curated Variants Matrix...")
            profile = UserProfile(**DEFAULT_CANDIDATE_DATA)
            db.add(profile)
            await db.commit()

    # Start background scheduler
    logger.info("Starting background scheduler...")
    scheduler_service.start()

    yield

    # Shutdown
    logger.info("Shutting down scheduler...")
    scheduler_service.stop()

app = FastAPI(
    title=settings.APP_NAME,
    description="Intelligent, Fact-Grounded Job Ingestion, Matching & Application Drafting Engine",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(profile_router)
app.include_router(jobs_router)
app.include_router(matches_router)
app.include_router(drafts_router)
app.include_router(ingestion_router)
app.include_router(gap_router)
app.include_router(outreach_router)

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "llm_provider": settings.LLM_PROVIDER,
        "scheduler_running": scheduler_service.scheduler.running
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
