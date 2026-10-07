from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from app.schemas.job import JobResponse

class MatchScoreBase(BaseModel):
    job_id: int
    profile_id: int
    score: float
    semantic_similarity: float
    rule_score: float
    selected_variant: str
    rationale: str
    matched_skills: List[str] = []
    missing_requirements: List[str] = []
    gap_report: Optional[Dict[str, Any]] = None

class MatchScoreResponse(MatchScoreBase):
    id: int
    calculated_at: datetime
    job: Optional[JobResponse] = None

    model_config = ConfigDict(from_attributes=True)

