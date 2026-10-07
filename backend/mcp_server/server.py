"""
AI Job Finder — Model Context Protocol (MCP) Server
===================================================
Enables Claude Desktop (and any MCP-compliant client) to interact directly
with the AI Job Finder system:
- Query ingested jobs & search roles
- Retrieve RAG profile evidence chunks
- Score job fit & run gap analysis
- Generate tailored application drafts
- Validate claims against ground-truth facts
"""

import sys
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

# Ensure backend root is on sys.path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from mcp.server.fastmcp import FastMCP
from sqlalchemy import select, or_, desc

from app.database import AsyncSessionLocal
from app.models.job import Job
from app.models.user_profile import UserProfile
from app.models.match_score import MatchScore
from app.knowledge.retriever import get_hybrid_retriever
from app.knowledge.chunker import load_profile_from_file
from app.matching.rules import RuleEvaluator
from app.matching.engine import MatchingEngine
from app.drafting.resume_drafter import ResumeDrafter
from app.drafting.cover_letter_drafter import CoverLetterDrafter
from app.drafting.claim_validator import ClaimValidator

# Initialize FastMCP Server
mcp = FastMCP("ai-job-finder", dependencies=["fastapi", "sqlalchemy", "numpy", "faiss-cpu", "google-genai"])
logger = logging.getLogger("mcp_server")


@mcp.tool()
async def search_jobs(query: str, max_results: int = 10) -> str:
    """
    Search ingested jobs in the database by title, company, or description keywords.
    Example: search_jobs("React Bengaluru") or search_jobs("Python Intern")
    """
    async with AsyncSessionLocal() as session:
        search_pattern = f"%{query}%"
        stmt = (
            select(Job)
            .where(
                or_(
                    Job.title.ilike(search_pattern),
                    Job.company.ilike(search_pattern),
                    Job.description.ilike(search_pattern),
                    Job.location.ilike(search_pattern),
                )
            )
            .order_by(desc(Job.id))
            .limit(max_results)
        )
        result = await session.execute(stmt)
        jobs = result.scalars().all()

        if not jobs:
            return f"No jobs found matching '{query}'."

        output = [f"Found {len(jobs)} jobs matching '{query}':\n"]
        for j in jobs:
            output.append(
                f"• [ID: {j.id}] {j.title} @ {j.company}\n"
                f"  Location: {j.location or 'Not specified'} | Source: {j.source}\n"
                f"  Apply: {j.apply_url}\n"
                f"  Snippet: {j.description[:180].replace(chr(10), ' ')}...\n"
            )
        return "\n".join(output)


@mcp.tool()
async def list_recent_jobs(limit: int = 10, min_score: float = 0.0) -> str:
    """
    List recently ingested fresher jobs sorted by ID or fit score.
    """
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Job, MatchScore)
            .outerjoin(MatchScore, Job.id == MatchScore.job_id)
            .order_by(desc(Job.id))
            .limit(limit)
        )
        result = await session.execute(stmt)
        rows = result.all()

        if not rows:
            return "No jobs currently in database. Ingest jobs via backend scraper or API."

        output = [f"Top {len(rows)} recent job opportunities:\n"]
        for job, score in rows:
            fit_val = f"{score.overall_score:.1f}%" if score else "Not scored"
            output.append(
                f"• [ID: {job.id}] {job.title} at {job.company}\n"
                f"  Score: {fit_val} | Location: {job.location or 'N/A'}\n"
                f"  Apply Link: {job.apply_url}\n"
            )
        return "\n".join(output)


@mcp.tool()
async def retrieve_profile_evidence(query: str, top_k: int = 5) -> str:
    """
    Search candidate's profile RAG knowledge base for atomic evidence chunks.
    Uses dense vector similarity (Gemini Embeddings) + sparse keyword RRF.
    Example: retrieve_profile_evidence("telemetry observability OpenTelemetry Grafana")
    """
    retriever = await get_hybrid_retriever()
    results = await retriever.retrieve(query_text=query, top_k=top_k)

    if not results:
        return f"No evidence chunks found for '{query}'."

    output = [f"Retrieved {len(results)} profile evidence chunks for: '{query}':\n"]
    for idx, chunk in enumerate(results, start=1):
        output.append(
            f"{idx}. [{chunk.get('chunk_id')}] (Source: {chunk.get('source_detail')})\n"
            f"   Claim: \"{chunk.get('text')}\"\n"
            f"   Skills: {', '.join(chunk.get('skills', []))}\n"
            f"   Ownership: {chunk.get('ownership_level')} | Quantified Metric: {chunk.get('has_metric')}\n"
            f"   RRF Score: {chunk.get('fused_score', 0.0):.4f}\n"
        )
    return "\n".join(output)


