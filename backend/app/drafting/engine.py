import logging
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.job import Job
from app.models.user_profile import UserProfile
from app.models.match_score import MatchScore
from app.models.application_draft import ApplicationDraft
from app.drafting.llm_client import LLMClient
from app.drafting.resume_drafter import ResumeDrafter
from app.drafting.cover_letter_drafter import CoverLetterDrafter
from app.drafting.claim_validator import ClaimValidator
from app.drafting.company_researcher import CompanyResearcher
from app.outreach.referral_generator import ReferralOutreachGenerator
from app.notifications.email_notifier import EmailNotifier

logger = logging.getLogger(__name__)

class DraftingEngine:
    def __init__(self):
        self.llm_client = LLMClient()
        self.resume_drafter = ResumeDrafter()
        self.cover_letter_drafter = CoverLetterDrafter(self.llm_client)

    async def draft_application(
        self,
        db: AsyncSession,
        job: Job,
        profile: UserProfile,
        match_score: MatchScore,
        skip_outreach: bool = False,
    ) -> ApplicationDraft:
        """
        Generates tailored resume variant, cover letter, verifies claims,
        creates outreach kit, and saves to database.

        Args:
            skip_outreach: If True, skip outreach kit generation (for when
                           MAX_OUTREACH_PER_DAY has been reached).
        """
        variant_key = match_score.selected_variant or "sde"

        # 0. Company Research (grounded — only uses JD + Gemini knowledge)
        top_project = {}
        if profile.projects:
            top_project = profile.projects[0] if isinstance(profile.projects[0], dict) else {}

        company_insights = await CompanyResearcher.research(
            company=job.company,
            job_title=job.title,
            job_description=job.description or "",
            candidate_skills=profile.skills or [],
            top_project=top_project,
        )

        # 1. Resume Variant Tailoring
        tailored_resume = self.resume_drafter.draft_resume_variant(
            job=job,
            profile=profile,
            variant_key=variant_key,
            matched_skills=match_score.matched_skills
        )

        # 2. Cover Letter Generation (with company insights)
        cover_letter = await self.cover_letter_drafter.draft_cover_letter(
            job=job,
            profile=profile,
            variant_key=variant_key,
            matched_skills=match_score.matched_skills,
            tailored_resume=tailored_resume,
            company_insights=company_insights,
        )

        # 3. Anti-Hallucination Claim Validation Pass
        claim_status, claim_report = ClaimValidator.validate_claims(
            tailored_resume=tailored_resume,
            cover_letter=cover_letter,
            profile=profile
        )

        # 4. Referral & Cold Outreach Kit (with company insights)
        outreach_kit: Dict[str, Any] = {}
        if not skip_outreach:
            outreach_kit = await ReferralOutreachGenerator.generate_outreach_kit(
                job=job,
                profile=profile,
                tailored_resume=tailored_resume,
                company_insights=company_insights,
            )

        # 5. Save or update ApplicationDraft
        stmt = select(ApplicationDraft).where(
            ApplicationDraft.job_id == job.id,
            ApplicationDraft.match_score_id == match_score.id
        )
        draft = (await db.execute(stmt)).scalars().first()

        if not draft:
            draft = ApplicationDraft(
                job_id=job.id,
                match_score_id=match_score.id,
                resume_variant=tailored_resume,
                cover_letter=cover_letter,
                claim_validation_status=claim_status,
                claim_validation_report=claim_report,
                outreach_kit=outreach_kit,
                company_research=company_insights,
                user_action="pending"
            )
            db.add(draft)
        else:
            draft.resume_variant = tailored_resume
            draft.cover_letter = cover_letter
            draft.claim_validation_status = claim_status
            draft.claim_validation_report = claim_report
            draft.outreach_kit = outreach_kit
            draft.company_research = company_insights

        await db.commit()
        await db.refresh(draft)

        # 6. Send optional email alert if high fit
        if match_score.score >= 70.0:
            await EmailNotifier.send_new_match_alert(job, match_score, draft)

        logger.info(f"Successfully drafted application for Job #{job.id} ({job.title} at {job.company}). Claim status: {claim_status}")
        return draft
