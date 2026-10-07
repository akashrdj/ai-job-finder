"""
Cold Outreach API Router
=========================
Endpoints for the full cold email automation pipeline:
  - Load companies from Excel sheets
  - Enrich contacts (Hunter.io, Snov.io, web scrape, patterns)
  - Generate AI-powered cold email drafts
  - Review, approve, and send drafts
  - Track outreach status
"""
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from app.database import get_db
from app.models.company_contact import CompanyContact
from app.outreach.excel_ingestion import load_all_companies, parse_freshers_xlsx
from app.outreach.contact_enrichment import (
    enrich_company_contacts,
    enrich_batch,
    generate_linkedin_search_links,
    guess_domain,
)
from app.outreach.cold_email_drafter import (
    generate_cold_email_draft,
    generate_batch_drafts,
)
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/outreach", tags=["outreach"])


# ──────────────────────────────────────────────────────────────────
# Request / Response Schemas
# ──────────────────────────────────────────────────────────────────

class EnrichRequest(BaseModel):
    company_name: str
    domain: Optional[str] = None
    industry: Optional[str] = None
    hunter_key: Optional[str] = None
    snov_id: Optional[str] = None
    snov_secret: Optional[str] = None

class BatchEnrichRequest(BaseModel):
    source: str = Field(default="freshers", description="'freshers', 'master', or 'all'")
    limit: Optional[int] = Field(default=None, description="Max companies to enrich")
    skip_already_enriched: bool = True
    hunter_key: Optional[str] = None
    snov_id: Optional[str] = None
    snov_secret: Optional[str] = None

class DraftRequest(BaseModel):
    contact_ids: Optional[List[int]] = None
    company_name: Optional[str] = None
    max_drafts: int = Field(default=5, le=20)

class ApproveRequest(BaseModel):
    contact_ids: List[int]
    send_immediately: bool = False

class SendRequest(BaseModel):
    contact_ids: List[int]


# ──────────────────────────────────────────────────────────────────
# Helper: Load candidate profile
# ──────────────────────────────────────────────────────────────────

def _load_profile() -> dict:
    """Load candidate profile from my_profile.json."""
    profile_path = Path(__file__).resolve().parent.parent.parent.parent / "my_profile.json"
    if profile_path.exists():
        with open(profile_path, "r", encoding="utf-8") as f:
            return json.load(f)
    # Fallback: return minimal profile
    return {
        "full_name": "Akash R Jadhav",
        "email": "akashrj090@gmail.com",
        "phone": "+91 7676265783",
        "skills": ["Python", "React", "FastAPI", "Docker"],
        "github_url": "https://github.com/akashrdj/portfolio",
        "linkedin_url": "https://www.linkedin.com/in/akashrjadhav/",
    }


# ──────────────────────────────────────────────────────────────────
# 1. Load Companies from Excel
# ──────────────────────────────────────────────────────────────────

@router.get("/companies")
async def list_companies(
    source: str = Query(default="all", description="'freshers', 'master', or 'all'"),
):
    """Load and list all companies from the Excel sheets."""
    all_companies = load_all_companies()

    if source == "freshers":
        companies = [c for c in all_companies if c.get("source_sheet") == "freshers"]
    elif source == "master":
        companies = [c for c in all_companies if c.get("source_sheet") == "master"]
    else:
        companies = all_companies

    return {
        "total": len(companies),
        "source_filter": source,
        "companies": companies,
    }


# ──────────────────────────────────────────────────────────────────
# 2. Enrich a Single Company
# ──────────────────────────────────────────────────────────────────

