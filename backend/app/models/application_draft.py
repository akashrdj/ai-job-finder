from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base

class ApplicationDraft(Base):
    __tablename__ = "applications_drafted"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    match_score_id = Column(Integer, ForeignKey("match_scores.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Tailored resume content (selected variant + tailored bullets)
    resume_variant = Column(JSON, nullable=False, default=dict)
    
    # Tailored cover letter
    cover_letter = Column(Text, nullable=False)
    
    # Anti-Hallucination Claim Validation
    # "PASSED" or "FLAGGED_UNVERIFIED_CLAIMS"
    claim_validation_status = Column(String(50), nullable=False, default="PASSED")
    claim_validation_report = Column(JSON, nullable=False, default=dict)

    # Referral & Cold Outreach Kit (LinkedIn X-Ray links, domain email pattern, ready cold pitch)
    outreach_kit = Column(JSON, nullable=False, default=dict)

    # Grounded company research insights (product domain, talking points, recent news)
    company_research = Column(JSON, nullable=True, default=dict)

    # User review workflow: "pending", "applied", "dismissed"
    user_action = Column(String(50), nullable=False, default="pending", index=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    job = relationship("Job", back_populates="drafts")
    match_score = relationship("MatchScore", back_populates="draft")
