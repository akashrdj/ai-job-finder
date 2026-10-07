"""
Atomic Evidence Chunker for Profile Knowledge Base
===================================================
Converts structured user profile data into atomic, verifiable evidence chunks.
Each chunk represents a single authentic claim or accomplishment with its
source, relevant skills, ownership level, and metrics.
"""

from __future__ import annotations

import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Action verbs mapped to ownership level
_LED_VERBS = {"led", "headed", "architected", "founded", "directed", "pioneered", "spearheaded"}
_BUILT_VERBS = {
    "built", "designed", "engineered", "developed", "deployed", "implemented",
    "created", "automated", "optimized", "integrated", "produced", "authored"
}
_CONTRIBUTED_VERBS = {"contributed", "assisted", "supported", "collaborated", "partnered", "participated"}

# Metric regex: finds percentages, multipliers, counts with units, scores
_METRIC_REGEX = re.compile(
    r"(\b\d+(\.\d+)?%|\b\d+(\.\d+)?[xX]\b|\b\d+\+?\s*(users|clients|tables|sources|languages|containers|signals|semesters|hours|ms|seconds|min|days|variants|table|cgpa|grade)\b|\b\d+\.\d+\s*/\s*\d+(\.\d+)?\b|\brank\s*\d+\b)",
    re.IGNORECASE
)


class EvidenceChunk(BaseModel):
    chunk_id: str
    text: str
    source: str  # "work_history" | "projects" | "education" | "certifications" | "skills"
    source_detail: str
    skills: List[str] = Field(default_factory=list)
    ownership_level: str = "used"  # "led" | "built" | "contributed" | "used" | "studied"
    has_metric: bool = False
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


def detect_ownership(text: str) -> str:
    """Classify the ownership level demonstrated in a bullet text."""
    lower = text.lower()
    first_words = re.findall(r"\b[a-z]+\b", lower)[:6]

    for word in first_words:
        if word in _LED_VERBS:
            return "led"
    for word in first_words:
        if word in _BUILT_VERBS:
            return "built"
    for word in first_words:
        if word in _CONTRIBUTED_VERBS:
            return "contributed"

    # Secondary check across entire bullet
    for word in _LED_VERBS:
        if re.search(rf"\b{word}\b", lower):
            return "led"
    for word in _BUILT_VERBS:
        if re.search(rf"\b{word}\b", lower):
            return "built"
    for word in _CONTRIBUTED_VERBS:
        if re.search(rf"\b{word}\b", lower):
            return "contributed"

    return "used"


def detect_metrics(text: str) -> bool:
    """Determine if the text contains a quantified outcome or metric."""
    return bool(_METRIC_REGEX.search(text))


def extract_matched_skills(text: str, candidate_skills: List[str]) -> List[str]:
    """Find candidate skills that explicitly appear in the bullet text."""
    found: List[str] = []
    text_lower = text.lower()
    for skill in candidate_skills:
        pattern = rf"(?<!\w){re.escape(skill.lower())}(?!\w)"
        if re.search(pattern, text_lower):
            if skill not in found:
                found.append(skill)
    return found


def _slugify(val: str) -> str:
    """Create a URL/id friendly slug."""
    clean = re.sub(r"[^\w\s-]", "", val).strip().lower()
    return re.sub(r"[-\s]+", "_", clean)[:30]


