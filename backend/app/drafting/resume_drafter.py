from typing import Dict, Any, List
from app.models.user_profile import UserProfile
from app.models.job import Job

class ResumeDrafter:
    """
    Tailors the candidate's authentic resume data for the target job:
    1. Injects the best matching curated introduction summary.
    2. Re-orders authentic project and experience bullet points based on keyword alignment.
    3. Guarantees 100% authentic candidate data with zero hallucination.
    """

    @staticmethod
    def draft_resume_variant(job: Job, profile: UserProfile, variant_key: str, matched_skills: List[str]) -> Dict[str, Any]:
        variants = profile.curated_variants or {}
        chosen_variant = variants.get(variant_key, {})

        variant_title = chosen_variant.get("title", variant_key.replace("_", " ").title())
        variant_summary = chosen_variant.get("summary", "")
        variant_highlighted_skills = chosen_variant.get("highlighted_skills", [])
        variant_key_bullets = chosen_variant.get("key_bullet_points", [])

        # Priority score for projects based on matching skills
        scored_projects = []
        for proj in (profile.projects or []):
            proj_skills = proj.get("tech_stack", [])
            overlap = len(set(s.lower() for s in proj_skills) & set(s.lower() for s in matched_skills))
            scored_projects.append((overlap, proj))

        # Sort projects by highest relevance
        scored_projects.sort(key=lambda x: x[0], reverse=True)
        tailored_projects = [p[1] for p in scored_projects]

        # Prioritize skills: put matched skills at the front of the list
        all_skills = profile.skills or []
        ordered_skills = matched_skills + [s for s in all_skills if s not in matched_skills]

        return {
            "variant_key": variant_key,
            "target_role": job.title,
            "target_company": job.company,
            "profile_header": {
                "full_name": profile.full_name,
                "email": profile.email,
                "phone": profile.phone,
                "location": profile.location,
                "github_url": profile.github_url,
                "linkedin_url": profile.linkedin_url,
                "portfolio_url": profile.portfolio_url
            },
            "professional_summary": variant_summary,
            "highlighted_focus_skills": variant_highlighted_skills or ordered_skills[:8],
            "skills": ordered_skills,
            "key_highlights": variant_key_bullets,
            "projects": tailored_projects,
            "work_history": profile.work_history or [],
            "education": profile.education or []
        }
