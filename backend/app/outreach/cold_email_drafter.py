"""
AI-Powered Cold Email Draft Generator
======================================
Uses Gemini to generate highly personalized cold emails for each
contact, grounded in:
  - The candidate's profile (skills, projects, experience)
  - The target company (industry, role, recent news)
  - The contact's role (HR vs CTO vs Tech Lead — different tones)

Generates drafts that are saved for review before sending.
"""
import logging
import json
from typing import Dict, Any, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────
# Prompt Templates
# ──────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are an expert career coach and cold email strategist for a software engineering fresher in India.
You write concise, high-conversion cold emails that feel genuine, not template-y.

Core principles:
1. NEVER use generic openers like "I hope this email finds you well" or "I'm writing to express my interest"
2. Open with something specific about the company or a mutual connection point
3. Keep the email under 150 words — recruiters skim, not read
4. Include ONE concrete project/skill that maps to their tech stack
5. End with a low-commitment CTA (quick chat, portfolio review, etc.)
6. Match the tone to the recipient: formal for MNC HR, casual-professional for startup CTOs
7. NEVER fabricate facts about the candidate or company
"""

_DRAFT_PROMPT = """Generate a cold email for this job application scenario:

## Candidate Profile
- Name: {name}
- Email: {email}
- Phone: {phone}
- Key Skills: {skills}
- Top Project: {project_name} — {project_desc}
- Experience: {experience_summary}
- GitHub: {github}
- LinkedIn: {linkedin}

## Target Company
- Company: {company_name}
- Industry: {industry}
- Domain: {domain}

## Target Contact
- Contact Name: {contact_name}
- Contact Role: {contact_role}
- Contact Title: {contact_title}
- Contact Email: {contact_email}

## Target Role (if known)
- Fresher Role: {fresher_role}
- Opening Period: {opening_period}

## Instructions
{special_instructions}

Generate a JSON response with:
{{
  "subject": "concise, compelling subject line",
  "body": "the cold email body (plain text, max 150 words)",
  "follow_up_subject": "follow-up email subject (to send 5 days later)",
  "follow_up_body": "follow-up email body (max 80 words, reference the original)"
}}

Return ONLY valid JSON, no markdown fences.
"""


def _get_special_instructions(contact_role: str) -> str:
    """Generate role-specific email writing instructions."""
    role_lower = contact_role.lower()

    if "hr" in role_lower or "recruiter" in role_lower or "talent" in role_lower:
        return (
            "This is an HR / Recruiter. Be professional and structured. "
            "Mention the specific role you're targeting. "
            "Highlight that you're a fresher with strong fundamentals. "
            "Ask if they have any upcoming campus / off-campus drives."
        )
    elif "cto" in role_lower or "ceo" in role_lower or "founder" in role_lower or "leadership" in role_lower:
        return (
            "This is a C-suite / Founder. Be respectful of their time. "
            "Lead with a specific compliment about their product or tech choices. "
            "Keep it under 100 words. Propose to share your portfolio. "
            "DON'T directly ask for a job — ask to connect or learn."
        )
    elif "engineer" in role_lower or "tech lead" in role_lower or "developer" in role_lower:
        return (
            "This is a fellow engineer / tech lead. Be technical and peer-level. "
            "Mention a specific technical challenge from your projects. "
            "Show you've explored their tech stack. "
            "Ask for a quick technical chat or if they know of openings."
        )
    elif "manager" in role_lower:
        return (
            "This is a hiring manager. Balance professionalism with passion. "
            "Mention specific technical skills that match the role. "
            "Ask about the team's current tech challenges."
        )
    else:
        return (
            "This contact's role is unclear. Write a versatile cold email "
            "asking if they can direct you to the right person for fresher hiring. "
            "Be polite and concise."
        )


async def _call_gemini(prompt: str, system_prompt: str = _SYSTEM_PROMPT) -> Optional[str]:
    """Call Gemini API for email generation."""
    try:
        from google import genai

        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7,
                max_output_tokens=1024,
            ),
        )
        return response.text
    except Exception as e:
        logger.error(f"[Gemini] Error generating email draft: {e}")
        return None


def _parse_draft_response(text: str) -> Optional[Dict[str, str]]:
    """Parse Gemini's JSON response into a draft dict."""
    if not text:
        return None

    # Clean markdown fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove ```json and trailing ```
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        data = json.loads(cleaned)
        return {
            "subject": data.get("subject", ""),
            "body": data.get("body", ""),
            "follow_up_subject": data.get("follow_up_subject", ""),
            "follow_up_body": data.get("follow_up_body", ""),
        }
    except json.JSONDecodeError:
        logger.warning(f"[Draft] Failed to parse JSON response: {cleaned[:200]}")
        # Fallback: use the raw text as the email body
        return {
            "subject": "Application from a Passionate Fresher",
            "body": cleaned[:600],
            "follow_up_subject": "",
            "follow_up_body": "",
        }


