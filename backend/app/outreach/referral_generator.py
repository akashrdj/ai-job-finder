import urllib.parse
from typing import Dict, Any, List, Optional
import httpx
from app.models.job import Job
from app.models.user_profile import UserProfile
from app.config import settings

class ReferralOutreachGenerator:
    @staticmethod
    def _clean_company_name(company: str) -> str:
        # Strip generic suffixes
        return company.replace(" Inc", "").replace(" LLC", "").replace(" Ltd", "").strip()

    @classmethod
    async def generate_outreach_kit(
        cls,
        job: Job,
        profile: UserProfile,
        tailored_resume: Dict[str, Any],
        company_insights: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        company_clean = cls._clean_company_name(job.company)
        encoded_company = urllib.parse.quote(company_clean)
        
        # User's school for alumni search
        school_name = ""
        if profile.education and len(profile.education) > 0:
            school_name = profile.education[0].get("institution", "")
        encoded_school = urllib.parse.quote(school_name) if school_name else ""

        # 1. Targeted LinkedIn Search URLs (1-Click X-Ray links)
        linkedin_links = {
            "search_recruiters": f"https://www.linkedin.com/search/results/people/?keywords=Recruiter%20OR%20%22Talent%20Acquisition%22%20{encoded_company}",
            "search_engineering_managers": f"https://www.linkedin.com/search/results/people/?keywords=%22Engineering%20Manager%22%20OR%20%22Tech%20Lead%22%20{encoded_company}",
        }
        if school_name:
            linkedin_links["search_alumni"] = f"https://www.linkedin.com/search/results/people/?keywords={encoded_school}%20{encoded_company}"

        # 2. Company Domain Email Syntax
        domain_guess = f"{company_clean.lower().replace(' ', '')}.com"
        email_patterns = [
            f"{{first}}.{{last}}@{domain_guess}",
            f"{{first}}@{domain_guess}",
            f"{{first}}{{last}}@{domain_guess}"
        ]

        # 3. Hunter.io domain contacts (optional free API lookup)
        verified_contacts: List[Dict[str, Any]] = []
        if settings.HUNTER_API_KEY:
            try:
                hunter_url = f"https://api.hunter.io/v2/domain-search?domain={domain_guess}&api_key={settings.HUNTER_API_KEY}&limit=5"
                async with httpx.AsyncClient(timeout=6.0) as client:
                    resp = await client.get(hunter_url)
                    if resp.status_code == 200:
                        h_data = resp.json().get("data", {})
                        for email_item in h_data.get("emails", []):
                            verified_contacts.append({
                                "name": f"{email_item.get('first_name', '')} {email_item.get('last_name', '')}".strip(),
                                "position": email_item.get("position", "Recruiter / Team"),
                                "email": email_item.get("value", ""),
                                "confidence": email_item.get("confidence", 80)
                            })
            except Exception:
                pass

        # 4. Extract grounded company context for pitches
        company_hook = ""
        product_mention = ""
        if company_insights and company_insights.get("confidence") in ("high", "medium"):
            if company_insights.get("product_domain"):
                product_mention = company_insights["product_domain"].rstrip(".")
                company_hook = f"Given {company_clean}'s focus on {product_mention}, "
            tps = company_insights.get("talking_points", [])
            if tps:
                company_hook += tps[0].rstrip(".") + ". "

        # 5. Ready-to-copy LinkedIn Connection Pitch (< 300 chars)
        top_project = (tailored_resume.get("projects") or [{}])[0]
        top_project_name = top_project.get("name", "full-stack development")
        
        if company_hook:
            # Grounded pitch — uses company research
            linkedin_pitch = (
                f"Hi [Name], {company_hook}"
                f"Having built {top_project_name} using {', '.join((profile.skills or [])[:3])}, "
                f"I'd love to connect about the {job.title} role. Thanks!"
            )
        else:
            # Fallback — generic but honest
            linkedin_pitch = (
                f"Hi [Name], I noticed your work at {company_clean}. "
                f"I recently saw the {job.title} opening. Having built {top_project_name} "
                f"using {', '.join((profile.skills or [])[:3])}, I'd love to connect and share my portfolio for a quick referral. Thanks!"
            )
        if len(linkedin_pitch) > 300:
            linkedin_pitch = (
                f"Hi [Name], I saw the {job.title} role at {company_clean}. "
                f"With hands-on experience in {', '.join((profile.skills or [])[:2])}, "
                f"I'd love to connect for a potential referral. Thanks!"
            )

        # 6. Ready-to-copy Cold Email Template
        cold_email_subject = f"Application / Referral Request: {job.title} - {profile.full_name}"

        # Build company-specific paragraph if research is available
        company_paragraph = ""
        if product_mention:
            company_paragraph = f"\nI'm particularly drawn to {company_clean}'s work in {product_mention}. "
            if company_insights and company_insights.get("talking_points"):
                company_paragraph += company_insights["talking_points"][0]
            company_paragraph += "\n"

        cold_email_body = f"""Hi [Hiring Manager / Team Lead Name],

I hope this note finds you well. I'm reaching out because I came across the {job.title} opening at {company_clean} and would love to explore opportunities with your team.
{company_paragraph}
A quick summary of why I'm a strong fit:
• Technical Foundation: Hands-on experience with {', '.join((profile.skills or [])[:4])}.
• Project Highlight: Built {top_project.get('name', 'scalable software solutions')} ({top_project.get('description', 'focusing on performance and maintainability')}).
• Work Ethic: Passionate about clean code, rapid prototyping, and delivering high user impact.

I would be grateful for a quick conversation or referral for this position ({job.url}).

Best regards,
{profile.full_name}
{profile.email} | {profile.phone or ''}
GitHub: {profile.github_url or 'N/A'} | LinkedIn: {profile.linkedin_url or 'N/A'}
"""

        return {
            "company_name": company_clean,
            "domain_guess": domain_guess,
            "email_patterns": email_patterns,
            "verified_contacts": verified_contacts,
            "linkedin_search_links": linkedin_links,
            "linkedin_pitch": linkedin_pitch,
            "cold_email_subject": cold_email_subject,
            "cold_email_body": cold_email_body.strip()
        }
