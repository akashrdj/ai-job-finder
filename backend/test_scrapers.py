"""
Test all scraper adapters and verify tiered scheduling.
Tests: LinkedIn Guest (free), JobSpy (free), Apify (cost-guarded check only).
"""
import asyncio
import logging
from app.ingestion.linkedin_scraper import LinkedInGuestScraperAdapter
from app.ingestion.jobspy_scraper import JobSpyAdapter
from app.ingestion.apify_scraper import ApifyJobScraperAdapter
from app.ingestion.manager import IngestionManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def test_all_scrapers():
    # ─── 1. LinkedIn Guest Scraper (FREE, every 15 min) ──────────────────
    print("\n" + "=" * 70)
    print("  TIER 1: LinkedIn Guest Scraper — $0/month, runs every 15 min")
    print("=" * 70)

    linkedin_adapter = LinkedInGuestScraperAdapter(
        config={
            "location": "India",
            "queries": ["Python Developer", "AI Engineer"],
            "max_jobs_per_query": 3,
        }
    )
    li_jobs = await linkedin_adapter.fetch_new_postings()
    print(f"\n✅ LinkedIn: {len(li_jobs)} jobs scraped (past 24h)")
    for idx, job in enumerate(li_jobs[:3], 1):
        print(f"  [{idx}] {job.title} @ {job.company}")
        print(f"      📍 {job.location} | 🔗 {job.url[:80]}...")
        desc_preview = job.description[:120].replace('\n', ' ')
        print(f"      📝 {desc_preview}...")

    # ─── 2. JobSpy Multi-Board Scraper (FREE, every 15 min) ──────────────
    print("\n" + "=" * 70)
    print("  TIER 1: JobSpy — $0/month (LinkedIn + Indeed + Glassdoor + Google)")
    print("=" * 70)

    jobspy_adapter = JobSpyAdapter(
        config={
            "location": "India",
            "queries": ["Python Developer"],
            "sites": ["linkedin", "indeed", "glassdoor"],
            "results_per_query": 5,
            "hours_old": 72,
        }
    )
    js_jobs = await jobspy_adapter.fetch_new_postings()
    print(f"\n✅ JobSpy: {len(js_jobs)} jobs scraped across multiple boards")
    for idx, job in enumerate(js_jobs[:5], 1):
        print(f"  [{idx}] {job.title} @ {job.company} ({job.source_name})")
        print(f"      📍 {job.location}")
        if job.salary_min or job.salary_max:
            print(f"      💰 {job.salary_currency} {job.salary_min}-{job.salary_max}")

    # ─── 3. Apify Cloud Scraper (PAID, once/day at 6 PM IST) ─────────────
    print("\n" + "=" * 70)
    print("  TIER 3: Apify Cloud Scraper — ~$0.81/month (once/day at 6 PM IST)")
    print("=" * 70)

    apify_adapter = ApifyJobScraperAdapter()
    print(f"  Configured: {apify_adapter.is_configured()}")
    print(f"  Actor: {apify_adapter.actor_id}")
    print(f"  Max Items: {apify_adapter.max_items}")
    if not apify_adapter.is_configured():
        print("  ⚠️  APIFY_API_TOKEN not set. Skipping cloud run.")
        print("  💡 Get free $5/month at https://console.apify.com")
    else:
        apify_jobs = await apify_adapter.fetch_new_postings()
        print(f"  ✅ Apify: {len(apify_jobs)} jobs from cloud actor")

    # ─── 4. Verify Tiered Manager ────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  TIERED INGESTION MANAGER — Cost-Aware Adapter Groups")
    print("=" * 70)

    mgr = IngestionManager()
    print(f"\n  All adapters registered: {list(mgr.adapters.keys())}")
    print(f"\n  TIER 1 (Free Frequent - every 15 min):")
    for name in mgr.get_tier_adapters("free_frequent"):
        print(f"    ✅ {name}")
    print(f"\n  TIER 2 (Free Moderate - every 2 hours):")
    for name in mgr.get_tier_adapters("free_moderate"):
        print(f"    ✅ {name}")
    print(f"\n  TIER 3 (Paid Daily - 6 PM IST only):")
    for name in mgr.get_tier_adapters("paid_daily"):
        cost = "~$0.81/mo" if name == "apify_scraper" else "$?"
        print(f"    💰 {name} ({cost})")

    # ─── Summary ─────────────────────────────────────────────────────────
    total_free_jobs = len(li_jobs) + len(js_jobs)
    print("\n" + "=" * 70)
    print(f"  TOTAL FREE JOBS SCRAPED: {total_free_jobs}")
    print(f"  Monthly cost: $0.00 (LinkedIn + JobSpy + JSearch + Adzuna + ATS)")
    print(f"  Apify budget: ~$0.81/month of $5.00 free tier")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_all_scrapers())
