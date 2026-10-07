"""
SQLAlchemy model for enriched company contacts.
Stores HR / recruiter / CTO / engineering lead contacts discovered
via Hunter.io, Snov.io, web scraping, LinkedIn, or email-pattern
generation.
"""
import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Float, Boolean
from app.database import Base


class CompanyContact(Base):
    __tablename__ = "company_contacts"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # ── Company info ──────────────────────────────────────────────
    company_name = Column(String(256), nullable=False, index=True)
    company_domain = Column(String(256), nullable=True)
    industry = Column(String(128), nullable=True)
    company_type = Column(String(64), nullable=True)          # "startup" | "mnc" | "mid-size"

    # ── Contact info ──────────────────────────────────────────────
    contact_name = Column(String(256), nullable=True)
    contact_email = Column(String(320), nullable=False)
    contact_role = Column(String(256), nullable=True)         # "Technical Recruiter", "CTO", "HR Manager", etc.
    contact_title = Column(String(256), nullable=True)        # Exact LinkedIn title if available
    linkedin_url = Column(String(512), nullable=True)

    # ── Discovery metadata ────────────────────────────────────────
    source = Column(String(64), nullable=False, default="manual")
    # Values: "hunter", "snov", "apollo", "web_scrape", "pattern_guess",
    #         "manual", "master_sheet", "freshers_sheet"
    confidence = Column(Float, nullable=True)                 # 0–100
    is_verified = Column(Boolean, default=False)
    verification_status = Column(String(32), nullable=True)   # "valid" | "invalid" | "risky" | "unknown"

    # ── Cold-email tracking ───────────────────────────────────────
    cold_email_status = Column(String(32), default="pending")
    # Values: "pending" | "draft_ready" | "approved" | "sent" | "replied" | "bounced" | "skipped"
    cold_email_subject = Column(Text, nullable=True)
    cold_email_body = Column(Text, nullable=True)
    cold_email_sent_at = Column(DateTime, nullable=True)

    # ── Freshers-specific fields ──────────────────────────────────
    fresher_role = Column(String(256), nullable=True)         # "SDE-I", "Backend Developer", etc.
    opening_period = Column(String(128), nullable=True)       # "Q1/Q3 off-campus", "Year-round"
    target_contact_type = Column(String(128), nullable=True)  # "Technical Recruiter", "Engineering Manager"

    # ── Timestamps ────────────────────────────────────────────────
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    def __repr__(self):
        return f"<CompanyContact {self.company_name} | {self.contact_email} | {self.source}>"
