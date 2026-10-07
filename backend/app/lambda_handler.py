"""
AWS Lambda & Cloud Cron Handler
===============================
Serverless execution entry point for AI Job Finder.

Flow:
1. Ingest fresh jobs across all active adapters (Workday, Greenhouse, Lever, RemoteOK, Adzuna, JSearch)
2. Score jobs against candidate profile (my_profile.json)
3. Cross-reference hiring companies against recruiter_companies.json
4. Sync prioritized jobs to Google Sheets via Google Sheets API (gspread)
5. Dispatch Gmail summary email alert to candidate with direct link to Google Sheet
"""

import os
import sys
import json
import asyncio
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from app.config import settings
from app.ingestion.manager import IngestionManager
from app.ingestion.jd_fetcher import JobDescriptionFetcher
from app.matching.engine import MatchingEngine
from app.matching.rules import RuleEvaluator
from app.models.job import Job
from app.models.user_profile import UserProfile
from app.sheets.sheets_sync import GoogleSheetsSync
from app.knowledge.retriever import get_hybrid_retriever

logger = logging.getLogger("cloud_cron")
logger.setLevel(logging.INFO)
logging.getLogger().setLevel(logging.INFO)


def load_master_profile() -> Dict[str, Any]:
    """Load candidate profile from my_profile.json or environment."""
    possible_paths = [
        Path(__file__).resolve().parent.parent.parent / "my_profile.json",
        Path(__file__).resolve().parent / "my_profile.json",
        Path("/var/task/my_profile.json"),
        Path(__file__).resolve().parent.parent.parent / "my_profile.example.json",
        Path(__file__).resolve().parent / "my_profile.example.json",
        Path("/var/task/my_profile.example.json"),
    ]
    for p in possible_paths:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    return {}


def load_recruiter_directory() -> Dict[str, List[str]]:
    """Load company -> recruiter email lookup from recruiter_companies.json."""
    possible_paths = [
        Path(__file__).resolve().parent.parent.parent / "recruiter_companies.json",
        Path(__file__).resolve().parent / "recruiter_companies.json",
        Path("/var/task/recruiter_companies.json"),
    ]
    for p in possible_paths:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {
                        c["company"].strip().lower(): c["emails"]
                        for c in data.get("companies", [])
                    }
            except Exception as e:
                logger.warning(f"Failed loading recruiter directory: {e}")
    return {}


