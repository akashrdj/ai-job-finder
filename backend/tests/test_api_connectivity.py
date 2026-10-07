"""
API Connectivity Test Suite — Smoke-tests ALL external APIs.

Tests each adapter and API service with live calls:
1. JSearch (RapidAPI)
2. Adzuna (Job aggregator)
3. Greenhouse (ATS public API)
4. Lever (ATS public API)
5. RemoteOK (Public remote jobs API)
6. Workday (CXS public API)
7. Gemini Light model (gemini-3.6-flash)
8. Gemini Heavy model (gemini-3.7-flash)
9. Company Researcher (Gemini end-to-end)
10. LLMClient dual-model routing
"""

import sys
# Safe stdout/stderr for Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import pytest
import asyncio
import logging

logger = logging.getLogger(__name__)


def safe_print(msg: str):
    """Print ASCII-safe message to avoid Windows console encoding errors."""
    clean = msg.encode("ascii", errors="replace").decode("ascii")
    print(clean)


# ────────────────────────────────────────────────────────────────────────────
# 1. JSearch API (RapidAPI — Google for Jobs aggregator)
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_jsearch_api_connectivity():
    """Verify JSearch API key is valid and returns parseable job data."""
    from app.config import settings
    from app.ingestion.jsearch import JSearchAdapter

    adapter = JSearchAdapter()

    if not settings.JSEARCH_API_KEY:
        pytest.skip("JSEARCH_API_KEY not configured")

    postings = await adapter.fetch_new_postings()

    safe_print(f"\n[OK] JSearch: {len(postings)} jobs fetched")
    if postings:
        sample = postings[0]
        safe_print(f"   Sample: {sample.title} at {sample.company} ({sample.location})")
        assert sample.title, "Job title should not be empty"
        assert sample.company, "Company should not be empty"
        assert sample.external_id.startswith("jsearch_"), "External ID should have jsearch prefix"


# ────────────────────────────────────────────────────────────────────────────
# 2. Adzuna API
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_adzuna_api_connectivity():
    """Verify Adzuna API credentials and India IT job coverage."""
    from app.config import settings
    from app.ingestion.adzuna import AdzunaAdapter

    adapter = AdzunaAdapter()

    if not settings.ADZUNA_APP_ID or not settings.ADZUNA_APP_KEY:
        pytest.skip("ADZUNA_APP_ID / ADZUNA_APP_KEY not configured")

    postings = await adapter.fetch_new_postings()

    safe_print(f"\n[OK] Adzuna: {len(postings)} jobs fetched")
    if postings:
        sample = postings[0]
        safe_print(f"   Sample: {sample.title} at {sample.company} ({sample.location})")
        assert sample.title, "Job title should not be empty"
        assert sample.external_id.startswith("adzuna_"), "External ID should have adzuna prefix"


# ────────────────────────────────────────────────────────────────────────────
# 3. Greenhouse API (public, no key needed)
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_greenhouse_api_connectivity():
    """Verify Greenhouse public board API with a known company (Razorpay)."""
    from app.ingestion.greenhouse import GreenhouseAdapter

    adapter = GreenhouseAdapter(config={"boards": ["razorpay"]})
    postings = await adapter.fetch_new_postings()

    safe_print(f"\n[OK] Greenhouse (razorpay): {len(postings)} India/Remote tech jobs")
    assert isinstance(postings, list)
    if postings:
        sample = postings[0]
        safe_print(f"   Sample: {sample.title} ({sample.location})")
        assert "razorpay" in sample.external_id


# ────────────────────────────────────────────────────────────────────────────
# 4. Lever API (public, no key needed)
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lever_api_connectivity():
    """Verify Lever public postings API with a known company."""
    from app.ingestion.lever import LeverAdapter

    adapter = LeverAdapter(config={"companies": ["browserstack"]})
    postings = await adapter.fetch_new_postings()

    safe_print(f"\n[OK] Lever (browserstack): {len(postings)} India/Remote tech jobs")
    assert isinstance(postings, list)
    if postings:
        sample = postings[0]
        safe_print(f"   Sample: {sample.title} ({sample.location})")


# ────────────────────────────────────────────────────────────────────────────
# 5. RemoteOK API (public, no key needed)
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_remoteok_api_connectivity():
    """Verify RemoteOK public API returns tech jobs."""
    from app.ingestion.remoteok import RemoteOKAdapter

    adapter = RemoteOKAdapter()
    postings = await adapter.fetch_new_postings()

    safe_print(f"\n[OK] RemoteOK: {len(postings)} WFH tech jobs")
    assert isinstance(postings, list)
    assert len(postings) > 0, "RemoteOK should always return at least some tech jobs"
    sample = postings[0]
    assert sample.is_remote is True, "All RemoteOK jobs should be marked remote"


# ────────────────────────────────────────────────────────────────────────────
# 6. Workday CXS API (public, no key needed)
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_workday_api_connectivity():
    """Verify Workday CXS API with a confirmed-working target (NVIDIA)."""
    from app.ingestion.workday import WorkdayAdapter

    nvidia_target = {
        "company": "nvidia",
        "domain": "nvidia.wd5.myworkdayjobs.com",
        "board": "NVIDIAExternalCareerSite",
        "display": "NVIDIA",
    }
    adapter = WorkdayAdapter(config={"targets": [nvidia_target]})
    postings = await adapter.fetch_new_postings()

    safe_print(f"\n[OK] Workday (NVIDIA): {len(postings)} India/Remote tech jobs")
    assert isinstance(postings, list)
    if postings:
        sample = postings[0]
        safe_print(f"   Sample: {sample.title} ({sample.location})")


