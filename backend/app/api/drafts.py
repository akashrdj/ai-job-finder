from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app.models.application_draft import ApplicationDraft
from app.models.job import Job
from app.models.user_profile import UserProfile
from app.models.match_score import MatchScore
from app.schemas.draft import ApplicationDraftResponse, ApplicationDraftActionUpdate
from app.drafting.engine import DraftingEngine

router = APIRouter(prefix="/api/drafts", tags=["drafts"])
drafting_engine = DraftingEngine()

@router.get("", response_model=List[ApplicationDraftResponse])
async def list_drafts(
    action: Optional[str] = Query(default=None), # "pending", "applied", "dismissed"
    claim_status: Optional[str] = None, # "PASSED", "FLAGGED_UNVERIFIED_CLAIMS"
    limit: int = Query(default=100, le=200),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(ApplicationDraft)
        .options(
            selectinload(ApplicationDraft.job),
            selectinload(ApplicationDraft.match_score)
        )
        .order_by(ApplicationDraft.created_at.desc())
    )

    if action:
        stmt = stmt.where(ApplicationDraft.user_action == action)
    if claim_status:
        stmt = stmt.where(ApplicationDraft.claim_validation_status == claim_status)

    stmt = stmt.limit(limit)
    drafts = (await db.execute(stmt)).scalars().all()
    return drafts

@router.get("/{draft_id}", response_model=ApplicationDraftResponse)
async def get_draft(draft_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(ApplicationDraft)
        .options(
            selectinload(ApplicationDraft.job),
            selectinload(ApplicationDraft.match_score)
        )
        .where(ApplicationDraft.id == draft_id)
    )
    draft = (await db.execute(stmt)).scalars().first()
    if not draft:
        raise HTTPException(status_code=404, detail="Application draft not found")
    return draft

@router.patch("/{draft_id}/action", response_model=ApplicationDraftResponse)
async def update_draft_action(
    draft_id: int,
    payload: ApplicationDraftActionUpdate,
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(ApplicationDraft)
        .options(
            selectinload(ApplicationDraft.job),
            selectinload(ApplicationDraft.match_score)
        )
        .where(ApplicationDraft.id == draft_id)
    )
    draft = (await db.execute(stmt)).scalars().first()
    if not draft:
        raise HTTPException(status_code=404, detail="Application draft not found")

    draft.user_action = payload.user_action
    if payload.notes is not None:
        draft.notes = payload.notes
    draft.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(draft)
    return draft

@router.post("/{draft_id}/regenerate", response_model=ApplicationDraftResponse)
async def regenerate_draft(draft_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(ApplicationDraft)
        .options(
            selectinload(ApplicationDraft.job),
            selectinload(ApplicationDraft.match_score)
        )
        .where(ApplicationDraft.id == draft_id)
    )
    draft = (await db.execute(stmt)).scalars().first()
    if not draft:
        raise HTTPException(status_code=404, detail="Application draft not found")

    profile_stmt = select(UserProfile).where(UserProfile.is_active == True)
    profile = (await db.execute(profile_stmt)).scalars().first()
    if not profile:
        raise HTTPException(status_code=400, detail="No active user profile found")

    updated_draft = await drafting_engine.draft_application(
        db=db,
        job=draft.job,
        profile=profile,
        match_score=draft.match_score
    )

    # Re-fetch with relationships loaded
    return await get_draft(updated_draft.id, db)
