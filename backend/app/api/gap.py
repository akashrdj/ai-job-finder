import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.match_score import MatchScore
from app.models.user_profile import UserProfile
from app.matching.gap_analyzer import analyze_gap

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/matches", tags=["gap-analysis"])


@router.post("/{match_id}/analyze-gap")
async def analyze_resume_gap(match_id: int, db: AsyncSession = Depends(get_db)):
    """
    Trigger Gemini-powered gap analysis for a specific match.
    Reads the JD and candidate profile, returns what keywords/skills are missing
    from the resume so the candidate knows what to add before applying.
    """
    # Load the match with its job
    stmt = (
        select(MatchScore)
        .options(selectinload(MatchScore.job), selectinload(MatchScore.profile))
        .where(MatchScore.id == match_id)
    )
    match = (await db.execute(stmt)).scalars().first()
    if not match:
        raise HTTPException(status_code=404, detail=f"Match {match_id} not found.")

    job = match.job
    profile = match.profile

    if not job:
        raise HTTPException(status_code=404, detail="Job not found for this match.")
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found for this match.")

    logger.info(f"Running gap analysis for match {match_id} — Job: {job.title} @ {job.company}")

    gap_report = await analyze_gap(
        job_title=job.title,
        job_description=job.description or "",
        candidate_name=profile.full_name or "Candidate",
        candidate_skills=profile.skills or [],
        candidate_work_history=profile.work_history or [],
        candidate_projects=profile.projects or [],
    )

    # Persist the gap report so we don't re-run Gemini next time
    match.gap_report = gap_report
    await db.commit()
    await db.refresh(match)

    return {
        "match_id": match_id,
        "job_title": job.title,
        "company": job.company,
        "matched_skills": match.matched_skills or [],
        "missing_requirements": match.missing_requirements or [],
        "gap_report": gap_report,
    }
