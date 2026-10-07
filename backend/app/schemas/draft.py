from typing import Dict, Any, Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from app.schemas.job import JobResponse
from app.schemas.match import MatchScoreResponse

class ApplicationDraftBase(BaseModel):
    job_id: int
    match_score_id: int
    resume_variant: Dict[str, Any]
    cover_letter: str
    claim_validation_status: str
    claim_validation_report: Dict[str, Any]
    outreach_kit: Dict[str, Any]
    user_action: str = "pending"
    notes: Optional[str] = None

class ApplicationDraftActionUpdate(BaseModel):
    user_action: str
    notes: Optional[str] = None

class ApplicationDraftResponse(ApplicationDraftBase):
    id: int
    created_at: datetime
    updated_at: datetime
    job: Optional[JobResponse] = None
    match_score: Optional[MatchScoreResponse] = None

    model_config = ConfigDict(from_attributes=True)
