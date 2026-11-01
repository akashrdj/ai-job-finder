"""
Three-Speed Pipeline Scheduler
================================================================================

FAST LANE (every 15 min) — $0/month:
    LinkedIn Guest Scraper + JobSpy + JSearch + Adzuna + ATS adapters
    → Score all new jobs → Store ranked list
    Zero LLM calls. Pure HTTP + local TF-IDF scoring.

MEDIUM LANE (every 2 hours) — $0/month:
    Company Portal Tracker + Scraper Fallback
    Heavier HTTP crawling of custom career pages.

APIFY LANE (once/day at 6 PM IST) — ~$0.81/month:
    Apify Cloud Actor with cost guards (512MB, 60s timeout, 15 rows)
    Catches LinkedIn jobs that guest scraper missed + non-ATS sites.

SLOW LANE (2x/day: configurable IST hours):
    Pick top-N undrafted jobs → Company research → Cover letter + resume
    → Anti-hallucination validation → Outreach kit
    Capped at MAX_DRAFTS_PER_DAY and MAX_OUTREACH_PER_DAY.
================================================================================
"""

import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

import app.database as app_db
from app.config import settings
from app.models.job import Job
from app.models.user_profile import UserProfile
from app.models.match_score import MatchScore
from app.models.application_draft import ApplicationDraft
from app.ingestion.manager import IngestionManager
from app.matching.engine import MatchingEngine
from app.drafting.engine import DraftingEngine

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.ingestion_manager = IngestionManager()
        self.matching_engine = MatchingEngine()
        self.drafting_engine = DraftingEngine()

        self.is_running = False
        self._discovery_lock = asyncio.Lock()
        self._drafting_lock = asyncio.Lock()
        self._apify_lock = asyncio.Lock()
        self.last_run_time: Optional[datetime] = None

        # Daily counters (reset each day)
        self._today: Optional[date] = None
        self._drafts_today: int = 0
        self._outreach_today: int = 0

        self.last_run_stats: Dict[str, Any] = {
            "new_jobs_found": 0,
            "jobs_scored": 0,
            "drafts_created": 0,
            "status": "idle",
            "mode": "idle",
        }

    def _reset_daily_counters_if_needed(self):
        """Reset daily volume counters at midnight."""
        today = date.today()
        if self._today != today:
            self._today = today
            self._drafts_today = 0
            self._outreach_today = 0
            logger.info(f"Daily counters reset for {today}")

    # ──────────────────────────────────────────────────────────────────────────
    # FAST LANE: Free Discovery + Scoring (every 15 min, zero LLM calls)
    # ──────────────────────────────────────────────────────────────────────────

    async def execute_discovery(self) -> Dict[str, Any]:
        """
        Fast lane — runs every 15 minutes.
        Ingests jobs from FREE sources (LinkedIn Scraper, JobSpy, JSearch,
        Adzuna, ATS APIs), scores them against the profile.
        No LLM calls, no paid APIs, no drafting.
        """
        if self._discovery_lock.locked():
            logger.info("Discovery already running, skipping overlapping invocation.")
            return {"status": "skipped", "reason": "already_running", "mode": "discovery"}

        async with self._discovery_lock:
            self.is_running = True
            self.last_run_stats["status"] = "running"
            self.last_run_stats["mode"] = "discovery"
            logger.info("=== FAST LANE: Free Discovery + Scoring (every 15 min) ===")

            stats: Dict[str, Any] = {
                "new_jobs_found": 0,
                "jobs_scored": 0,
                "drafts_created": 0,
                "timestamp": datetime.utcnow().isoformat(),
                "mode": "discovery",
                "tier": "free_frequent",
            }

            async with app_db.AsyncSessionLocal() as db:
                try:
                    # 1. Fetch active candidate profile
                    stmt = select(UserProfile).where(UserProfile.is_active == True)
                    profile = (await db.execute(stmt)).scalars().first()

                    if not profile:
                        logger.warning("No active UserProfile found. Skipping discovery.")
                        self.is_running = False
                        self.last_run_stats = {**stats, "status": "no_profile_found"}
                        return self.last_run_stats

                    # 2. Ingest from FREE FREQUENT adapters only (no Apify)
                    free_sources = self.ingestion_manager.get_tier_adapters("free_frequent")
                    new_jobs = await self.ingestion_manager.run_ingestion(db, source_names=free_sources)
                    stats["new_jobs_found"] = len(new_jobs)

                    # 3. Score all unscored jobs (no LLM — just TF-IDF + rules)
                    existing_scored_subq = select(MatchScore.job_id).where(
                        MatchScore.profile_id == profile.id
                    )
                    unscored_stmt = (
                        select(Job)
                        .where(Job.id.not_in(existing_scored_subq))
                        .order_by(Job.fetched_at.desc())
                        .limit(100)
                    )
                    unscored_jobs = (await db.execute(unscored_stmt)).scalars().all()

                    logger.info(f"Scoring {len(unscored_jobs)} unscored jobs...")

                    for job in unscored_jobs:
                        await self.matching_engine.score_job(db, job, profile)
                        stats["jobs_scored"] += 1

                    stats["status"] = "success"
                    self.last_run_time = datetime.utcnow()
                    self.last_run_stats = stats
                    logger.info(
                        f"Discovery complete: {stats['new_jobs_found']} new, "
                        f"{stats['jobs_scored']} scored"
                    )

                except Exception as e:
                    logger.error(f"Error during discovery: {e}", exc_info=True)
                    stats["status"] = f"error: {str(e)}"
                    self.last_run_stats = stats
                finally:
                    self.is_running = False

            return self.last_run_stats

    # ──────────────────────────────────────────────────────────────────────────
    # MEDIUM LANE: Portal Crawling (every 2 hours, free but heavier)
    # ──────────────────────────────────────────────────────────────────────────

    async def execute_moderate_discovery(self) -> Dict[str, Any]:
        """
        Medium lane — runs every 2 hours.
        Crawls custom company career portals and scraper fallback pages.
        Free but involves heavier HTTP crawling.
        """
        logger.info("=== MEDIUM LANE: Portal Crawling (every 2 hours) ===")

        stats: Dict[str, Any] = {
            "new_jobs_found": 0,
            "timestamp": datetime.utcnow().isoformat(),
            "mode": "moderate_discovery",
            "tier": "free_moderate",
        }

        async with app_db.AsyncSessionLocal() as db:
            try:
                moderate_sources = self.ingestion_manager.get_tier_adapters("free_moderate")
                new_jobs = await self.ingestion_manager.run_ingestion(db, source_names=moderate_sources)
                stats["new_jobs_found"] = len(new_jobs)
                stats["status"] = "success"

                # Score any new unscored jobs
                stmt = select(UserProfile).where(UserProfile.is_active == True)
                profile = (await db.execute(stmt)).scalars().first()
                if profile and new_jobs:
                    existing_scored_subq = select(MatchScore.job_id).where(
                        MatchScore.profile_id == profile.id
                    )
                    unscored_stmt = (
                        select(Job)
                        .where(Job.id.not_in(existing_scored_subq))
                        .order_by(Job.fetched_at.desc())
                        .limit(50)
                    )
                    unscored_jobs = (await db.execute(unscored_stmt)).scalars().all()
                    for job in unscored_jobs:
                        await self.matching_engine.score_job(db, job, profile)

                logger.info(f"Moderate discovery complete: {stats['new_jobs_found']} new jobs.")
            except Exception as e:
                logger.error(f"Error during moderate discovery: {e}", exc_info=True)
                stats["status"] = f"error: {str(e)}"

        return stats

    # ──────────────────────────────────────────────────────────────────────────
    # APIFY LANE: Paid Cloud Scraper (once/day at 6 PM IST)
    # ──────────────────────────────────────────────────────────────────────────

    async def execute_apify_scrape(self) -> Dict[str, Any]:
        """
        Apify lane — runs ONCE per day at 6 PM IST.
        Uses cost-guarded Apify actor (512 MB, 60s timeout, 15 rows).
        Estimated monthly cost: ~$0.81 (well within $5 free tier).
        """
        if self._apify_lock.locked():
            logger.info("Apify scrape already running, skipping.")
            return {"status": "skipped", "reason": "already_running", "mode": "apify_daily"}

        async with self._apify_lock:
            logger.info("=== APIFY LANE: Daily Cloud Scrape (6 PM IST, cost-guarded) ===")

            stats: Dict[str, Any] = {
                "new_jobs_found": 0,
                "timestamp": datetime.utcnow().isoformat(),
                "mode": "apify_daily",
                "tier": "paid_daily",
            }

            async with app_db.AsyncSessionLocal() as db:
                try:
                    apify_sources = self.ingestion_manager.get_tier_adapters("paid_daily")
                    new_jobs = await self.ingestion_manager.run_ingestion(db, source_names=apify_sources)
                    stats["new_jobs_found"] = len(new_jobs)
                    stats["status"] = "success"

                    # Score new Apify jobs
                    stmt = select(UserProfile).where(UserProfile.is_active == True)
                    profile = (await db.execute(stmt)).scalars().first()
                    if profile and new_jobs:
                        existing_scored_subq = select(MatchScore.job_id).where(
                            MatchScore.profile_id == profile.id
                        )
                        unscored_stmt = (
                            select(Job)
                            .where(Job.id.not_in(existing_scored_subq))
                            .order_by(Job.fetched_at.desc())
                            .limit(50)
                        )
                        unscored_jobs = (await db.execute(unscored_stmt)).scalars().all()
                        for job in unscored_jobs:
                            await self.matching_engine.score_job(db, job, profile)

                    logger.info(f"Apify daily scrape complete: {stats['new_jobs_found']} new jobs.")
                except Exception as e:
                    logger.error(f"Error during Apify scrape: {e}", exc_info=True)
                    stats["status"] = f"error: {str(e)}"

            return stats

    # ──────────────────────────────────────────────────────────────────────────
    # SLOW LANE: Drafting + Company Research (2x/day, uses LLM)
    # ──────────────────────────────────────────────────────────────────────────

    async def execute_drafting(self) -> Dict[str, Any]:
        """
        Slow lane — runs at scheduled hours (default 9am + 6pm IST).
        Picks the top-N highest-scoring undrafted jobs, runs company research,
        generates cover letters + outreach kits, validates claims.
        Respects daily volume caps.
        """
        if self._drafting_lock.locked():
            logger.info("Drafting already running, skipping overlapping invocation.")
            return {"status": "skipped", "reason": "already_running", "mode": "drafting"}

        self._reset_daily_counters_if_needed()

        # Check if daily cap already reached
        remaining_drafts = settings.MAX_DRAFTS_PER_DAY - self._drafts_today
        if remaining_drafts <= 0:
            logger.info(
                f"Daily draft cap reached ({self._drafts_today}/{settings.MAX_DRAFTS_PER_DAY}). "
                "Skipping drafting run."
            )
            return {
                "status": "capped",
                "drafts_today": self._drafts_today,
                "max_per_day": settings.MAX_DRAFTS_PER_DAY,
                "mode": "drafting",
            }

        async with self._drafting_lock:
            self.is_running = True
            logger.info(
                f"=== SLOW LANE: Drafting + Company Research "
                f"(remaining today: {remaining_drafts} drafts, "
                f"{settings.MAX_OUTREACH_PER_DAY - self._outreach_today} outreach) ==="
            )

            stats: Dict[str, Any] = {
                "new_jobs_found": 0,
                "jobs_scored": 0,
                "drafts_created": 0,
                "outreach_created": 0,
                "skipped_outreach": 0,
                "timestamp": datetime.utcnow().isoformat(),
                "mode": "drafting",
            }

            async with app_db.AsyncSessionLocal() as db:
                try:
                    # 1. Fetch active profile
                    stmt = select(UserProfile).where(UserProfile.is_active == True)
                    profile = (await db.execute(stmt)).scalars().first()

                    if not profile:
                        logger.warning("No active UserProfile found. Skipping drafting.")
                        self.is_running = False
                        return {**stats, "status": "no_profile_found"}

                    # 2. Find top-N qualifying jobs that haven't been drafted yet
                    existing_draft_job_ids_stmt = select(ApplicationDraft.job_id)
                    existing_draft_job_ids = set(
                        (await db.execute(existing_draft_job_ids_stmt)).scalars().all()
                    )

                    # Get top-scoring unprocessed matches
                    qualifying_stmt = (
                        select(MatchScore)
                        .where(
                            MatchScore.profile_id == profile.id,
                            MatchScore.score >= settings.MIN_MATCH_SCORE_FOR_DRAFTING,
                            MatchScore.job_id.not_in(existing_draft_job_ids_stmt),
                        )
                        .order_by(MatchScore.score.desc())
                        .limit(remaining_drafts)
                    )
                    top_matches = (await db.execute(qualifying_stmt)).scalars().all()

                    logger.info(
                        f"Found {len(top_matches)} qualifying undrafted jobs "
                        f"(score >= {settings.MIN_MATCH_SCORE_FOR_DRAFTING})"
                    )

                    # 3. Draft applications for each (with company research)
                    for ms in top_matches:
                        if self._drafts_today >= settings.MAX_DRAFTS_PER_DAY:
                            logger.info("Daily draft cap reached mid-run. Stopping.")
                            break

                        # Load the job
                        job = (await db.execute(
                            select(Job).where(Job.id == ms.job_id)
                        )).scalars().first()

                        if not job or job.id in existing_draft_job_ids:
                            continue

                        # Check outreach cap
                        skip_outreach = self._outreach_today >= settings.MAX_OUTREACH_PER_DAY

                        try:
                            await self.drafting_engine.draft_application(
                                db, job, profile, ms,
                                skip_outreach=skip_outreach,
                            )
                            self._drafts_today += 1
                            stats["drafts_created"] += 1

                            if skip_outreach:
                                stats["skipped_outreach"] += 1
                            else:
                                self._outreach_today += 1
                                stats["outreach_created"] += 1

                            existing_draft_job_ids.add(job.id)

                            logger.info(
                                f"Drafted #{stats['drafts_created']}: "
                                f"{job.title} at {job.company} "
                                f"(score: {ms.score:.1f}, "
                                f"outreach: {'skipped' if skip_outreach else 'generated'})"
                            )

                        except Exception as draft_err:
                            logger.error(
                                f"Failed to draft for Job #{job.id}: {draft_err}",
                                exc_info=True,
                            )

                    stats["status"] = "success"
                    stats["drafts_today_total"] = self._drafts_today
                    stats["outreach_today_total"] = self._outreach_today
                    self.last_run_stats = stats
                    logger.info(
                        f"Drafting complete: {stats['drafts_created']} new drafts, "
                        f"{stats['outreach_created']} outreach kits"
                    )

                except Exception as e:
                    logger.error(f"Error during drafting: {e}", exc_info=True)
                    stats["status"] = f"error: {str(e)}"
                    self.last_run_stats = stats
                finally:
                    self.is_running = False

            return self.last_run_stats

    # ──────────────────────────────────────────────────────────────────────────
    # LEGACY: Full pipeline (for backward compat with tests + manual trigger)
    # ──────────────────────────────────────────────────────────────────────────

    async def execute_full_pipeline(self) -> Dict[str, Any]:
        """
        Combined pipeline — runs discovery then drafting in sequence.
        Used for manual triggers and backward compatibility with tests.
        """
        discovery_stats = await self.execute_discovery()
        drafting_stats = await self.execute_drafting()

        # Merge stats
        combined = {
            "new_jobs_found": discovery_stats.get("new_jobs_found", 0),
            "jobs_scored": discovery_stats.get("jobs_scored", 0),
            "drafts_created": drafting_stats.get("drafts_created", 0),
            "status": drafting_stats.get("status", discovery_stats.get("status")),
            "mode": "full_pipeline",
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.last_run_stats = combined
        return combined

    # ──────────────────────────────────────────────────────────────────────────
    # Scheduler Management
    # ──────────────────────────────────────────────────────────────────────────

    def start(self):
        """Start the background APScheduler with three-speed + drafting jobs."""
        if not self.scheduler.running:
            # ── FAST LANE: Free discovery every 15 minutes ────────────────
            self.scheduler.add_job(
                self.execute_discovery,
                IntervalTrigger(minutes=settings.INGESTION_INTERVAL_MINUTES),
                id="discovery_fast_lane",
                replace_existing=True,
            )
            logger.info(
                f"Scheduled FAST LANE (free discovery) every "
                f"{settings.INGESTION_INTERVAL_MINUTES} minutes. "
                f"[LinkedIn Scraper + JobSpy + JSearch + Adzuna + ATS APIs]"
            )

            # ── MEDIUM LANE: Portal crawling every 2 hours ───────────────
            self.scheduler.add_job(
                self.execute_moderate_discovery,
                IntervalTrigger(hours=2),
                id="moderate_portal_crawl",
                replace_existing=True,
            )
            logger.info(
                "Scheduled MEDIUM LANE (portal crawling) every 2 hours. "
                "[Company Portals + Scraper Fallback]"
            )

            # ── APIFY LANE: Once/day at 6 PM IST (12:30 UTC) ─────────────
            # IST 18:00 = UTC 12:30
            self.scheduler.add_job(
                self.execute_apify_scrape,
                CronTrigger(hour=12, minute=30),
                id="apify_daily_6pm_ist",
                replace_existing=True,
            )
            logger.info(
                "Scheduled APIFY LANE at 6:00 PM IST (UTC 12:30) — once/day. "
                "[Cost-guarded: 512MB, 60s timeout, 15 rows max, ~$0.81/month]"
            )

            # ── SLOW LANE: Drafting at configured IST hours ───────────────
            drafting_hours = [
                int(h.strip())
                for h in settings.DRAFTING_SCHEDULE_HOURS.split(",")
                if h.strip().isdigit()
            ]
            for hour in drafting_hours:
                # IST = UTC+5:30, so IST 9:00 = UTC 3:30
                utc_hour = (hour - 5) % 24
                utc_minute = 30  # IST is +5:30 from UTC
                self.scheduler.add_job(
                    self.execute_drafting,
                    CronTrigger(hour=utc_hour, minute=utc_minute),
                    id=f"drafting_slow_lane_{hour}h",
                    replace_existing=True,
                )
                logger.info(
                    f"Scheduled SLOW LANE (drafting) at {hour}:00 IST "
                    f"(UTC {utc_hour}:{utc_minute:02d})"
                )

            self.scheduler.start()

    def stop(self):
        """Stop the background scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Stopped background scheduler.")


scheduler_service = SchedulerService()