class ProfileChunker:
    """Decomposes a candidate profile into atomic, indexable evidence chunks."""

    def __init__(self, profile_data: Optional[Dict[str, Any]] = None):
        self.profile = profile_data or {}
        self.master_skills: List[str] = self.profile.get("skills", [])

    def chunk(self, profile: Optional[Dict[str, Any]] = None) -> List[EvidenceChunk]:
        """Convert the entire profile into an ordered list of EvidenceChunks."""
        if profile:
            self.profile = profile
            self.master_skills = profile.get("skills", [])

        chunks: List[EvidenceChunk] = []

        chunks.extend(self._chunk_work_history())
        chunks.extend(self._chunk_projects())
        chunks.extend(self._chunk_education())
        chunks.extend(self._chunk_certifications())
        chunks.extend(self._chunk_skills_summary())

        logger.info(f"Chunked profile into {len(chunks)} atomic evidence items.")
        return chunks

    def _chunk_work_history(self) -> List[EvidenceChunk]:
        chunks: List[EvidenceChunk] = []
        work_list = self.profile.get("work_history", [])

        for w_idx, work in enumerate(work_list, start=1):
            company = work.get("company", f"Company_{w_idx}")
            title = work.get("title", "Software Engineer")
            company_slug = _slugify(company)
            source_detail = f"{company} | {title}"
            explicit_skills = work.get("skills_used", [])

            bullets = work.get("bullets", [])
            for b_idx, bullet in enumerate(bullets, start=1):
                clean_bullet = bullet.strip()
                if not clean_bullet:
                    continue

                matched = list(dict.fromkeys(
                    explicit_skills + extract_matched_skills(clean_bullet, self.master_skills)
                ))

                chunks.append(
                    EvidenceChunk(
                        chunk_id=f"work_{company_slug}_bullet_{b_idx}",
                        text=clean_bullet,
                        source="work_history",
                        source_detail=source_detail,
                        skills=matched,
                        ownership_level=detect_ownership(clean_bullet),
                        has_metric=detect_metrics(clean_bullet),
                        metadata={
                            "company": company,
                            "title": title,
                            "start_date": work.get("start_date", ""),
                            "end_date": work.get("end_date", ""),
                            "location": work.get("location", ""),
                        }
                    )
                )

        return chunks

    def _chunk_projects(self) -> List[EvidenceChunk]:
        chunks: List[EvidenceChunk] = []
        projects = self.profile.get("projects", [])

        for p_idx, proj in enumerate(projects, start=1):
            name = proj.get("name", f"Project_{p_idx}")
            role = proj.get("role", "Creator")
            tech_stack = proj.get("tech_stack", [])
            proj_slug = _slugify(name)
            source_detail = f"Project: {name} ({role})"

            # Project overview chunk if description is present
            desc = proj.get("description", "").strip()
            if desc:
                matched_desc_skills = list(dict.fromkeys(
                    tech_stack + extract_matched_skills(desc, self.master_skills)
                ))
                chunks.append(
                    EvidenceChunk(
                        chunk_id=f"project_{proj_slug}_overview",
                        text=desc,
                        source="projects",
                        source_detail=source_detail,
                        skills=matched_desc_skills,
                        ownership_level="built",
                        has_metric=detect_metrics(desc),
                        metadata={
                            "project_name": name,
                            "role": role,
                            "tech_stack": tech_stack,
                            "github_url": proj.get("github_url", ""),
                            "is_overview": True,
                        }
                    )
                )

            # Project bullet points
            bullets = proj.get("bullets", [])
            for b_idx, bullet in enumerate(bullets, start=1):
                clean_bullet = bullet.strip()
                if not clean_bullet:
                    continue

                matched = list(dict.fromkeys(
                    tech_stack + extract_matched_skills(clean_bullet, self.master_skills)
                ))

                chunks.append(
                    EvidenceChunk(
                        chunk_id=f"project_{proj_slug}_bullet_{b_idx}",
                        text=clean_bullet,
                        source="projects",
                        source_detail=source_detail,
                        skills=matched,
                        ownership_level=detect_ownership(clean_bullet),
                        has_metric=detect_metrics(clean_bullet),
                        metadata={
                            "project_name": name,
                            "role": role,
                            "tech_stack": tech_stack,
                            "github_url": proj.get("github_url", ""),
                            "bullet_index": b_idx,
                        }
                    )
                )

        return chunks

    def _chunk_education(self) -> List[EvidenceChunk]:
        chunks: List[EvidenceChunk] = []
        education_list = self.profile.get("education", [])

        for e_idx, edu in enumerate(education_list, start=1):
            institution = edu.get("institution", "")
            degree = edu.get("degree", "")
            field = edu.get("field_of_study", "")
            year = edu.get("graduation_year", "")
            grade = edu.get("cgpa_or_grade", "")

            if not institution:
                continue

            parts = [institution]
            if degree:
                parts.append(degree)
            if field:
                parts.append(f"in {field}")
            if grade:
                parts.append(f"— Grade/CGPA: {grade}")
            if year:
                parts.append(f"({year})")

            text = " ".join(parts).strip()
            slug = _slugify(institution)

            chunks.append(
                EvidenceChunk(
                    chunk_id=f"education_{slug}_{e_idx}",
                    text=text,
                    source="education",
                    source_detail=institution,
                    skills=["Data Structures & Algorithms", "Computer Science"],
                    ownership_level="studied",
                    has_metric=bool(grade),
                    metadata={
                        "institution": institution,
                        "degree": degree,
                        "field_of_study": field,
                        "graduation_year": year,
                        "cgpa_or_grade": grade,
                    }
                )
            )

        return chunks

    def _chunk_certifications(self) -> List[EvidenceChunk]:
        chunks: List[EvidenceChunk] = []
        certs = self.profile.get("certifications", [])

        for c_idx, cert in enumerate(certs, start=1):
            clean_cert = cert.strip()
            if not clean_cert:
                continue

            matched = extract_matched_skills(clean_cert, self.master_skills)
            slug = _slugify(clean_cert[:20])

            chunks.append(
                EvidenceChunk(
                    chunk_id=f"cert_{slug}_{c_idx}",
                    text=clean_cert,
                    source="certifications",
                    source_detail="Professional Certifications & Honors",
                    skills=matched,
                    ownership_level="studied",
                    has_metric=False,
                    metadata={"certification": clean_cert}
                )
            )

        return chunks

    def _chunk_skills_summary(self) -> List[EvidenceChunk]:
        """Produce high-level synthesized capability chunks for broad retrieval."""
        chunks: List[EvidenceChunk] = []
        if not self.master_skills:
            return chunks

        # Group skills into logical categories
        categories = {
            "backend_cloud": [s for s in self.master_skills if s in {
                "Python", "FastAPI", "Java", "Docker", "Kubernetes", "AWS Lambda",
                "Amazon EventBridge", "Amazon ECR", "Oracle Cloud Infrastructure", "OCI",
                "REST APIs", "MySQL", "SQLite", "MongoDB", "JUnit", "pytest"
            }],
            "observability_systems": [s for s in self.master_skills if s in {
                "OpenTelemetry", "Prometheus", "Grafana", "Loki", "Scapy",
                "TCP/IP protocol analysis", "packet crafting (ARP, Ethernet/MAC)", "System Design"
            }],
            "ai_ml_data": [s for s in self.master_skills if s in {
                "PyTorch", "TensorFlow", "Keras", "Scikit-learn", "Pandas", "NumPy",
                "Machine Learning", "Deep Learning", "Computer Vision", "Multimodal AI",
                "Federated Learning", "LLMs", "Gemini API", "ONNX"
            }],
            "frontend_fullstack": [s for s in self.master_skills if s in {
                "React", "React.js", "Node.js", "Express.js", "HTML5", "CSS3",
                "JavaScript", "Streamlit"
            }]
        }

        full_name = self.profile.get("full_name", "Candidate")
        for cat_name, skills in categories.items():
            if skills:
                text = f"{full_name} demonstrated core competencies in: {', '.join(skills)}."
                chunks.append(
                    EvidenceChunk(
                        chunk_id=f"skills_category_{cat_name}",
                        text=text,
                        source="skills",
                        source_detail=f"Core Competencies: {cat_name.replace('_', ' ').title()}",
                        skills=skills,
                        ownership_level="used",
                        has_metric=False,
                        metadata={"category": cat_name, "skills": skills}
                    )
                )

        return chunks


def load_profile_from_file(file_path: Optional[Path | str] = None) -> Dict[str, Any]:
    """Load profile from path or find my_profile.json in repository."""
    candidate_paths: List[Path] = []
    if file_path:
        candidate_paths.append(Path(file_path))

    # Default lookup locations
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    candidate_paths.extend([
        repo_root / "my_profile.json",
        Path.cwd() / "my_profile.json",
        Path.cwd().parent / "my_profile.json",
    ])

    for p in candidate_paths:
        if p.exists() and p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return {k: v for k, v in data.items() if not k.startswith("_")}
            except Exception as e:
                logger.warning(f"Failed to read profile at {p}: {e}")

    logger.warning("Could not locate my_profile.json; returning empty profile.")
    return {}
