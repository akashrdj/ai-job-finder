import pytest
from app.models.user_profile import UserProfile
from app.drafting.claim_validator import ClaimValidator
from app.api.profile import DEFAULT_CANDIDATE_DATA

def test_claim_validator_authentic_content_passes():
    profile = UserProfile(**DEFAULT_CANDIDATE_DATA)
    
    tailored_resume = {
        "skills": ["Python", "FastAPI", "React", "PostgreSQL", "Docker"],
        "projects": profile.projects
    }
    
    cover_letter = """
    Dear Hiring Team,
    I am writing to express my interest in the Software Engineer position.
    With experience in Python and FastAPI, I built asynchronous REST APIs.
    I look forward to discussing my application.
    """
    
    status, report = ClaimValidator.validate_claims(tailored_resume, cover_letter, profile)
    assert status == "PASSED"
    assert report["flagged_claims_count"] == 0
    assert report["verified_claims_count"] > 0

def test_claim_validator_flags_unverified_skills():
    profile = UserProfile(**DEFAULT_CANDIDATE_DATA)
    
    # Add a fabricated skill the user does not have (e.g. Rust / Cassandra)
    tailored_resume = {
        "skills": ["Python", "FastAPI", "Rust", "Cassandra"],
        "projects": profile.projects
    }
    
    cover_letter = "I am an expert in Rust and Cassandra distributed storage."
    
    status, report = ClaimValidator.validate_claims(tailored_resume, cover_letter, profile)
    assert status == "FLAGGED_UNVERIFIED_CLAIMS"
    assert report["flagged_claims_count"] >= 2
    flagged_entities = [c["entity"] for c in report["claims_breakdown"] if c["status"] == "FLAGGED_UNVERIFIED"]
    assert "Rust" in flagged_entities or "rust" in [e.lower() for e in flagged_entities]

def test_claim_validator_flags_fabricated_metrics():
    profile = UserProfile(**DEFAULT_CANDIDATE_DATA)
    
    tailored_resume = {
        "skills": ["Python", "FastAPI"],
        "projects": profile.projects
    }
    
    # LLM hallucination with fake 95% metric never in candidate profile
    cover_letter = "I boosted company annual revenue by 95% single-handedly."
    
    status, report = ClaimValidator.validate_claims(tailored_resume, cover_letter, profile)
    assert status == "FLAGGED_UNVERIFIED_CLAIMS"
    assert report["flagged_claims_count"] >= 1
