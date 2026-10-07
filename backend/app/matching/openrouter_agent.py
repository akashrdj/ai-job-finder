import json
import logging
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


@dataclass
class FresherInspectionResult:
    min_years_experience: float
    max_years_experience: Optional[float]
    is_fresher_eligible: bool
    batch_eligibility: List[str]
    verdict: str  # "ELIGIBLE_FRESHER" or "DISQUALIFIED"
    rejection_reason: Optional[str]
    confidence: float
    provider_used: str


class FresherInspectionAgent:
    """
    AI Agent that parses job descriptions using OpenRouter's free LLMs
    (e.g., Llama 3.2 1B/3B, Qwen 2.5, or Gemini) to definitively determine:
    1. Exact minimum years of experience required.
    2. True fresher eligibility (0 YOE / college grad / trainee).
    3. Eligible graduating batches (e.g. 2024, 2025, 2026).
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.OPENROUTER_API_KEY
        self.model = model or settings.OPENROUTER_MODEL

    async def inspect_job_description(self, title: str, description: str, company: str = "") -> FresherInspectionResult:
        """
        Deeply inspects the job description to verify 0-YOE fresher eligibility.
        Tries OpenRouter free model first; falls back to Gemini or rule analysis.
        """
        prompt = f"""You are a strict ATS Qualification Evaluator for Freshers (0 Years of Experience, 2025-2026 batch graduates).
Analyze the following job description and determine whether a PURE FRESHER with 0 YEARS of industry experience is eligible.

Rules:
1. If the job explicitly requires ANY prior full-time experience (e.g., "1+ years", "2-3 years", "minimum 1 year", "prior experience required"), then min_years_experience is > 0, and is_fresher_eligible is FALSE.
2. If the job accepts 0 years of experience (e.g., "0-1 years", "0-2 years", "freshers can apply", "Graduate Engineer Trainee", "Software Engineer Program", "Campus Hire", "Trainee", "Intern", "no prior experience required"), then min_years_experience is 0, and is_fresher_eligible is TRUE.
3. If no experience number is stated but title is explicitly an entry role ("GET", "Intern", "Graduate Trainee", "New Analyst"), is_fresher_eligible is TRUE with min_years_experience = 0.
4. If title is generic (e.g. "Software Engineer") and requires 2+ or 3+ years anywhere in requirements, is_fresher_eligible is FALSE.

Job Title: {title}
Company: {company}
Job Description:
{description[:3500]}