@mcp.tool()
async def score_job_fit(job_id: int) -> str:
    """
    Calculate candidate fit score for a specific job ID using rule filters and skill overlap.
    Returns composite score, matched skills, missing skills, and hard filter breakdown.
    """
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        if not job:
            return f"Job ID {job_id} not found."

        # Fetch profile
        prof_stmt = select(UserProfile).order_by(desc(UserProfile.id)).limit(1)
        prof_res = await session.execute(prof_stmt)
        user_prof = prof_res.scalar_one_or_none()
        if not user_prof:
            profile_dict = load_profile_from_file()
            user_prof = UserProfile(
                full_name=profile_dict.get("full_name", "Akash R Jadhav"),
                email=profile_dict.get("email", "akash@example.com"),
                skills=profile_dict.get("skills", []),
                work_history=profile_dict.get("work_history", []),
                projects=profile_dict.get("projects", []),
                education=profile_dict.get("education", []),
                curated_variants=profile_dict.get("curated_variants", {}),
                preferences=profile_dict.get("preferences", {}),
            )

        # Score job with production MatchingEngine
        engine = MatchingEngine()
        match_score = await engine.score_job(session, job, user_prof)
        rule_score, matched_skills, missing_skills, rule_reasons = RuleEvaluator.evaluate(job, user_prof)

        output = (
            f"=== FIT SCORE REPORT: [ID {job.id}] {job.title} @ {job.company} ===\n"
            f"Overall Match Score: {match_score.overall_score:.1f} / 100\n"
            f"Recommendation: {'APPLY' if match_score.overall_score >= 60 else 'BORDERLINE' if match_score.overall_score >= 40 else 'SKIP'}\n"
            f"Recommended Resume Variant: {match_score.selected_variant.upper() if match_score.selected_variant else 'SDE'}\n\n"
            f"Matched Skills ({len(matched_skills)}): {', '.join(matched_skills)}\n"
            f"Missing Skills ({len(missing_skills)}): {', '.join(missing_skills)}\n"
            f"Rule Outcome: {rule_reasons[0] if rule_reasons else 'Eligible fresher role'}\n"
        )
        return output


@mcp.tool()
async def get_gap_analysis(job_id: int) -> str:
    """
    Analyze skill gaps for a job and provide bridging talking points grounded in real projects.
    """
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        if not job:
            return f"Job ID {job_id} not found."

        prof_stmt = select(UserProfile).order_by(desc(UserProfile.id)).limit(1)
        prof_res = await session.execute(prof_stmt)
        user_prof = prof_res.scalar_one_or_none()
        if not user_prof:
            profile_dict = load_profile_from_file()
            user_prof = UserProfile(
                full_name=profile_dict.get("full_name", "Akash R Jadhav"),
                email=profile_dict.get("email", "akash@example.com"),
                skills=profile_dict.get("skills", []),
                work_history=profile_dict.get("work_history", []),
                projects=profile_dict.get("projects", []),
                education=profile_dict.get("education", []),
                curated_variants=profile_dict.get("curated_variants", {}),
                preferences=profile_dict.get("preferences", {}),
            )

        rule_score, matched, missing, rule_reasons = RuleEvaluator.evaluate(job, user_prof)

        # Retrieve related evidence for the job
        retriever = await get_hybrid_retriever()
        evidence = await retriever.retrieve_evidence_for_job(
            job_title=job.title,
            job_description=job.description,
            required_skills=missing + matched,
            top_k=3
        )

        output = [
            f"=== SKILL GAP ANALYSIS: {job.title} @ {job.company} ===\n",
            f"Skills You Have: {', '.join(matched) if matched else 'None detected in JD'}\n",
            f"Identified Gaps: {', '.join(missing) if missing else 'Zero major gaps detected!'}\n\n",
            "Bridge Strategies (Grounding from your actual projects):\n"
        ]

        for item in evidence:
            output.append(f"• In '{item.get('source_detail')}', you demonstrated:\n  \"{item.get('text')}\"")

        return "\n".join(output)


