from datetime import datetime
from sqlalchemy import Column, Integer, Float, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base

class MatchScore(Base):
    __tablename__ = "match_scores"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_id = Column(Integer, ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    
    score = Column(Float, nullable=False, index=True) # 0.0 to 100.0
    semantic_similarity = Column(Float, nullable=False, default=0.0) # 0.0 to 1.0
    rule_score = Column(Float, nullable=False, default=1.0) # 0.0 to 1.0
    selected_variant = Column(Text, nullable=False, default="sde") # "backend", "sde", "genai_ml", "fullstack"
    
    rationale = Column(Text, nullable=False) # Markdown explanation of why matched
    matched_skills = Column(JSON, nullable=False, default=list)
    missing_requirements = Column(JSON, nullable=False, default=list)
    gap_report = Column(JSON, nullable=True, default=None) # Gemini-powered full gap analysis
    calculated_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="match_scores")
    profile = relationship("UserProfile", back_populates="match_scores")
    draft = relationship("ApplicationDraft", back_populates="match_score", uselist=False, cascade="all, delete-orphan")