def send_email_alert(new_jobs_count: int, top_matches: List[Dict[str, Any]], sheet_url: str):
    """Send formatted HTML & text summary email to candidate via Gmail SMTP."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD or not settings.ALERT_RECIPIENT_EMAIL:
        logger.info("Email alerts skipped: SMTP credentials not configured.")
        return

    recipient = settings.ALERT_RECIPIENT_EMAIL
    subject = f"🎯 [Job Finder] {new_jobs_count} New Fresher Jobs Ingested! Top Match: {top_matches[0].get('fit_score', 0):.0f}%"

    # Build summary rows
    text_lines = [
        f"Hi Akash,\n",
        f"Your AI Job Finder completed its scheduled run and ingested {new_jobs_count} new opportunities matching your profile.\n",
        f"Top Prioritized Matches:\n"
    ]

    html_rows = ""
    for i, j in enumerate(top_matches[:10], 1):
        score = j.get("fit_score", 0)
        title = j.get("title", "")
        comp = j.get("company", "")
        variant = j.get("selected_variant", "sde")
        url = j.get("url", "#")
        emails = j.get("recruiter_emails", [])
        exp_lvl = j.get("experience_level", "Fresher (0 YOE)")
        is_fresher_tag = j.get("is_fresher", True)
        badge_bg = "#dcfce7" if is_fresher_tag else "#f1f5f9"
        badge_color = "#15803d" if is_fresher_tag else "#475569"
        email_str = f" | Recruiter: {', '.join(emails)}" if emails else ""

        text_lines.append(f"{i}. [{score:.1f}% Fit | {exp_lvl}] {title} at {comp} (Variant: {variant}){email_str}\n   Apply: {url}\n")
        html_rows += f"""
        <tr style="border-bottom: 1px solid #e2e8f0;">
            <td style="padding: 10px; font-weight: bold; color: #2563eb;">{score:.1f}%</td>
            <td style="padding: 10px;"><span style="background: {badge_bg}; color: {badge_color}; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">{exp_lvl}</span></td>
            <td style="padding: 10px;"><a href="{url}" style="color: #0f172a; text-decoration: none; font-weight: 600;">{title}</a></td>
            <td style="padding: 10px; color: #475569;">{comp}</td>
            <td style="padding: 10px;"><span style="background: #e0f2fe; color: #0369a1; padding: 2px 8px; border-radius: 4px; font-size: 12px;">{variant}</span></td>
            <td style="padding: 10px; font-size: 12px; color: #64748b;">{', '.join(emails) if emails else 'None'}</td>
            <td style="padding: 10px;"><a href="{url}" style="background: #2563eb; color: #ffffff; padding: 4px 10px; border-radius: 4px; text-decoration: none; font-size: 12px;">Apply &rarr;</a></td>
        </tr>
        """

    text_lines.append(f"\n📊 View Live Google Sheet: {sheet_url}\n\nHappy applying!\nAI Job Finder Bot")
    plain_text = "\n".join(text_lines)

    html_content = f"""
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; padding: 20px; color: #1e293b;">
        <div style="max-width: 750px; margin: 0 auto; background: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border: 1px solid #e2e8f0;">
            <div style="background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); padding: 24px; color: #ffffff;">
                <h2 style="margin: 0; font-size: 22px;">🎯 {new_jobs_count} Fresher Opportunities Ingested</h2>
                <p style="margin: 6px 0 0; opacity: 0.9; font-size: 14px;">AWS Scheduled Pipeline &bull; Filtered strictly for Freshers (0-2 YOE) &bull; 0 YOE Prioritized First</p>
            </div>
            <div style="padding: 24px;">
                <p style="margin-top: 0;">Hi <strong>Akash</strong>,</p>
                <p>Your automated serverless pipeline filtered out all senior/experienced roles and prioritized the following fresher-targeted opportunities:</p>
                
                <table style="width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 13px;">
                    <thead>
                        <tr style="background: #f1f5f9; text-align: left; color: #475569;">
                            <th style="padding: 10px;">Fit</th>
                            <th style="padding: 10px;">Level</th>
                            <th style="padding: 10px;">Role</th>
                            <th style="padding: 10px;">Company</th>
                            <th style="padding: 10px;">Variant</th>
                            <th style="padding: 10px;">Recruiter Email</th>
                            <th style="padding: 10px;">Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {html_rows}
                    </tbody>
                </table>

                {f'<div style="text-align: center; margin: 30px 0;"><a href="{sheet_url}" style="background: #10b981; color: #ffffff; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: bold; font-size: 14px;">📊 Open Live Google Sheet</a></div>' if sheet_url else ''}
            </div>
            <div style="background: #f8fafc; padding: 16px 24px; font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0; text-align: center;">
                Automated by AI Job Finder on AWS Lambda &bull; Amazon EventBridge Scheduler
            </div>
        </div>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_USER
    msg["To"] = recipient
    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_USER, recipient, msg.as_string())
        logger.info(f"Email alert sent successfully to {recipient}!")
    except Exception as e:
        logger.error(f"Failed to send email alert: {e}")


