import logging
import json
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)

# Gemini client (same pattern as rest of the app)
try:
    from google import genai as google_genai
    _gemini_client = google_genai.Client(api_key=settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None
except Exception:
    _gemini_client = None


GAP_ANALYSIS_PROMPT = """You are an expert technical recruiter and resume coach.

You have been given:
1. A job description (JD) for a software engineering role.
2. A candidate profile with their skills, experience, and projects.

Your task is to do a KEYWORD GAP ANALYSIS: identify what is in the JD that the candidate does NOT have in their profile.

Focus on:
- Technical keywords, tools, frameworks, languages, databases, cloud services
- Methodologies (Agile, CI/CD, TDD, etc.)
- Soft skills explicitly mentioned in the JD
- Resume improvement tips specific to this role

Return a JSON object with EXACTLY this structure (no extra text, just raw JSON):
{
  "missing_technical_keywords": ["keyword1", "keyword2"],
  "missing_soft_skills": ["skill1", "skill2"],
  "resume_tips": [
    "Specific actionable tip referencing the candidate actual projects.",
    "Another specific tip."
  ],
  "overall_gap_summary": "One sentence summary of the biggest gap."
}

Rules:
- missing_technical_keywords: max 12 items. Only include things mentioned in JD that candidate lacks.
- missing_soft_skills: max 5 items.
- resume_tips: 2-4 specific, actionable tips referencing the candidate actual projects/experience.
- If candidate is strong match, return empty arrays for missing fields.

JOB DESCRIPTION:
{job_description}

CANDIDATE PROFILE:
Name: {name}
Skills: {skills}

Work Experience:
{work_history}

Projects:
{projects}

Return ONLY the raw JSON object."""


def _format_work_history(work_history):
    if not work_history:
        return "No work experience listed."
    lines = []
    for w in work_history:
        if isinstance(w, dict):
            lines.append(f"- {w.get('title', '')} @ {w.get('company', '')}")
            for b in w.get("bullets", []):
                lines.append(f"  * {b}")
            if w.get("skills_used"):
                lines.append(f"  Skills: {', '.join(w['skills_used'])}")
    return "\n".join(lines)


def _format_projects(projects):
    if not projects:
        return "No projects listed."
    lines = []
    for p in projects:
        if isinstance(p, dict):
            lines.append(f"- {p.get('name', '')} (Tech: {', '.join(p.get('tech_stack', []))})")
            for b in p.get("bullets", []):
                lines.append(f"  * {b}")
    return "\n".join(lines)


async def analyze_gap(
    job_title: str,
    job_description: str,
    candidate_name: str,
    candidate_skills: list,
    candidate_work_history: list,
    candidate_projects: list,
) -> dict:
    """
    Use Gemini to perform a deep keyword gap analysis between the JD and candidate profile.
    Returns a structured dict with missing_technical_keywords, missing_soft_skills, resume_tips.
    Falls back gracefully if Gemini is unavailable.
    """
    if not _gemini_client:
        logger.warning("Gemini client not available - returning empty gap report.")
        return {
            "missing_technical_keywords": [],
            "missing_soft_skills": [],
            "resume_tips": ["Add your Gemini API key to enable AI-powered gap analysis."],
            "overall_gap_summary": "AI gap analysis unavailable - configure GEMINI_API_KEY in backend/.env"
        }

    prompt = GAP_ANALYSIS_PROMPT.format(
        job_description=f"{job_title}\n\n{job_description[:3000]}",
        name=candidate_name,
        skills=", ".join(candidate_skills[:50]),
        work_history=_format_work_history(candidate_work_history),
        projects=_format_projects(candidate_projects),
    )

    try:
        response = _gemini_client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
        )
        raw = response.text.strip()

        # Strip markdown fences if Gemini wraps in ```json ... ```
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        gap_report = json.loads(raw)
        return {
            "missing_technical_keywords": gap_report.get("missing_technical_keywords", [])[:12],
            "missing_soft_skills": gap_report.get("missing_soft_skills", [])[:5],
            "resume_tips": gap_report.get("resume_tips", [])[:4],
            "overall_gap_summary": gap_report.get("overall_gap_summary", ""),
        }

    except json.JSONDecodeError as e:
        logger.error(f"Gap analyzer: Failed to parse Gemini JSON: {e}")
        return {
            "missing_technical_keywords": [],
            "missing_soft_skills": [],
            "resume_tips": ["Could not parse AI response. Try again."],
            "overall_gap_summary": "Gap analysis parsing failed."
        }
    except Exception as e:
        logger.error(f"Gap analyzer: Gemini call failed: {e}")
        return {
            "missing_technical_keywords": [],
            "missing_soft_skills": [],
            "resume_tips": [f"Gap analysis failed: {str(e)[:100]}"],
            "overall_gap_summary": "Gap analysis failed. Check backend logs."
        }
