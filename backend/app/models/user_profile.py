from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON
from sqlalchemy.orm import relationship
from app.database import Base

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False)
    phone = Column(String(50), nullable=True)
    location = Column(String(100), nullable=True)
    github_url = Column(String(255), nullable=True)
    linkedin_url = Column(String(255), nullable=True)
    portfolio_url = Column(String(255), nullable=True)

    # Core structured data
    skills = Column(JSON, nullable=False, default=list) # e.g. ["Python", "FastAPI", "React", ...]
    work_history = Column(JSON, nullable=False, default=list)
    projects = Column(JSON, nullable=False, default=list)
    education = Column(JSON, nullable=False, default=list)

    # 4 Curated Profiles Matrix for high ATS relevance & zero bogus AI claims
    # Keys: "backend", "sde", "genai_ml", "fullstack"
    curated_variants = Column(JSON, nullable=False, default=dict)

    # Candidate Preferences & Hard Filters
    preferences = Column(JSON, nullable=False, default=lambda: {
        "target_roles": ["Software Engineer", "Backend Developer", "Full Stack Developer", "Python Developer", "AI Engineer"],
        "max_yoe": 1,
        "remote_only": False,
        "preferred_locations": ["Remote", "Bengaluru", "Hyderabad", "Pune", "San Francisco", "New York", "London"],
        "min_salary": 0,
        "excluded_companies": [],
        "excluded_keywords": ["Senior Lead", "Staff", "Director", "5+ years", "7+ years", "10+ years"]
    })

    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    match_scores = relationship("MatchScore", back_populates="profile", cascade="all, delete-orphan")
