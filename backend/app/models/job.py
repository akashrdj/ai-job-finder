from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, Float, DateTime, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.orm import relationship
from app.database import Base

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey("sources.id", ondelete="SET NULL"), nullable=True)
    source_name = Column(String(50), nullable=False, index=True) # e.g. "greenhouse", "remoteok", "lever"
    external_id = Column(String(255), nullable=False, index=True)
    title = Column(String(255), nullable=False, index=True)
    company = Column(String(255), nullable=False, index=True)
    location = Column(String(255), nullable=True)
    is_remote = Column(Boolean, default=False)
    description = Column(Text, nullable=False)
    url = Column(String(1000), nullable=False)
    salary_min = Column(Float, nullable=True)
    salary_max = Column(Float, nullable=True)
    salary_currency = Column(String(10), nullable=True, default="USD")
    posted_date = Column(DateTime, nullable=True)
    raw_metadata = Column(JSON, nullable=True, default=dict)
    fetched_at = Column(DateTime, default=datetime.utcnow)

    # Constraints: Unique per source & external_id
    __table_args__ = (
        UniqueConstraint("source_name", "external_id", name="uq_source_external_id"),
    )

    source_rel = relationship("Source", back_populates="jobs")
    match_scores = relationship("MatchScore", back_populates="job", cascade="all, delete-orphan")
    drafts = relationship("ApplicationDraft", back_populates="job", cascade="all, delete-orphan")
