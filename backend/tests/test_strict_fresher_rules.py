import pytest
import asyncio
from app.models.job import Job
from app.models.user_profile import UserProfile
from app.matching.rules import RuleEvaluator, extract_experience_requirements
from app.matching.openrouter_agent import FresherInspectionAgent
from app.api.profile import DEFAULT_CANDIDATE_DATA


def test_extract_experience_requirements():
    assert 0 in extract_experience_requirements("Looking for freshers with 0-1 years of experience.")
    assert 2 in extract_experience_requirements("Candidate must have 2+ years of software experience.")
    assert 1 in extract_experience_requirements("Requires 1-3 years of experience in Python.")
    assert 3 in extract_experience_requirements("Minimum 3 years of hands-on experience.")


def test_disqualify_junior_with_2_yoe():
    """A role labeled 'Junior' or 'Associate' that demands 2+ YOE must be rejected for a 0-YOE fresher."""
    profile = UserProfile(**DEFAULT_CANDIDATE_DATA)
    profile.preferences["excluded_keywords"] = []

    job = Job(
        source_name="jsearch",
        external_id="j_2yoe",
        title="Associate Software Engineer",
        company="GlobalTech",
        location="Bengaluru, India",
        description="We are looking for an Associate Software Engineer. Requirements: 2+ years of experience in Java and Spring Boot.",
        url="https://example.com/job1"
    )

    rule_score, matched, missing, reasons = RuleEvaluator.evaluate(job, profile)
    assert rule_score == 0.0
    assert any("Disqualified" in r and "years of experience" in r for r in reasons)


def test_disqualify_1_to_3_years_experience():
    """A role requiring 1-3 years without 0 YOE eligibility must be rejected."""
    profile = UserProfile(**DEFAULT_CANDIDATE_DATA)
    profile.preferences["excluded_keywords"] = []

    job = Job(
        source_name="adzuna",
        external_id="j_1to3",
        title="Junior Python Developer",
        company="StartupX",
        location="Remote",
        description="Looking for Junior Python Developer with 1-3 years of experience building APIs with FastAPI.",
        url="https://example.com/job2"
    )

    rule_score, matched, missing, reasons = RuleEvaluator.evaluate(job, profile)
    assert rule_score == 0.0
    assert any("Disqualified" in r for r in reasons)


def test_qualify_pure_fresher_0_to_1_yoe():
    """A role explicitly stating 0-1 or 0-2 years must qualify and receive fresher priority."""
    profile = UserProfile(**DEFAULT_CANDIDATE_DATA)
    profile.preferences["excluded_keywords"] = []

    job = Job(
        source_name="workday",
        external_id="j_0yoe",
        title="Software Engineer 1",
        company="Adobe",
        location="Bengaluru, India",
        description="0-1 years of experience or new university graduate. Hands-on experience with Python, Data Structures, and APIs.",
        url="https://example.com/job3"
    )

    rule_score, matched, missing, reasons = RuleEvaluator.evaluate(job, profile)
    assert rule_score >= 1.0
    assert any("Pure Fresher Experience" in r or "Fresher Priority" in r for r in reasons)


def test_fintech_jpmorgan_software_engineer_program():
    """JPMorgan Software Engineer Program for campus/freshers must receive top score."""
    profile = UserProfile(**DEFAULT_CANDIDATE_DATA)
    profile.preferences["excluded_keywords"] = []

    job = Job(
        source_name="workday",
        external_id="jpmc_sep_01",
        title="Software Engineer Program - 2026",
        company="JPMorgan Chase",
        location="Bengaluru, India",
        description="Software Engineer Program for campus recruits and fresh graduates. 0 years experience required, knowledge of Python, Java, and CS fundamentals.",
        url="https://jpmc.wd5.myworkdayjobs.com/JPMC/job/1"
    )

    rule_score, matched, missing, reasons = RuleEvaluator.evaluate(job, profile)
    assert rule_score >= 1.3
    assert RuleEvaluator.is_fresher_job(job) is True


def test_disqualify_mandatory_commercial_experience():
    """Roles requiring prior commercial/industry experience without 0 YOE override must be disqualified."""
    profile = UserProfile(**DEFAULT_CANDIDATE_DATA)
    profile.preferences["excluded_keywords"] = []

    job = Job(
        source_name="greenhouse",
        external_id="gh_commercial",
        title="Software Engineer",
        company="MidCorp",
        location="Bengaluru, India",
        description="We are hiring a Software Engineer. Prior commercial experience required. Strong knowledge of Python and React.",
        url="https://example.com/job4"
    )

    rule_score, matched, missing, reasons = RuleEvaluator.evaluate(job, profile)
    assert rule_score == 0.0
    assert any("prior experience" in r.lower() for r in reasons)


@pytest.mark.asyncio
async def test_fresher_inspection_agent_heuristic():
    agent = FresherInspectionAgent()

    # Test 1: Should disqualify 2+ years
    res_disq = await agent.inspect_job_description(
        title="Associate Backend Developer",
        description="Requires 2+ years of professional experience with PostgreSQL and Docker.",
        company="FinTech Inc"
    )
    assert res_disq.is_fresher_eligible is False
    assert res_disq.verdict == "DISQUALIFIED"

    # Test 2: Should qualify 0-1 years GET
    res_qual = await agent.inspect_job_description(
        title="Graduate Engineer Trainee - SDE",
        description="Open to freshers and 2025/2026 batch. 0-1 years of experience. Python knowledge preferred.",
        company="TopMNC"
    )
    assert res_qual.is_fresher_eligible is True
    assert res_qual.verdict == "ELIGIBLE_FRESHER"
