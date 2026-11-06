import logging
from typing import Dict, Any, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.job import Job
from app.models.user_profile import UserProfile
from app.models.match_score import MatchScore
from app.matching.rules import RuleEvaluator
from app.matching.embeddings import EmbeddingVectorizer
from app.ingestion.jd_fetcher import JobDescriptionFetcher

logger = logging.getLogger(__name__)

class MatchingEngine:
    def __init__(self):
        self.vectorizer = EmbeddingVectorizer()
        self.jd_fetcher = JobDescriptionFetcher()

    def evaluate_variant_fit(self, job_text: str, profile: UserProfile) -> Tuple[str, float]:
        """
        Evaluate which of the 4 curated resume variants matches the target job best.
        Returns: (best_variant_key, best_similarity_score)
        """
        variants = profile.curated_variants or {}
        if not variants:
            return "sde", 0.5

        best_variant = "sde"
        highest_sim = -1.0

        for key, var_data in variants.items():
            if isinstance(var_data, dict):
                summary = var_data.get("summary", "")
                skills = " ".join(var_data.get("highlighted_skills", []))
                bullets = " ".join(var_data.get("key_bullet_points", []))
                var_text = f"{key} {summary} {skills} {bullets}"
            else:
                var_text = str(var_data)

            sim = self.vectorizer.compute_similarity(job_text, var_text)
            if sim > highest_sim:
                highest_sim = sim
                best_variant = key

        return best_variant, max(0.0, highest_sim)

    async def score_job(self, db: AsyncSession, job: Job, profile: UserProfile) -> MatchScore:
        """
        Calculate composite fit score (0-100), select best variant, and save/update MatchScore.
        """
        # If job description is short (< 300 chars), attempt deep fetch
        if len((job.description or "").strip()) < 300 and job.url:
            try:
                deep_desc = await self.jd_fetcher.fetch_full_description(job.url)
                if deep_desc and len(deep_desc) > len(job.description or ""):
                    job.description = deep_desc
            except Exception:
                pass

        job_full_text = f"{job.title}\n{job.company}\n{job.location or ''}\n{job.description}"

        # 1. Rule & keyword evaluation
        rule_score, matched_skills, missing_requirements, rule_reasons = RuleEvaluator.evaluate(job, profile)

        # 2. Curated variant selection & semantic similarity
        best_variant, semantic_sim = self.evaluate_variant_fit(job_full_text, profile)

        # 3. Skill overlap ratio
        total_candidate_skills = len(profile.skills or [])
        skill_ratio = (len(matched_skills) / max(1, min(total_candidate_skills, 8))) if matched_skills else 0.0
        skill_ratio = min(1.0, skill_ratio)

        # 4. Composite Score Synthesis (0 - 100)
        # Hard zero if disqualified by rules OR if candidate matched 0 skills in JD
        if rule_score <= 0.0 or not matched_skills:
            final_score = 0.0
        else:
            is_fresher = RuleEvaluator.is_fresher_job(job)
            weighted = (0.45 * semantic_sim) + (0.30 * skill_ratio) + (0.25 * rule_score)
            final_score = round(min(100.0, max(0.0, weighted * 100.0)), 1)
            if is_fresher:
                final_score = min(99.0, final_score + 15.0)

        # 5. Build Human-Readable Markdown Rationale
        variant_title = profile.curated_variants.get(best_variant, {}).get("title", best_variant.upper()) if profile.curated_variants else best_variant.upper()
        
        rationale_lines = [
            f"### Fit Summary: **{final_score}/100**",
            f"- **Selected Resume Profile**: `{variant_title}` ({round(semantic_sim * 100)}% semantic fit)",
            f"- **Core Matched Skills**: {', '.join(f'`{s}`' for s in matched_skills) if matched_skills else '_None explicitly mentioned in JD_'}"
        ]

        if missing_requirements:
            rationale_lines.append(f"- **JD Requirements to Note**: {', '.join(f'`{r}`' for r in missing_requirements)}")

        if rule_reasons:
            rationale_lines.append("\n**Evaluation Notes**:")
            for note in rule_reasons:
                rationale_lines.append(f"- {note}")

        full_rationale = "\n".join(rationale_lines)

        # Check existing match score for idempotency
        stmt = select(MatchScore).where(
            MatchScore.job_id == job.id,
            MatchScore.profile_id == profile.id
        )
        match_score = (await db.execute(stmt)).scalars().first()

        if not match_score:
            match_score = MatchScore(
                job_id=job.id,
                profile_id=profile.id,
                score=final_score,
                semantic_similarity=semantic_sim,
                rule_score=rule_score,
                selected_variant=best_variant,
                rationale=full_rationale,
                matched_skills=matched_skills,
                missing_requirements=missing_requirements
            )
            db.add(match_score)
        else:
            match_score.score = final_score
            match_score.semantic_similarity = semantic_sim
            match_score.rule_score = rule_score
            match_score.selected_variant = best_variant
            match_score.rationale = full_rationale
            match_score.matched_skills = matched_skills
            match_score.missing_requirements = missing_requirements

        await db.commit()
        await db.refresh(match_score)
        return match_score
