import pytest
from app.models.job import Job
from app.models.user_profile import UserProfile
from app.matching.rules import RuleEvaluator
from app.matching.embeddings import EmbeddingVectorizer
from app.matching.engine import MatchingEngine
from app.api.profile import DEFAULT_CANDIDATE_DATA

def test_embedding_vectorizer_similarity():
    v = EmbeddingVectorizer()
    sim_high = v.compute_similarity(
        "Python FastAPI backend engineer building REST APIs and PostgreSQL database",
        "Python backend developer FastAPI PostgreSQL async REST endpoints"
    )
    assert sim_high > 0.35

    sim_low = v.compute_similarity(
        "Python FastAPI backend engineer",
        "Senior Pediatric Nurse with hospital ICU surgical ward clinical experience"
    )
    assert sim_low < 0.15

def test_rule_evaluator_blacklist_company():
    profile = UserProfile(**DEFAULT_CANDIDATE_DATA)
    profile.preferences["excluded_companies"] = ["BadCorp"]

    job = Job(
        source_name="greenhouse",
        external_id="123",
        title="Software Engineer",
        company="BadCorp",
        location="Remote",
        description="Great engineering job",
        url="https://example.com"
    )

    rule_score, matched, missing, reasons = RuleEvaluator.evaluate(job, profile)
    assert rule_score == 0.0
    assert any("Disqualified" in r for r in reasons)

def test_rule_evaluator_experience_filter():
    profile = UserProfile(**DEFAULT_CANDIDATE_DATA)
    profile.preferences["max_yoe"] = 1
    # Clear excluded keywords to specifically test the seniority and YOE evaluation
    profile.preferences["excluded_keywords"] = []

    # Senior job with 7+ years
    senior_job = Job(
        source_name="greenhouse",
        external_id="sen_1",
        title="Senior Staff Software Engineer",
        company="TechCorp",
        location="Remote",
        description="Requires 7+ years of experience in distributed systems.",
        url="https://example.com"
    )

    rule_score, matched, missing, reasons = RuleEvaluator.evaluate(senior_job, profile)
    assert rule_score < 0.3
    assert any("Seniority" in r or "Experience" in r for r in reasons)

def test_matching_engine_variant_selection():
    engine = MatchingEngine()
    profile = UserProfile(**DEFAULT_CANDIDATE_DATA)

    # Backend JD
    backend_jd = "Python FastAPI Backend Developer building microservices and PostgreSQL database pipelines."
    var, sim = engine.evaluate_variant_fit(backend_jd, profile)
    assert var == "backend"

    # AI / ML JD
    ai_jd = "GenAI Machine Learning Engineer working on PyTorch, LangChain, RAG pipelines, and Vector Embeddings."
    var_ai, sim_ai = engine.evaluate_variant_fit(ai_jd, profile)
    assert var_ai == "genai_ml"
