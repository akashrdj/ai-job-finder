from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict
from datetime import datetime

class JobBase(BaseModel):
    source_name: str
    external_id: str
    title: str
    company: str
    location: Optional[str] = None
    is_remote: bool = False
    description: str
    url: str
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = "USD"
    posted_date: Optional[datetime] = None
    raw_metadata: Optional[Dict[str, Any]] = None

class JobCreate(JobBase):
    source_id: Optional[int] = None

class JobResponse(JobBase):
    id: int
    fetched_at: datetime

    model_config = ConfigDict(from_attributes=True)
