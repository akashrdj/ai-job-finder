from typing import Dict, Any, List, Optional
from jinja2 import Template
from app.models.user_profile import UserProfile
from app.models.job import Job
from app.drafting.llm_client import LLMClient

DEFAULT_COVER_LETTER_TEMPLATE = """Dear Hiring Team at {{ company }},

I am writing to express my enthusiasm for the {{ role }} position. With a strong foundation in {{ top_skills }}, I am excited about the opportunity to contribute to {{ company }}'s engineering initiatives.

{{ summary }}

{% if company_insight %}{{ company_insight }}

{% endif %}In my recent project work, I {{ top_project_bullet }} Leveraging {{ top_project_tech }}, I focused on writing clean, maintainable code and solving challenging technical problems. {% if talking_point %}{{ talking_point }}{% endif %}

I am eager to bring my dedication, fast learning curve, and technical skills to the team at {{ company }}. Thank you for your time and consideration, and I look forward to the possibility of discussing how my background meets your needs.

Sincerely,
{{ candidate_name }}
{{ email }} | {{ phone }}
"""

class CoverLetterDrafter:
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def draft_cover_letter(
        self,
        job: Job,
        profile: UserProfile,
        variant_key: str,
        matched_skills: List[str],
        tailored_resume: Dict[str, Any],
        company_insights: Optional[Dict[str, Any]] = None,
    ) -> str:
        variants = profile.curated_variants or {}
        chosen_variant = variants.get(variant_key, {})
        template_str = chosen_variant.get("cover_letter_template") or DEFAULT_COVER_LETTER_TEMPLATE

        # Prepare context variables
        top_skills_str = ", ".join(matched_skills[:4]) if matched_skills else ", ".join((profile.skills or [])[:4])
        
        top_project = (tailored_resume.get("projects") or [{}])[0]
        top_project_bullet = ""
        if top_project.get("bullets"):
            top_project_bullet = top_project["bullets"][0]
        elif top_project.get("description"):
            top_project_bullet = f"developed {top_project['name']}, {top_project['description']}."
        else:
            top_project_bullet = "built full-stack applications emphasizing reliable performance and scalability."

        top_project_tech = ", ".join(top_project.get("tech_stack", [])) or "modern development best practices"

        # Extract grounded company insight and talking point
        company_insight = ""
        talking_point = ""
        if company_insights and company_insights.get("confidence") in ("high", "medium"):
            # Product domain sentence
            if company_insights.get("product_domain"):
                company_insight = (
                    f"I am particularly drawn to {job.company}'s work in "
                    f"{company_insights['product_domain'].rstrip('.')}."
                )
            # Recent news (only if high confidence)
            if company_insights.get("recent_news") and company_insights.get("confidence") == "high":
                company_insight += f" {company_insights['recent_news'].rstrip('.')}."

            # Best talking point
            tps = company_insights.get("talking_points", [])
            if tps:
                talking_point = tps[0]

        context = {
            "company": job.company,
            "role": job.title,
            "location": job.location or "your team",
            "candidate_name": profile.full_name,
            "email": profile.email,
            "phone": profile.phone or "",
            "top_skills": top_skills_str,
            "summary": chosen_variant.get("summary", ""),
            "top_project_bullet": top_project_bullet,
            "top_project_tech": top_project_tech,
            "company_insight": company_insight,
            "talking_point": talking_point,
        }

        try:
            rendered = Template(template_str).render(**context)
            return rendered.strip()
        except Exception:
            return Template(DEFAULT_COVER_LETTER_TEMPLATE).render(**context).strip()