@mcp.tool()
async def tailor_application(job_id: int) -> str:
    """
    Generate a tailored resume recommendation and fact-grounded cover letter draft.
    Uses RAG evidence retrieval and anti-hallucination validation.
    """
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        if not job:
            return f"Job ID {job_id} not found."

        profile_dict = load_profile_from_file()

        # 1. Select optimal variant and draft resume bullets
        resume_drafter = ResumeDrafter()
        best_variant, variant_data = resume_drafter.select_best_variant(
            job_title=job.title,
            job_description=job.description,
            profile=profile_dict
        )

        # 2. Retrieve RAG evidence
        retriever = await get_hybrid_retriever()
        evidence_chunks = await retriever.retrieve_evidence_for_job(
            job_title=job.title,
            job_description=job.description,
            top_k=4
        )

        # 3. Draft cover letter
        cl_drafter = CoverLetterDrafter()
        cover_letter = await cl_drafter.generate_cover_letter(
            job_title=job.title,
            company=job.company,
            job_description=job.description,
            profile=profile_dict,
            variant_name=best_variant,
            variant_data=variant_data
        )

        # 4. Validate claims
        val_status, val_report = ClaimValidator.validate_claims(
            cover_letter=cover_letter,
            profile=profile_dict
        )

        output = (
            f"=== TAILORED APPLICATION DRAFT FOR [ID {job.id}] {job.title} @ {job.company} ===\n\n"
            f"Recommended Resume Variant: {best_variant.upper()} ({variant_data.get('title')})\n"
            f"Claim Verification Status: {val_status}\n\n"
            f"--- RAG Supporting Evidence Chunks ---\n"
            + "\n".join(f"• [{c.get('chunk_id')}] {c.get('text')}" for c in evidence_chunks)
            + f"\n\n--- Tailored Cover Letter Draft ---\n\n{cover_letter}\n"
        )
        return output


@mcp.tool()
async def verify_claim(claim_text: str) -> str:
    """
    Verify whether a resume claim or cover letter bullet is authentically supported by candidate's profile.
    Example: verify_claim("Engineered low-latency ring buffer using OpenTelemetry in Java")
    """
    profile_dict = load_profile_from_file()
    retriever = await get_hybrid_retriever()
    evidence = await retriever.retrieve(query_text=claim_text, top_k=3)

    is_supported = len(evidence) > 0 and evidence[0].get("fused_score", 0) > 0.015

    output = [
        f"Claim Under Review: \"{claim_text}\"\n",
        f"Verdict: {'AUTHENTICALLY SUPPORTED' if is_supported else 'NEEDS HUMAN REVIEW / UNSUPPORTED'}\n\n",
        "Closest Evidence In Profile Knowledge Base:\n"
    ]
    for idx, e in enumerate(evidence, start=1):
        output.append(
            f"{idx}. [{e.get('chunk_id')}] (Source: {e.get('source_detail')})\n"
            f"   \"{e.get('text')}\"\n"
            f"   Skills: {', '.join(e.get('skills', []))} | Ownership: {e.get('ownership_level')}\n"
        )
    return "\n".join(output)


# --- MCP RESOURCES ---

@mcp.resource("profile://evidence")
async def get_profile_evidence_resource() -> str:
    """Read-only resource returning all atomic profile evidence items."""
    retriever = await get_hybrid_retriever()
    chunks = retriever.vector_store.chunks
    return json.dumps([
        {
            "chunk_id": c.get("chunk_id"),
            "text": c.get("text"),
            "source": c.get("source_detail"),
            "skills": c.get("skills", []),
            "ownership": c.get("ownership_level"),
            "has_metric": c.get("has_metric")
        }
        for c in chunks
    ], indent=2)


if __name__ == "__main__":
    mcp.run()
