from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class JobPosting:
    source_name: str
    external_id: str
    title: str
    company: str
    location: Optional[str] = None
    is_remote: bool = False
    description: str = ""
    url: str = ""
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = "USD"
    posted_date: Optional[datetime] = None
    recruiter_email: Optional[str] = None
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

class SourceAdapter(ABC):
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.config = config or {}

    @abstractmethod
    async def fetch_new_postings(self, since: Optional[datetime] = None) -> List[JobPosting]:
        """Fetch and normalize job postings from this source."""
        pass
