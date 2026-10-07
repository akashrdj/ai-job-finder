"""
Company Research Module — Lightweight, grounded company intelligence for outreach.

Only runs for the daily shortlist (top-N jobs). Searches for recent company news,
engineering blog posts, product launches, and funding rounds to feed into cover
letters and cold emails. Falls back gracefully to JD-derived tech stack if
nothing substantive is found.

Design principle: GROUNDED ONLY — never fabricate insights. If the search
returns nothing, return an empty insights dict rather than hallucinating.
"""

import logging
import json
from typing import Dict, Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)

def _get_gemini_client():
    """Get or initialize Gemini client dynamically."""
    if not settings.GEMINI_API_KEY:
        return None
    try:
        from google import genai as google_genai
        return google_genai.Client(api_key=settings.GEMINI_API_KEY)
    except Exception as e:
        logger.warning(f"Failed to initialize Gemini client: {e}")
        return None


COMPANY_RESEARCH_PROMPT = """You are a job research assistant. Given a company name, a job title, and the job description,
extract ONLY factual, verifiable information about the company. Do NOT make up or hallucinate information.

Your task:
1. From the JD itself, extract the company's tech stack, product domain, and team description.
2. Based on widely-known public information, note any recent news (funding rounds, product launches, acquisitions) — but ONLY if you are highly confident it is accurate. If unsure, omit it.
3. Identify 1-2 specific talking points that connect the candidate's background to this company's work.

Company: {company}
Job Title: {title}
Job Description (first 2000 chars):
{description}

Candidate Background (for talking point matching):
- Skills: {candidate_skills}
- Top Project: {top_project}

Return ONLY a raw JSON object with this exact structure (no markdown, no extra text):
{{
  "tech_stack_from_jd": ["tech1", "tech2"],
  "product_domain": "One sentence about what the company builds",
  "recent_news": "One sentence of recent verifiable news, or empty string if unsure",
  "talking_points": [
    "Specific point connecting candidate's experience to this company's work",
    "Another specific point"
  ],
  "confidence": "high" or "medium" or "low"
}}"""


class CompanyResearcher:
    """
    Lightweight company research using Gemini for JD analysis + knowledge.
    Falls back to empty insights if Gemini is unavailable.
    """

    @staticmethod
    async def research(
        company: str,
        job_title: str,
        job_description: str,
        candidate_skills: list,
        top_project: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Research a company for outreach personalization.

        Returns a dict with:
        - tech_stack_from_jd: list of technologies mentioned in JD
        - product_domain: what the company builds
        - recent_news: recent verifiable news (or empty)
        - talking_points: connection points between candidate and company
        - confidence: how confident we are in the research
        """
        client = _get_gemini_client()
        if not client:
            logger.info(f"Gemini unavailable — falling back to JD-only research for {company}")
            return CompanyResearcher._fallback_from_jd(job_description)

        # Format candidate context
        skills_str = ", ".join(candidate_skills[:15])
        project_str = (
            f"{top_project.get('name', 'N/A')} — {top_project.get('description', 'N/A')} "
            f"(Tech: {', '.join(top_project.get('tech_stack', []))})"
            if top_project
            else "No projects listed"
        )

        prompt = COMPANY_RESEARCH_PROMPT.format(
            company=company,
            title=job_title,
            description=job_description[:2000],
            candidate_skills=skills_str,
            top_project=project_str,
        )

        try:
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
            )
            raw = response.text.strip()

            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            insights = json.loads(raw)

            # Validate structure
            result = {
                "tech_stack_from_jd": insights.get("tech_stack_from_jd", [])[:10],
                "product_domain": insights.get("product_domain", ""),
                "recent_news": insights.get("recent_news", ""),
                "talking_points": insights.get("talking_points", [])[:3],
                "confidence": insights.get("confidence", "low"),
                "source": "gemini_research",
            }

            logger.info(
                f"Company research for '{company}': "
                f"{len(result['talking_points'])} talking points, "
                f"confidence={result['confidence']}"
            )
            return result

        except json.JSONDecodeError as e:
            logger.warning(f"Company research JSON parse error for '{company}': {e}")
            return CompanyResearcher._fallback_from_jd(job_description)
        except Exception as e:
            logger.warning(f"Company research failed for '{company}': {e}")
            return CompanyResearcher._fallback_from_jd(job_description)

    @staticmethod
    def _fallback_from_jd(description: str) -> Dict[str, Any]:
        """Extract basic tech stack from JD text as fallback."""
        import re

        # Quick keyword extraction from JD
        tech_keywords = [
            "Python", "Java", "JavaScript", "TypeScript", "React", "Node.js",
            "Go", "Rust", "C++", "Kotlin", "Swift", "Ruby",
            "AWS", "GCP", "Azure", "Docker", "Kubernetes",
            "PostgreSQL", "MongoDB", "Redis", "MySQL", "Kafka",
            "FastAPI", "Django", "Spring Boot", "Flask",
            "PyTorch", "TensorFlow", "Machine Learning",
        ]
        desc_lower = description.lower()
        found_tech = [t for t in tech_keywords if t.lower() in desc_lower]

        return {
            "tech_stack_from_jd": found_tech[:8],
            "product_domain": "",
            "recent_news": "",
            "talking_points": [],
            "confidence": "jd_only",
            "source": "jd_fallback",
        }
