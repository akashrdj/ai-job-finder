from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON
from sqlalchemy.orm import relationship
from app.database import Base

class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    adapter_type = Column(String(50), nullable=False) # greenhouse, lever, ashby, remoteok, workday, scraper
    config = Column(JSON, nullable=True, default=dict)
    is_active = Column(Boolean, default=True)
    last_polled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    jobs = relationship("Job", back_populates="source_rel", cascade="all, delete-orphan")