Respond ONLY with valid JSON in this exact structure:
{{
  "min_years_experience": 0,
  "max_years_experience": 1,
  "is_fresher_eligible": true,
  "batch_eligibility": ["2024", "2025", "2026"],
  "verdict": "ELIGIBLE_FRESHER",
  "rejection_reason": null,
  "confidence": 0.95
}}
If not eligible, set "is_fresher_eligible": false, "verdict": "DISQUALIFIED", and provide the concise "rejection_reason" (e.g. "Requires 2+ years of experience").
"""

        # 1. Try OpenRouter if API key is present
        if self.api_key:
            try:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/akashrdj/ai-job-finder",
                    "X-Title": "AI Job Finder Fresher Agent",
                }
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You are a precise JSON-only recruiter assistant."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 300,
                }
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(OPENROUTER_ENDPOINT, json=payload, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_content = data["choices"][0]["message"]["content"]
                        parsed = self._extract_json(raw_content)
                        if parsed:
                            return FresherInspectionResult(
                                min_years_experience=float(parsed.get("min_years_experience", 0)),
                                max_years_experience=parsed.get("max_years_experience"),
                                is_fresher_eligible=bool(parsed.get("is_fresher_eligible", False)),
                                batch_eligibility=parsed.get("batch_eligibility", []),
                                verdict=parsed.get("verdict", "ELIGIBLE_FRESHER"),
                                rejection_reason=parsed.get("rejection_reason"),
                                confidence=float(parsed.get("confidence", 0.9)),
                                provider_used=f"openrouter/{self.model}"
                            )
            except Exception as e:
                logger.warning(f"OpenRouter agent inspection error: {e}. Falling back.")

        # 2. Fallback to Gemini if configured
        if settings.GEMINI_API_KEY:
            try:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=settings.GEMINI_API_KEY)
                response = client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        response_mime_type="application/json"
                    )
                )
                if response.text:
                    parsed = self._extract_json(response.text)
                    if parsed:
                        return FresherInspectionResult(
                            min_years_experience=float(parsed.get("min_years_experience", 0)),
                            max_years_experience=parsed.get("max_years_experience"),
                            is_fresher_eligible=bool(parsed.get("is_fresher_eligible", False)),
                            batch_eligibility=parsed.get("batch_eligibility", []),
                            verdict=parsed.get("verdict", "ELIGIBLE_FRESHER"),
                            rejection_reason=parsed.get("rejection_reason"),
                            confidence=float(parsed.get("confidence", 0.95)),
                            provider_used=f"gemini/{settings.GEMINI_MODEL}"
                        )
            except Exception as e:
                logger.warning(f"Gemini inspection agent error: {e}. Falling back to rule parser.")

        # 3. Rule-based heuristic fallback
        return self._heuristic_inspection(title, description)

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract and parse JSON safely from LLM output."""
        try:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception:
            pass
        return None

    def _heuristic_inspection(self, title: str, description: str) -> FresherInspectionResult:
        """Deterministic rule-based fallback when LLMs are offline."""
        from app.matching.rules import extract_experience_requirements, FRESHER_JD_SIGNALS, NON_FRESHER_PHRASES, FRESHER_BONUS_TITLES

        t_lower = title.lower()
        d_lower = description.lower()

        extracted = extract_experience_requirements(description)
        has_fresher_title = any(ft in t_lower for ft in FRESHER_BONUS_TITLES)
        has_fresher_signal = any(sig in d_lower for sig in FRESHER_JD_SIGNALS)

        if extracted:
            min_exp = min(extracted)
            if min_exp > 0 and not has_fresher_signal:
                return FresherInspectionResult(
                    min_years_experience=float(min_exp),
                    max_years_experience=float(max(extracted)),
                    is_fresher_eligible=False,
                    batch_eligibility=[],
                    verdict="DISQUALIFIED",
                    rejection_reason=f"Requires {min_exp}+ years of experience",
                    confidence=0.85,
                    provider_used="heuristic_rules"
                )
            if 0 in extracted:
                return FresherInspectionResult(
                    min_years_experience=0.0,
                    max_years_experience=float(max(extracted)),
                    is_fresher_eligible=True,
                    batch_eligibility=["2024", "2025", "2026"],
                    verdict="ELIGIBLE_FRESHER",
                    rejection_reason=None,
                    confidence=0.90,
                    provider_used="heuristic_rules"
                )

        for phrase in NON_FRESHER_PHRASES:
            if phrase in d_lower and not has_fresher_signal and not has_fresher_title:
                return FresherInspectionResult(
                    min_years_experience=1.0,
                    max_years_experience=None,
                    is_fresher_eligible=False,
                    batch_eligibility=[],
                    verdict="DISQUALIFIED",
                    rejection_reason=f"Requires prior experience ({phrase})",
                    confidence=0.80,
                    provider_used="heuristic_rules"
                )

        is_eligible = has_fresher_title or has_fresher_signal or len(description.strip()) < 300
        return FresherInspectionResult(
            min_years_experience=0.0 if is_eligible else 1.0,
            max_years_experience=None,
            is_fresher_eligible=is_eligible,
            batch_eligibility=["2025", "2026"] if is_eligible else [],
            verdict="ELIGIBLE_FRESHER" if is_eligible else "DISQUALIFIED",
            rejection_reason=None if is_eligible else "Experience required / non-fresher role",
            confidence=0.75,
            provider_used="heuristic_rules"
        )
