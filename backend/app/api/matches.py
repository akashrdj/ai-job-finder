from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Optional

from app.database import get_db
from app.models.match_score import MatchScore
from app.models.job import Job
from app.schemas.match import MatchScoreResponse

router = APIRouter(prefix="/api/matches", tags=["matches"])

@router.get("", response_model=List[MatchScoreResponse])
async def list_matches(
    min_score: float = Query(default=0.0, ge=0.0, le=100.0),
    variant: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(MatchScore)
        .options(selectinload(MatchScore.job))
        .where(MatchScore.score >= min_score)
        .order_by(MatchScore.score.desc())
    )
    if variant:
        stmt = stmt.where(MatchScore.selected_variant == variant)
    stmt = stmt.limit(limit)

    matches = (await db.execute(stmt)).scalars().all()
    return matches