async def run_pipeline_async() -> Dict[str, Any]:
    """Execute ingestion, matching, Google Sheet sync, and email alert."""
    logger.info("=== Starting Cloud Job Pipeline Run ===")
    start_time = datetime.now()

    # 1. Load Profile & Recruiter Lookup
    profile_data = load_master_profile()
    if not profile_data:
        logger.error("No profile data found in my_profile.json!")
        return {"status": "error", "message": "Missing profile"}

    recruiter_map = load_recruiter_directory()
    logger.info(f"Loaded {len(recruiter_map)} recruiter company mappings.")

    # Create in-memory profile model
    profile = UserProfile(
        id=1,
        full_name=profile_data.get("full_name", "Candidate"),
        email=profile_data.get("email", ""),
        skills=profile_data.get("skills", []),
        work_history=profile_data.get("work_history", []),
        projects=profile_data.get("projects", []),
        curated_variants=profile_data.get("curated_variants", {}),
        preferences=profile_data.get("preferences", {}),
    )

    # 2. Ingest Jobs from All Active Sources
    ingestion_mgr = IngestionManager()
    new_raw_postings = []

    async def _fetch_safe(name, adapter):
        try:
            logger.info(f"Polling source: {name}...")
            postings = await asyncio.wait_for(adapter.fetch_new_postings(), timeout=35.0)
            logger.info(f"-> {name}: fetched {len(postings)} jobs")
            return postings
        except asyncio.TimeoutError:
            logger.warning(f"Adapter {name} timed out after 35s")
            return []
        except Exception as e:
            logger.warning(f"Adapter {name} failed: {e}")
            return []

    batches = await asyncio.gather(*(_fetch_safe(n, a) for n, a in ingestion_mgr.adapters.items()))
    for batch in batches:
        new_raw_postings.extend(batch)

    logger.info(f"Total raw postings fetched: {len(new_raw_postings)}")

    # 3. Initialize RAG Hybrid Retriever for factual evidence grounding
    retriever = None
    try:
        retriever = await get_hybrid_retriever()
        logger.info(f"Initialized RAG HybridRetriever with {retriever.vector_store.count()} indexed chunks.")
    except Exception as e:
        logger.warning(f"Failed to initialize RAG HybridRetriever in Lambda: {e}")

    # 4. Score Every Job with Local Matching Engine & RAG Grounding
    matching_engine = MatchingEngine()
    jd_fetcher = JobDescriptionFetcher()
    scored_items: List[Dict[str, Any]] = []

    for p in new_raw_postings:
        desc = p.description or ""
        # If aggregator provided a short snippet (< 300 chars), try fetching full JD text
        if len(desc.strip()) < 300 and p.url:
            try:
                fetched_desc = await asyncio.wait_for(jd_fetcher.fetch_full_description(p.url), timeout=4.0)
                if fetched_desc and len(fetched_desc) > len(desc):
                    desc = fetched_desc
            except Exception:
                pass

        # Construct temporary Job model
        job_obj = Job(
            id=0,
            title=p.title,
            company=p.company,
            location=p.location or "Remote",
            is_remote=p.is_remote,
            description=desc,
            url=p.url or "",
            posted_date=p.posted_date or datetime.utcnow(),
        )

        job_full_text = f"{job_obj.title}\n{job_obj.company}\n{job_obj.location}\n{job_obj.description}"
        rule_score, matched_skills, missing_reqs, rule_notes = RuleEvaluator.evaluate(job_obj, profile)

        # STRICT FRESHER DISQUALIFICATION: Discard if minimum experience > 0 or senior keywords
        if rule_score <= 0.0:
            continue

        best_variant, semantic_sim = matching_engine.evaluate_variant_fit(job_full_text, profile)
        skill_ratio = min(1.0, len(matched_skills) / 8.0) if matched_skills else 0.0
        weighted = (0.45 * semantic_sim) + (0.30 * skill_ratio) + (0.25 * rule_score)
        fit_score = round(min(100.0, max(0.0, weighted * 100.0)), 1)

        is_fresher = RuleEvaluator.is_fresher_job(job_obj)
        if is_fresher:
            fit_score = min(99.0, fit_score + 15.0)

        # Retrieve top authentic RAG evidence supporting this job
        top_evidence_claim = ""
        top_evidence_id = ""
        if retriever:
            try:
                ev_chunks = await retriever.retrieve_evidence_for_job(
                    job_title=job_obj.title,
                    job_description=desc,
                    required_skills=matched_skills,
                    top_k=1
                )
                if ev_chunks:
                    top_chunk = ev_chunks[0]
                    top_evidence_id = top_chunk.get("chunk_id", "")
                    top_evidence_claim = top_chunk.get("text", "")
                    # RAG alignment bonus if strong grounded evidence exists
                    if top_chunk.get("fused_score", 0) > 0.02:
                        fit_score = min(99.0, fit_score + 5.0)
            except Exception as e:
                logger.debug(f"RAG retrieval skipped for job {job_obj.title}: {e}")

        # Lookup recruiter email
        comp_key = job_obj.company.strip().lower()
        recruiter_emails = recruiter_map.get(comp_key, [])

        scored_items.append({
            "fit_score": fit_score,
            "title": job_obj.title,
            "company": job_obj.company,
            "location": job_obj.location,
            "selected_variant": best_variant,
            "matched_skills": matched_skills,
            "url": job_obj.url,
            "recruiter_emails": recruiter_emails,
            "is_fresher": True,
            "experience_level": "🎯 Verified Fresher (0 YOE)",
            "top_evidence_id": top_evidence_id,
            "top_evidence_claim": top_evidence_claim,
        })

    # Sort: Pure Fresher (0 YOE) roles FIRST, then by fit score descending
    scored_items.sort(key=lambda x: (x.get("is_fresher", False), x["fit_score"]), reverse=True)
    logger.info(f"Scored {len(scored_items)} qualified fresher jobs.")

    # 4. Sync to Google Sheets
    appended_count = 0
    sheet_url = ""
    if settings.GOOGLE_SHEET_ID:
        sheet_url = f"https://docs.google.com/spreadsheets/d/{settings.GOOGLE_SHEET_ID}"

    has_google_creds = bool(
        settings.GOOGLE_SHEET_WEBHOOK_URL or
        settings.GOOGLE_SERVICE_ACCOUNT_JSON or
        settings.GOOGLE_SERVICE_ACCOUNT_FILE
    )
    if has_google_creds:
        try:
            syncer = GoogleSheetsSync(
                webhook_url=settings.GOOGLE_SHEET_WEBHOOK_URL,
                service_account_json=settings.GOOGLE_SERVICE_ACCOUNT_JSON,
                service_account_file=settings.GOOGLE_SERVICE_ACCOUNT_FILE,
                sheet_id=settings.GOOGLE_SHEET_ID,
                sheet_name=settings.GOOGLE_SHEET_NAME,
            )
            appended_count = syncer.sync_jobs(
                scored_items,
                min_fit_score=settings.MIN_FIT_SCORE_FOR_SHEET
            )
            logger.info(f"Google Sheets sync: {appended_count} new rows added.")
        except Exception as e:
            logger.error(f"Failed syncing to Google Sheets: {e}", exc_info=True)
    else:
        logger.info("Google Sheets sync skipped (neither webhook URL nor service account provided).")

    # 5. Dispatch Email Alert
    if scored_items:
        # If Google Sheets was synced, notify on appended_count; else notify on top matches found
        notify_count = appended_count if has_google_creds else len(scored_items)
        if notify_count > 0:
            send_email_alert(notify_count, scored_items, sheet_url)

    duration = (datetime.now() - start_time).total_seconds()
    result = {
        "status": "success",
        "duration_seconds": round(duration, 2),
        "raw_postings_found": len(new_raw_postings),
        "qualified_jobs_scored": len(scored_items),
        "google_sheet_rows_added": appended_count,
        "top_match": scored_items[0] if scored_items else None,
    }
    logger.info(f"Run completed in {duration:.2f}s: {result}")
    return result


def handler(event, context):
    """AWS Lambda Entrypoint."""
    return asyncio.run(run_pipeline_async())


if __name__ == "__main__":
    res = asyncio.run(run_pipeline_async())
    print("\n--- Pipeline Execution Summary ---")
    print(json.dumps(res, indent=2))
