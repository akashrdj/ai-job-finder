from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

class WorkExperienceItem(BaseModel):
    company: str
    title: str
    location: Optional[str] = None
    start_date: str
    end_date: Optional[str] = "Present"
    bullets: List[str] = Field(default_factory=list)
    skills_used: List[str] = Field(default_factory=list)

class ProjectItem(BaseModel):
    name: str
    role: Optional[str] = None
    description: str
    bullets: List[str] = Field(default_factory=list)
    tech_stack: List[str] = Field(default_factory=list)
    url: Optional[str] = None
    github_url: Optional[str] = None

class EducationItem(BaseModel):
    institution: str
    degree: str
    field_of_study: str
    graduation_year: str
    cgpa_or_grade: Optional[str] = None

class CuratedVariant(BaseModel):
    title: str
    summary: str
    highlighted_skills: List[str] = Field(default_factory=list)
    key_bullet_points: List[str] = Field(default_factory=list)
    cover_letter_template: str

class CandidatePreferences(BaseModel):
    target_roles: List[str] = Field(default_factory=lambda: [
        "Software Engineer", "Backend Developer", "Full Stack Developer", "Python Developer", "AI Engineer", "Graduate Engineer Trainee"
    ])
    max_yoe: int = 1
    remote_only: bool = False
    preferred_locations: List[str] = Field(default_factory=lambda: ["Remote", "Bengaluru", "Hyderabad", "Pune", "Delhi NCR", "San Francisco", "New York"])
    min_salary: float = 0
    excluded_companies: List[str] = Field(default_factory=list)
    excluded_keywords: List[str] = Field(default_factory=lambda: [
        "Senior", "Lead", "Staff", "Principal", "Director", "5+ years", "7+ years", "10+ years"
    ])

class UserProfileBase(BaseModel):
    full_name: str
    email: str
    phone: Optional[str] = None
    location: Optional[str] = None
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    work_history: List[WorkExperienceItem] = Field(default_factory=list)
    projects: List[ProjectItem] = Field(default_factory=list)
    education: List[EducationItem] = Field(default_factory=list)
    curated_variants: Dict[str, CuratedVariant] = Field(default_factory=dict)
    preferences: CandidatePreferences = Field(default_factory=CandidatePreferences)
    is_active: bool = True

class UserProfileCreate(UserProfileBase):
    pass

class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    skills: Optional[List[str]] = None
    work_history: Optional[List[WorkExperienceItem]] = None
    projects: Optional[List[ProjectItem]] = None
    education: Optional[List[EducationItem]] = None
    curated_variants: Optional[Dict[str, CuratedVariant]] = None
    preferences: Optional[CandidatePreferences] = None
    is_active: Optional[bool] = None

class UserProfileResponse(UserProfileBase):
    id: int
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