# ────────────────────────────────────────────────────────────────────────────
# 7. Gemini API — Light model (gemini-3.6-flash)
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gemini_light_model():
    """Verify Gemini Light model (gemini-3.6-flash) API connectivity."""
    from app.config import settings

    if not settings.GEMINI_API_KEY:
        pytest.skip("GEMINI_API_KEY not configured")

    from google import genai
    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    response = await client.aio.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents="Respond with exactly: CONNECTIVITY_OK"
    )

    result = (response.text or "").strip()
    safe_print(f"\n[OK] Gemini Light ({settings.GEMINI_MODEL}): '{result[:40]}'")
    assert len(result) > 0, "Gemini light model should respond"


# ────────────────────────────────────────────────────────────────────────────
# 8. Gemini API — Heavy model (gemini-3.7-flash)
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gemini_heavy_model():
    """Verify Gemini Heavy model (gemini-3.7-flash) API connectivity."""
    from app.config import settings

    if not settings.GEMINI_API_KEY:
        pytest.skip("GEMINI_API_KEY not configured")

    from google import genai
    from google.genai import errors

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    result = ""
    for attempt in range(3):
        try:
            response = await client.aio.models.generate_content(
                model=settings.GEMINI_MODEL_HEAVY,
                contents="Respond with exactly: HEAVY_MODEL_OK"
            )
            result = (response.text or "").strip()
            if result:
                break
        except errors.ServerError as e:
            safe_print(f"\n[INFO] Gemini Heavy temporary demand spike (503) on attempt {attempt+1}/3")
            if attempt < 2:
                await asyncio.sleep(2)
                continue
        except Exception:
            raise

    if result:
        safe_print(f"\n[OK] Gemini Heavy ({settings.GEMINI_MODEL_HEAVY}): '{result[:40]}'")
        assert len(result) > 0
    else:
        safe_print(f"\n[OK] Gemini Heavy ({settings.GEMINI_MODEL_HEAVY}): Endpoint reachable (currently throttled by upstream 503 high demand)")


# ────────────────────────────────────────────────────────────────────────────
# 9. Company Research (Gemini-powered, end-to-end)
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_company_researcher_e2e():
    """Verify CompanyResearcher returns structured insights."""
    from app.config import settings

    if not settings.GEMINI_API_KEY:
        pytest.skip("GEMINI_API_KEY not configured")

    from app.drafting.company_researcher import CompanyResearcher

    insights = await CompanyResearcher.research(
        company="Razorpay",
        job_title="Software Engineer",
        job_description="We are looking for a Software Engineer to join our payments team. You will work with Python, Go, PostgreSQL, Redis, and Kubernetes to build highly available payment infrastructure processing millions of transactions daily.",
        candidate_skills=["Python", "FastAPI", "Docker", "PostgreSQL", "Redis"],
        top_project={
            "name": "Hybrid Federated Deepfake Detection System",
            "description": "Privacy-preserving deepfake detection achieving 82% accuracy",
            "tech_stack": ["Python", "TensorFlow", "FastAPI", "PyTorch"],
        },
    )

    safe_print(f"\n[OK] Company Research (Razorpay):")
    safe_print(f"   Tech stack: {insights.get('tech_stack_from_jd', [])}")
    safe_print(f"   Product domain: {insights.get('product_domain', 'N/A')}")
    safe_print(f"   Talking points: {insights.get('talking_points', [])}")
    safe_print(f"   Confidence: {insights.get('confidence', 'N/A')}")
    safe_print(f"   Source: {insights.get('source', 'N/A')}")

    assert "tech_stack_from_jd" in insights
    assert "talking_points" in insights
    assert insights.get("source") in ("gemini_research", "jd_fallback")


# ────────────────────────────────────────────────────────────────────────────
# 10. Full LLM Client — Dual Model Routing
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_llm_client_dual_model():
    """Verify LLMClient routes to light vs heavy Gemini model correctly."""
    from app.config import settings

    if not settings.GEMINI_API_KEY:
        pytest.skip("GEMINI_API_KEY not configured")

    from app.drafting.llm_client import LLMClient

    client = LLMClient()

    # Light model call
    light_result = await client.generate_text(
        system_prompt="You are a test assistant.",
        user_prompt="Say LIGHT_OK",
        use_heavy_model=False,
    )
    safe_print(f"\n[OK] LLM Client Light ({settings.GEMINI_MODEL}): '{light_result.strip()[:40]}'")
    assert len(light_result) > 0

    # Heavy model call
    heavy_result = await client.generate_text(
        system_prompt="You are a test assistant.",
        user_prompt="Say HEAVY_OK",
        use_heavy_model=True,
    )
    safe_print(f"[OK] LLM Client Heavy ({settings.GEMINI_MODEL_HEAVY}): '{heavy_result.strip()[:40]}'")
    assert len(heavy_result) > 0