async def generate_cold_email_draft(
    profile: Dict[str, Any],
    contact: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Generate a personalized cold email draft for a specific contact.

    Args:
        profile: Candidate's profile data (from my_profile.json or DB)
        contact: Enriched contact data from the enrichment engine

    Returns:
        Dict with subject, body, follow_up_subject, follow_up_body, and metadata
    """
    # Extract profile fields
    skills_str = ", ".join((profile.get("skills") or [])[:8])
    projects = profile.get("projects") or profile.get("project_experience") or []
    top_project = projects[0] if projects else {}
    project_name = top_project.get("name") or top_project.get("title", "Software Projects")
    project_desc = top_project.get("description", "full-stack development projects")

    work_history = profile.get("work_history") or profile.get("experience") or []
    exp_summary = ""
    if work_history:
        latest = work_history[0]
        exp_summary = f"{latest.get('title', 'Intern')} at {latest.get('company', 'a tech company')}"
    else:
        exp_summary = "Fresh graduate with strong project portfolio"

    # Build the prompt
    prompt = _DRAFT_PROMPT.format(
        name=profile.get("full_name", ""),
        email=profile.get("email", ""),
        phone=profile.get("phone", ""),
        skills=skills_str,
        project_name=project_name,
        project_desc=project_desc if len(str(project_desc)) < 200 else str(project_desc)[:200],
        experience_summary=exp_summary,
        github=profile.get("github_url", "N/A"),
        linkedin=profile.get("linkedin_url", "N/A"),
        company_name=contact.get("company_name", ""),
        industry=contact.get("industry", "Tech"),
        domain=contact.get("company_domain", ""),
        contact_name=contact.get("contact_name", "[Hiring Team]"),
        contact_role=contact.get("contact_role", ""),
        contact_title=contact.get("contact_title", ""),
        contact_email=contact.get("contact_email", ""),
        fresher_role=contact.get("fresher_role", "Software Engineer / SDE-I"),
        opening_period=contact.get("opening_period", ""),
        special_instructions=_get_special_instructions(contact.get("contact_role", "")),
    )

    raw_response = await _call_gemini(prompt)
    draft = _parse_draft_response(raw_response)

    if draft:
        draft["contact_email"] = contact.get("contact_email", "")
        draft["contact_name"] = contact.get("contact_name", "")
        draft["company_name"] = contact.get("company_name", "")
        draft["contact_role"] = contact.get("contact_role", "")
        draft["status"] = "draft_ready"
    else:
        draft = _generate_fallback_draft(profile, contact)

    return draft


def _generate_fallback_draft(profile: Dict[str, Any], contact: Dict[str, Any]) -> Dict[str, str]:
    """Generate a template-based fallback if Gemini API fails."""
    name = profile.get("full_name", "")
    skills = ", ".join((profile.get("skills") or [])[:4])
    company = contact.get("company_name", "your company")
    role = contact.get("fresher_role", "Software Engineer")

    subject = f"{role} Application — {name}"
    body = f"""Hi {contact.get('contact_name', 'there')},

I'm {name}, a recent graduate passionate about {skills}.

I'm reaching out because I'm actively looking for {role} opportunities, and {company}'s work in {contact.get('industry', 'technology')} genuinely excites me.

Quick highlights:
• Hands-on with {skills}
• Built production-ready projects (portfolio: {profile.get('github_url', 'available on request')})
• {profile.get('work_history', [{}])[0].get('title', 'Strong')} experience with real-world engineering

Would love a quick 10-minute chat or if you could point me to the right person for fresher hiring.

Best regards,
{name}
{profile.get('email', '')} | {profile.get('phone', '')}
LinkedIn: {profile.get('linkedin_url', 'N/A')}"""

    return {
        "subject": subject,
        "body": body,
        "follow_up_subject": f"Following up: {role} — {name}",
        "follow_up_body": f"Hi {contact.get('contact_name', 'there')}, just circling back on my earlier note about the {role} role. Happy to share my portfolio or jump on a quick call. Thanks!",
        "contact_email": contact.get("contact_email", ""),
        "contact_name": contact.get("contact_name", ""),
        "company_name": contact.get("company_name", ""),
        "contact_role": contact.get("contact_role", ""),
        "status": "draft_ready",
    }


async def generate_batch_drafts(
    profile: Dict[str, Any],
    contacts: List[Dict[str, Any]],
    max_drafts: int = 10,
) -> List[Dict[str, Any]]:
    """
    Generate cold email drafts for a batch of contacts.
    Respects daily caps and adds delays between Gemini calls.
    """
    import asyncio
    drafts = []

    for i, contact in enumerate(contacts[:max_drafts]):
        logger.info(f"[Draft] Generating {i+1}/{min(len(contacts), max_drafts)}: "
                     f"{contact.get('company_name')} → {contact.get('contact_email')}")
        draft = await generate_cold_email_draft(profile, contact)
        drafts.append(draft)
        # Rate limit: ~2 seconds between Gemini calls
        if i < len(contacts) - 1:
            await asyncio.sleep(2)

    logger.info(f"[Draft] Generated {len(drafts)} cold email drafts")
    return drafts
