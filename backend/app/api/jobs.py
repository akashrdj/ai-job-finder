from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from collections import defaultdict

from app.database import get_db
from app.models.job import Job
from app.schemas.job import JobResponse

from app.ingestion.constants import is_senior_title
from app.matching.rules import extract_experience_requirements, FRESHER_JD_SIGNALS

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=List[JobResponse])
async def list_jobs(
    search: Optional[str] = None,
    source: Optional[str] = None,
    remote_only: Optional[bool] = None,
    work_type: Optional[str] = None,   # "wfh" | "onsite" | None
    company: Optional[str] = None,
    fresher_only: bool = Query(default=True, description="Filter out senior and 2+ YOE roles"),
    limit: int = Query(default=200, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """
    List all ingested jobs with strict fresher filtering by default.
    """
    stmt = select(Job).order_by(Job.company.asc(), Job.fetched_at.desc())

    if source:
        stmt = stmt.where(Job.source_name == source)

    if work_type == "wfh":
        stmt = stmt.where(Job.is_remote == True)
    elif work_type == "onsite":
        stmt = stmt.where(Job.is_remote == False)
    elif remote_only:
        stmt = stmt.where(Job.is_remote == True)

    if company:
        stmt = stmt.where(Job.company.ilike(f"%{company}%"))

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            (Job.title.ilike(pattern))
            | (Job.company.ilike(pattern))
            | (Job.description.ilike(pattern))
        )

    # Fetch extra records if filtering in python
    fetch_limit = limit * 2 if fresher_only else limit
    stmt = stmt.offset(offset).limit(fetch_limit)
    raw_jobs = (await db.execute(stmt)).scalars().all()

    if not fresher_only:
        return raw_jobs[:limit]

    filtered_jobs = []
    for j in raw_jobs:
        if is_senior_title(j.title or ""):
            continue
        desc_lower = (j.description or "").lower()
        has_0yoe = any(sig in desc_lower for sig in ["0-1", "0-2", "0 to 1", "0 to 2", "fresher", "freshers", "graduate", "batch of 2025", "batch of 2026"])
        mins = extract_experience_requirements(j.description or "")
        if mins and min(mins) >= 2 and not has_0yoe:
            continue
        filtered_jobs.append(j)
        if len(filtered_jobs) >= limit:
            break

    return filtered_jobs


@router.get("/grouped")
async def list_jobs_grouped(
    search: Optional[str] = None,
    work_type: Optional[str] = None,   # "wfh" | "onsite" | None (both)
    source: Optional[str] = None,
    fresher_only: bool = Query(default=True, description="Filter out senior and 2+ YOE roles"),
    db: AsyncSession = Depends(get_db)
):
    """
    Return jobs grouped by company, sorted alphabetically.
    Supports strict fresher filtering by default.
    """
    stmt = select(Job).order_by(Job.company.asc(), Job.title.asc())

    if work_type == "wfh":
        stmt = stmt.where(Job.is_remote == True)
    elif work_type == "onsite":
        stmt = stmt.where(Job.is_remote == False)

    if source:
        stmt = stmt.where(Job.source_name == source)

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            (Job.title.ilike(pattern))
            | (Job.company.ilike(pattern))
        )

    jobs = (await db.execute(stmt)).scalars().all()

    # Group by company
    grouped: dict = defaultdict(lambda: {"company": "", "jobs": [], "wfh_count": 0, "onsite_count": 0})

    for job in jobs:
        if fresher_only:
            if is_senior_title(job.title or ""):
                continue
            desc_lower = (job.description or "").lower()
            has_0yoe = any(sig in desc_lower for sig in ["0-1", "0-2", "0 to 1", "0 to 2", "fresher", "freshers", "graduate", "batch of 2025", "batch of 2026"])
            mins = extract_experience_requirements(job.description or "")
            if mins and min(mins) >= 2 and not has_0yoe:
                continue

        key = job.company
        grouped[key]["company"] = job.company
        grouped[key]["jobs"].append({
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "is_remote": job.is_remote,
            "work_type": "wfh" if job.is_remote else "onsite",
            "source_name": job.source_name,
            "url": job.url,
            "posted_date": job.posted_date.isoformat() if job.posted_date else None,
            "description_snippet": (job.description or "")[:280] + "..." if len(job.description or "") > 280 else job.description,
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "salary_currency": job.salary_currency,
        })
        if job.is_remote:
            grouped[key]["wfh_count"] += 1
        else:
            grouped[key]["onsite_count"] += 1

    # Sort companies alphabetically
    result = sorted(grouped.values(), key=lambda x: x["company"].lower())
    return result


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Job).where(Job.id == job_id)
    job = (await db.execute(stmt)).scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