@router.post("/enrich")
async def enrich_single(
    req: EnrichRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Enrich contacts for a single company using the multi-source cascade.
    Saves discovered contacts to the database.
    """
    result = await enrich_company_contacts(
        company_name=req.company_name,
        domain=req.domain,
        industry=req.industry,
        hunter_key=req.hunter_key,
        snov_id=req.snov_id,
        snov_secret=req.snov_secret,
    )

    # Save to database
    saved_count = 0
    for contact_data in result["contacts"]:
        # Check if email already exists for this company
        existing = await db.execute(
            select(CompanyContact).where(
                CompanyContact.company_name == req.company_name,
                CompanyContact.contact_email == contact_data["contact_email"],
            )
        )
        if existing.scalars().first():
            continue

        contact = CompanyContact(
            company_name=req.company_name,
            company_domain=result["domain"],
            industry=req.industry,
            contact_name=contact_data.get("contact_name", ""),
            contact_email=contact_data["contact_email"],
            contact_role=contact_data.get("contact_role", ""),
            contact_title=contact_data.get("contact_title", ""),
            linkedin_url=contact_data.get("linkedin_url", ""),
            source=contact_data.get("source", "unknown"),
            confidence=contact_data.get("confidence"),
            is_verified=contact_data.get("is_verified", False),
            verification_status=contact_data.get("verification_status", "unknown"),
            fresher_role=contact_data.get("fresher_role"),
            opening_period=contact_data.get("opening_period"),
            target_contact_type=contact_data.get("target_contact_type"),
        )
        db.add(contact)
        saved_count += 1

    await db.commit()

    return {
        "company_name": req.company_name,
        "domain": result["domain"],
        "contacts_found": result["contact_count"],
        "contacts_saved": saved_count,
        "sources_used": result["sources_used"],
        "linkedin_search_links": result["linkedin_search_links"],
        "contacts": result["contacts"],
    }


# ──────────────────────────────────────────────────────────────────
# 3. Batch Enrich (All companies from Excel)
# ──────────────────────────────────────────────────────────────────

@router.post("/enrich/batch")
async def enrich_all(
    req: BatchEnrichRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Batch-enrich all companies from the selected Excel sheet.
    This runs the full cascade for each company.
    """
    all_companies = load_all_companies()

    if req.source == "freshers":
        companies = [c for c in all_companies if c.get("source_sheet") == "freshers"]
    elif req.source == "master":
        companies = [c for c in all_companies if c.get("source_sheet") == "master"]
    else:
        companies = all_companies

    # Skip already-enriched companies
    if req.skip_already_enriched:
        enriched_names = set()
        result = await db.execute(
            select(CompanyContact.company_name).distinct()
        )
        enriched_names = {r[0].lower() for r in result.all()}
        companies = [c for c in companies if c["company_name"].lower() not in enriched_names]

    if req.limit:
        companies = companies[:req.limit]

    if not companies:
        return {"message": "No new companies to enrich", "total": 0}

    # Also inject existing emails from master sheet
    for comp in companies:
        existing_emails = comp.get("existing_emails", [])
        for email in existing_emails:
            existing = await db.execute(
                select(CompanyContact).where(
                    CompanyContact.company_name == comp["company_name"],
                    CompanyContact.contact_email == email,
                )
            )
            if not existing.scalars().first():
                contact = CompanyContact(
                    company_name=comp["company_name"],
                    company_domain=guess_domain(comp["company_name"]),
                    industry=comp.get("industry", ""),
                    contact_email=email,
                    source="master_sheet",
                    confidence=60,
                    fresher_role=comp.get("fresher_role"),
                    opening_period=comp.get("opening_period"),
                    target_contact_type=comp.get("target_contact_type"),
                )
                db.add(contact)
        await db.commit()

    # Run enrichment cascade
    results = await enrich_batch(
        companies,
        hunter_key=req.hunter_key,
        snov_id=req.snov_id,
        snov_secret=req.snov_secret,
    )

    # Save enriched contacts
    total_saved = 0
    for result in results:
        for contact_data in result["contacts"]:
            existing = await db.execute(
                select(CompanyContact).where(
                    CompanyContact.company_name == result["company_name"],
                    CompanyContact.contact_email == contact_data["contact_email"],
                )
            )
            if existing.scalars().first():
                continue

            contact = CompanyContact(
                company_name=result["company_name"],
                company_domain=result["domain"],
                industry=contact_data.get("industry", ""),
                contact_name=contact_data.get("contact_name", ""),
                contact_email=contact_data["contact_email"],
                contact_role=contact_data.get("contact_role", ""),
                contact_title=contact_data.get("contact_title", ""),
                linkedin_url=contact_data.get("linkedin_url", ""),
                source=contact_data.get("source", "unknown"),
                confidence=contact_data.get("confidence"),
                is_verified=contact_data.get("is_verified", False),
                verification_status=contact_data.get("verification_status", "unknown"),
                fresher_role=contact_data.get("fresher_role"),
                opening_period=contact_data.get("opening_period"),
                target_contact_type=contact_data.get("target_contact_type"),
            )
            db.add(contact)
            total_saved += 1

    await db.commit()

    return {
        "companies_processed": len(results),
        "total_contacts_found": sum(r["contact_count"] for r in results),
        "total_contacts_saved": total_saved,
        "details": [
            {
                "company": r["company_name"],
                "domain": r["domain"],
                "contacts_found": r["contact_count"],
                "sources": r["sources_used"],
                "linkedin_links": r["linkedin_search_links"],
            }
            for r in results
        ],
    }


# ──────────────────────────────────────────────────────────────────
# 4. List Contacts (with filters)
# ──────────────────────────────────────────────────────────────────

@router.get("/contacts")
async def list_contacts(
    db: AsyncSession = Depends(get_db),
    company: Optional[str] = None,
    role: Optional[str] = None,
    source: Optional[str] = None,
    status: Optional[str] = None,
    min_confidence: Optional[float] = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
):
    """List all enriched contacts with optional filters."""
    query = select(CompanyContact)

    if company:
        query = query.where(CompanyContact.company_name.ilike(f"%{company}%"))
    if role:
        query = query.where(CompanyContact.contact_role.ilike(f"%{role}%"))
    if source:
        query = query.where(CompanyContact.source == source)
    if status:
        query = query.where(CompanyContact.cold_email_status == status)
    if min_confidence is not None:
        query = query.where(CompanyContact.confidence >= min_confidence)

    query = query.order_by(CompanyContact.confidence.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    contacts = result.scalars().all()

    # Total count
    count_query = select(func.count(CompanyContact.id))
    if company:
        count_query = count_query.where(CompanyContact.company_name.ilike(f"%{company}%"))
    total = (await db.execute(count_query)).scalar()

    return {
        "total": total,
        "showing": len(contacts),
        "offset": offset,
        "contacts": [
            {
                "id": c.id,
                "company_name": c.company_name,
                "company_domain": c.company_domain,
                "industry": c.industry,
                "contact_name": c.contact_name,
                "contact_email": c.contact_email,
                "contact_role": c.contact_role,
                "contact_title": c.contact_title,
                "linkedin_url": c.linkedin_url,
                "source": c.source,
                "confidence": c.confidence,
                "is_verified": c.is_verified,
                "cold_email_status": c.cold_email_status,
                "cold_email_subject": c.cold_email_subject,
                "fresher_role": c.fresher_role,
                "opening_period": c.opening_period,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in contacts
        ],
    }


# ──────────────────────────────────────────────────────────────────
# 5. Generate Cold Email Drafts
# ──────────────────────────────────────────────────────────────────

@router.post("/drafts/generate")
async def generate_drafts(
    req: DraftRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate AI-powered cold email drafts for selected contacts.
    Drafts are saved for review (not auto-sent).
    """
    profile = _load_profile()

    # Get contacts to draft for
    query = select(CompanyContact).where(
        CompanyContact.cold_email_status == "pending"
    )

    if req.contact_ids:
        query = select(CompanyContact).where(CompanyContact.id.in_(req.contact_ids))
    elif req.company_name:
        query = query.where(CompanyContact.company_name.ilike(f"%{req.company_name}%"))

    query = query.order_by(CompanyContact.confidence.desc()).limit(req.max_drafts)
    result = await db.execute(query)
    contacts = result.scalars().all()

    if not contacts:
        return {"message": "No pending contacts found for drafting", "drafts_generated": 0}

    # Convert ORM objects to dicts for the drafter
    contact_dicts = [
        {
            "id": c.id,
            "company_name": c.company_name,
            "company_domain": c.company_domain,
            "industry": c.industry or "",
            "contact_name": c.contact_name or "",
            "contact_email": c.contact_email,
            "contact_role": c.contact_role or "",
            "contact_title": c.contact_title or "",
            "fresher_role": c.fresher_role or "Software Engineer",
            "opening_period": c.opening_period or "",
        }
        for c in contacts
    ]

    drafts = await generate_batch_drafts(profile, contact_dicts, max_drafts=req.max_drafts)

    # Save drafts back to the contacts
    saved = 0
    for draft, contact in zip(drafts, contacts):
        contact.cold_email_subject = draft.get("subject", "")
        contact.cold_email_body = draft.get("body", "")
        contact.cold_email_status = "draft_ready"
        saved += 1

    await db.commit()

    return {
        "drafts_generated": saved,
        "drafts": [
            {
                "id": contacts[i].id,
                "company_name": d.get("company_name"),
                "contact_email": d.get("contact_email"),
                "contact_role": d.get("contact_role"),
                "subject": d.get("subject"),
                "body": d.get("body"),
                "follow_up_subject": d.get("follow_up_subject"),
                "follow_up_body": d.get("follow_up_body"),
                "status": "draft_ready",
            }
            for i, d in enumerate(drafts)
        ],
    }


# ──────────────────────────────────────────────────────────────────
# 6. Review & Approve Drafts
# ──────────────────────────────────────────────────────────────────

@router.get("/drafts")
async def list_drafts(
    db: AsyncSession = Depends(get_db),
    status: str = Query(default="draft_ready"),
    limit: int = 20,
):
    """List all cold email drafts with the given status."""
    query = (
        select(CompanyContact)
        .where(CompanyContact.cold_email_status == status)
        .order_by(CompanyContact.updated_at.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    contacts = result.scalars().all()

    return {
        "total": len(contacts),
        "status_filter": status,
        "drafts": [
            {
                "id": c.id,
                "company_name": c.company_name,
                "contact_name": c.contact_name,
                "contact_email": c.contact_email,
                "contact_role": c.contact_role,
                "subject": c.cold_email_subject,
                "body": c.cold_email_body,
                "confidence": c.confidence,
                "source": c.source,
                "status": c.cold_email_status,
            }
            for c in contacts
        ],
    }


@router.post("/drafts/approve")
async def approve_drafts(
    req: ApproveRequest,
    db: AsyncSession = Depends(get_db),
):
    """Approve selected drafts for sending."""
    await db.execute(
        update(CompanyContact)
        .where(CompanyContact.id.in_(req.contact_ids))
        .values(cold_email_status="approved")
    )
    await db.commit()

    if req.send_immediately:
        return await send_approved(SendRequest(contact_ids=req.contact_ids), db)

    return {"approved": len(req.contact_ids), "message": "Drafts approved. Call /send to dispatch."}


# ──────────────────────────────────────────────────────────────────
# 7. Send Approved Emails via Gmail SMTP
# ──────────────────────────────────────────────────────────────────

@router.post("/send")
async def send_approved(
    req: SendRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Send approved cold emails via Gmail SMTP.
    Uses the SMTP settings from .env (SMTP_HOST, SMTP_USER, SMTP_PASSWORD).
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        raise HTTPException(400, "SMTP credentials not configured in .env")

    query = (
        select(CompanyContact)
        .where(
            CompanyContact.id.in_(req.contact_ids),
            CompanyContact.cold_email_status.in_(["approved", "draft_ready"]),
        )
    )
    result = await db.execute(query)
    contacts = result.scalars().all()

    if not contacts:
        return {"message": "No approved drafts to send", "sent": 0}

    sent_count = 0
    errors = []

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)

            for contact in contacts:
                if not contact.cold_email_subject or not contact.cold_email_body:
                    errors.append({
                        "id": contact.id,
                        "email": contact.contact_email,
                        "error": "No draft content"
                    })
                    continue

                try:
                    msg = MIMEMultipart()
                    msg["From"] = settings.SMTP_USER
                    msg["To"] = contact.contact_email
                    msg["Subject"] = contact.cold_email_subject
                    msg.attach(MIMEText(contact.cold_email_body, "plain"))

                    server.sendmail(
                        settings.SMTP_USER,
                        contact.contact_email,
                        msg.as_string()
                    )

                    contact.cold_email_status = "sent"
                    contact.cold_email_sent_at = datetime.utcnow()
                    sent_count += 1
                    logger.info(f"[Email] Sent to {contact.contact_email} ({contact.company_name})")

                except Exception as e:
                    contact.cold_email_status = "bounced"
                    errors.append({
                        "id": contact.id,
                        "email": contact.contact_email,
                        "error": str(e),
                    })

    except Exception as e:
        raise HTTPException(500, f"SMTP connection failed: {e}")

    await db.commit()

    return {
        "sent": sent_count,
        "errors": errors,
        "message": f"Successfully sent {sent_count} emails",
    }


# ──────────────────────────────────────────────────────────────────
# 8. Dashboard / Stats
# ──────────────────────────────────────────────────────────────────

@router.get("/stats")
async def outreach_stats(db: AsyncSession = Depends(get_db)):
    """Get outreach pipeline statistics."""
    total = (await db.execute(select(func.count(CompanyContact.id)))).scalar()
    by_status = {}
    for status in ["pending", "draft_ready", "approved", "sent", "replied", "bounced", "skipped"]:
        count = (await db.execute(
            select(func.count(CompanyContact.id)).where(CompanyContact.cold_email_status == status)
        )).scalar()
        by_status[status] = count

    by_source = {}
    result = await db.execute(
        select(CompanyContact.source, func.count(CompanyContact.id)).group_by(CompanyContact.source)
    )
    for row in result.all():
        by_source[row[0] or "unknown"] = row[1]

    companies_count = (await db.execute(
        select(func.count(func.distinct(CompanyContact.company_name)))
    )).scalar()

    return {
        "total_contacts": total,
        "unique_companies": companies_count,
        "by_status": by_status,
        "by_source": by_source,
    }


# ──────────────────────────────────────────────────────────────────
# 9. LinkedIn Search Links for a Company
# ──────────────────────────────────────────────────────────────────

@router.get("/linkedin-links/{company_name}")
async def get_linkedin_links(company_name: str):
    """Get 1-click LinkedIn search URLs for finding contacts at a company."""
    links = generate_linkedin_search_links(company_name)
    return {
        "company_name": company_name,
        "links": links,
    }


# ──────────────────────────────────────────────────────────────────
# 10. Edit a Draft
# ──────────────────────────────────────────────────────────────────

@router.put("/drafts/{contact_id}")
async def edit_draft(
    contact_id: int,
    subject: Optional[str] = Body(None),
    body: Optional[str] = Body(None),
    db: AsyncSession = Depends(get_db),
):
    """Edit a cold email draft before sending."""
    result = await db.execute(
        select(CompanyContact).where(CompanyContact.id == contact_id)
    )
    contact = result.scalars().first()
    if not contact:
        raise HTTPException(404, "Contact not found")

    if subject is not None:
        contact.cold_email_subject = subject
    if body is not None:
        contact.cold_email_body = body

    contact.cold_email_status = "draft_ready"
    await db.commit()

    return {
        "id": contact.id,
        "company_name": contact.company_name,
        "contact_email": contact.contact_email,
        "subject": contact.cold_email_subject,
        "body": contact.cold_email_body,
        "status": contact.cold_email_status,
    }
