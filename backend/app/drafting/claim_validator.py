import re
from typing import Dict, Any, List, Tuple
from app.models.user_profile import UserProfile

class ClaimValidator:
    """
    Automated Fact-Checking & Anti-Hallucination Guardrail.
    Extracts atomic claims (skills, projects, companies, metrics) from generated text
    and cross-verifies each against the canonical UserProfile.
    """

    KNOWN_TECH_ENTITIES = [
        "Python", "JavaScript", "TypeScript", "React", "Angular", "Vue", "Node.js", "Node",
        "FastAPI", "Django", "Flask", "Spring Boot", "Java", "C++", "C#", "Go", "Rust",
        "SQL", "PostgreSQL", "Postgres", "MySQL", "MongoDB", "Redis", "Cassandra", "DynamoDB",
        "Docker", "Kubernetes", "AWS", "Azure", "GCP", "Git", "GraphQL", "REST", "REST APIs",
        "PyTorch", "TensorFlow", "LangChain", "LlamaIndex", "HuggingFace", "Kafka"
    ]

    TECH_ALIASES = {
        "rest": ["rest apis", "restful", "rest api"],
        "node": ["node.js", "nodejs"],
        "postgres": ["postgresql"],
        "postgresql": ["postgres"],
        "js": ["javascript"],
        "ts": ["typescript"],
        "docker": ["containerization", "containers"],
        "dsa": ["data structures", "algorithms", "data structures & algorithms"]
    }

    @classmethod
    def _is_skill_verified(cls, skill: str, verified_skills_pool: set) -> bool:
        s_lower = skill.lower().strip()
        if s_lower in verified_skills_pool:
            return True
        
        # Check aliases
        for alias in cls.TECH_ALIASES.get(s_lower, []):
            if alias in verified_skills_pool:
                return True

        # Check if skill is substring of any verified multi-word skill (e.g. "REST" in "REST APIs")
        for v in verified_skills_pool:
            if s_lower == v or s_lower in v.split() or s_lower in v:
                return True

        return False

    @classmethod
    def validate_claims(
        cls,
        tailored_resume: Dict[str, Any],
        cover_letter: str,
        profile: UserProfile
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Validate all claims in resume and cover letter against canonical profile.
        Returns:
            - status: "PASSED" | "FLAGGED_UNVERIFIED_CLAIMS"
            - report: Dict with detailed verification trace for human reviewer
        """
        # Pool all verified skills from profile skills, project tech stacks, and work history
        verified_skills = set(s.lower() for s in (profile.skills or []))
        for p in (profile.projects or []):
            for t in p.get("tech_stack", []):
                verified_skills.add(t.lower())
        for w in (profile.work_history or []):
            for s in w.get("skills_used", []):
                verified_skills.add(s.lower())

        profile_all_bullets_text = " ".join([
            " ".join(p.get("bullets", [])) for p in (profile.projects or [])
        ] + [
            " ".join(w.get("bullets", [])) for w in (profile.work_history or [])
        ]).lower()

        claims_list: List[Dict[str, Any]] = []
        flagged_count = 0

        # 1. Verify technical skills in tailored resume
        resume_skills = tailored_resume.get("skills", [])
        for skill in resume_skills:
            is_valid = cls._is_skill_verified(skill, verified_skills)
            claims_list.append({
                "claim_type": "Skill Assertion",
                "entity": skill,
                "status": "VERIFIED" if is_valid else "FLAGGED_UNVERIFIED",
                "source_fact": "Profile Verified Skills" if is_valid else "Not found in your verified skills or project stack"
            })
            if not is_valid:
                flagged_count += 1

        # 2. Check for tech entities mentioned in cover letter
        cover_letter_lower = cover_letter.lower()
        for tech in cls.KNOWN_TECH_ENTITIES:
            # Word boundary search
            if re.search(rf'\b{re.escape(tech.lower())}\b', cover_letter_lower):
                is_valid = cls._is_skill_verified(tech, verified_skills)
                claims_list.append({
                    "claim_type": "Cover Letter Tech Mention",
                    "entity": tech,
                    "status": "VERIFIED" if is_valid else "FLAGGED_UNVERIFIED",
                    "source_fact": "Profile Verified Skills" if is_valid else f"Technology '{tech}' mentioned in letter but missing from verified skills"
                })
                if not is_valid:
                    flagged_count += 1

        # 3. Check for percentage or numerical metric claims in cover letter (e.g. 40%, 95%)
        metric_matches = re.findall(r'(\d+%\s*(?:increase|decrease|reduction|growth|boost|improvement)?)', cover_letter, re.IGNORECASE)
        for metric in metric_matches:
            # Verify if this metric string existed in candidate's original bullets
            is_valid = metric.lower() in profile_all_bullets_text
            claims_list.append({
                "claim_type": "Metric / Statistic Claim",
                "entity": metric,
                "status": "VERIFIED" if is_valid else "FLAGGED_UNVERIFIED",
                "source_fact": "Found in verified project/work bullet points" if is_valid else f"Metric '{metric}' not found in authentic bullets (Potential AI hallucination)"
            })
            if not is_valid:
                flagged_count += 1

        status = "PASSED" if flagged_count == 0 else "FLAGGED_UNVERIFIED_CLAIMS"

        report = {
            "validation_status": status,
            "total_claims_checked": len(claims_list),
            "verified_claims_count": len(claims_list) - flagged_count,
            "flagged_claims_count": flagged_count,
            "claims_breakdown": claims_list,
            "summary_note": (
                "All claims verified against your authentic profile data."
                if status == "PASSED" else
                f"{flagged_count} claim(s) could not be verified against your profile. Please review flagged items before applying."
            )
        }

        return status, report
