"""
Cold Outreach Pipeline — Standalone Runner
============================================
Run the full pipeline from command line without starting the FastAPI server.

Usage:
    # Step 1: Enrich all freshers companies
    python run_outreach_pipeline.py enrich --source freshers --limit 10

    # Step 2: Generate AI cold email drafts
    python run_outreach_pipeline.py draft --limit 5

    # Step 3: Review drafts (prints to console)
    python run_outreach_pipeline.py review

    # Step 4: Send approved drafts
    python run_outreach_pipeline.py send --ids 1,2,3

    # Full pipeline
    python run_outreach_pipeline.py full --source freshers --limit 5
"""
import asyncio
import argparse
import json
import logging
import sys
from pathlib import Path

# Add backend to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app.database import init_db, AsyncSessionLocal
from app.models.company_contact import CompanyContact
from app.outreach.excel_ingestion import load_all_companies
from app.outreach.contact_enrichment import (
    enrich_company_contacts,
    enrich_batch,
    guess_domain,
    generate_linkedin_search_links,
)
from app.outreach.cold_email_drafter import generate_cold_email_draft, generate_batch_drafts
from app.config import settings
from sqlalchemy import select, func

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("outreach_pipeline")


def _load_profile() -> dict:
    profile_path = Path(__file__).resolve().parent / "my_profile.json"
    if not profile_path.exists():
        example_path = Path(__file__).resolve().parent / "my_profile.example.json"
        if example_path.exists():
            logger.warning("my_profile.json not found! Falling back to my_profile.example.json.")
            profile_path = example_path
        else:
            raise FileNotFoundError(f"Neither {profile_path} nor {example_path} was found.")
    with open(profile_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ──────────────────────────────────────────────────────────────────
# Commands
# ──────────────────────────────────────────────────────────────────

async def cmd_enrich(args):
    """Enrich companies from Excel sheets."""
    await init_db()

    all_companies = load_all_companies()

    if args.source == "freshers":
        companies = [c for c in all_companies if c.get("source_sheet") == "freshers"]
    elif args.source == "master":
        companies = [c for c in all_companies if c.get("source_sheet") == "master"]
    else:
        companies = all_companies

    if args.limit:
        companies = companies[:args.limit]

    print(f"\n{'='*60}")
    print(f"  ENRICHING {len(companies)} COMPANIES")
    print(f"  Source: {args.source} | Hunter: {'YES' if settings.HUNTER_API_KEY else 'NO'}")
    print(f"{'='*60}\n")

    async with AsyncSessionLocal() as db:
        # First, save existing emails from master sheet
        for comp in companies:
            for email in comp.get("existing_emails", []):
                existing = await db.execute(
                    select(CompanyContact).where(
                        CompanyContact.company_name == comp["company_name"],
                        CompanyContact.contact_email == email,
                    )
                )
                if not existing.scalars().first():
                    contact = CompanyContact(
                        company_name=comp["company_name"],
                        company_domain=guess_domain(comp["company_name"]),
                        industry=comp.get("industry", ""),
                        contact_email=email,
                        source="master_sheet",
                        confidence=60,
                        fresher_role=comp.get("fresher_role"),
                        opening_period=comp.get("opening_period"),
                        target_contact_type=comp.get("target_contact_type"),
                    )
                    db.add(contact)
            await db.commit()

        # Run enrichment cascade
        results = await enrich_batch(companies)

        total_saved = 0
        for result in results:
            for cd in result["contacts"]:
                existing = await db.execute(
                    select(CompanyContact).where(
                        CompanyContact.company_name == result["company_name"],
                        CompanyContact.contact_email == cd["contact_email"],
                    )
                )
                if existing.scalars().first():
                    continue

                contact = CompanyContact(
                    company_name=result["company_name"],
                    company_domain=result["domain"],
                    industry=cd.get("industry", ""),
                    contact_name=cd.get("contact_name", ""),
                    contact_email=cd["contact_email"],
                    contact_role=cd.get("contact_role", ""),
                    contact_title=cd.get("contact_title", ""),
                    linkedin_url=cd.get("linkedin_url", ""),
                    source=cd.get("source", "unknown"),
                    confidence=cd.get("confidence"),
                    is_verified=cd.get("is_verified", False),
                    verification_status=cd.get("verification_status", "unknown"),
                    fresher_role=cd.get("fresher_role"),
                    opening_period=cd.get("opening_period"),
                    target_contact_type=cd.get("target_contact_type"),
                )
                db.add(contact)
                total_saved += 1

            # Print per-company summary
            print(f"  [OK] {result['company_name']:<25} | {result['domain']:<25} | "
                  f"{result['contact_count']} contacts | sources: {', '.join(result['sources_used'])}")
            print(f"    LinkedIn: {result['linkedin_search_links']['search_recruiters'][:80]}...")

        await db.commit()

    print(f"\n{'='*60}")
    print(f"  DONE: {len(results)} companies processed, {total_saved} new contacts saved")
    print(f"{'='*60}\n")


async def cmd_draft(args):
    """Generate AI cold email drafts."""
    await init_db()
    profile = _load_profile()

    async with AsyncSessionLocal() as db:
        query = (
            select(CompanyContact)
            .where(CompanyContact.cold_email_status == "pending")
            .order_by(CompanyContact.confidence.desc())
            .limit(args.limit)
        )
        result = await db.execute(query)
        contacts = result.scalars().all()

        if not contacts:
            print("\n  No pending contacts found. Run 'enrich' first.\n")
            return

        print(f"\n{'='*60}")
        print(f"  GENERATING {len(contacts)} COLD EMAIL DRAFTS")
        print(f"{'='*60}\n")

        contact_dicts = [
            {
                "id": c.id,
                "company_name": c.company_name,
                "company_domain": c.company_domain,
                "industry": c.industry or "",
                "contact_name": c.contact_name or "",
                "contact_email": c.contact_email,
                "contact_role": c.contact_role or "",
                "contact_title": c.contact_title or "",
                "fresher_role": c.fresher_role or "Software Engineer",
                "opening_period": c.opening_period or "",
            }
            for c in contacts
        ]

        drafts = await generate_batch_drafts(profile, contact_dicts, max_drafts=args.limit)

        for draft, contact in zip(drafts, contacts):
            contact.cold_email_subject = draft.get("subject", "")
            contact.cold_email_body = draft.get("body", "")
            contact.cold_email_status = "draft_ready"

            print(f"  [OK] Draft #{contact.id}: {contact.company_name} -> {contact.contact_email}")
            print(f"    Subject: {draft.get('subject', '')[:70]}")
            print()

        await db.commit()

    print(f"\n  Generated {len(drafts)} drafts. Run 'review' to inspect them.\n")


async def cmd_review(args):
    """Review all draft-ready cold emails."""
    await init_db()

    async with AsyncSessionLocal() as db:
        query = (
            select(CompanyContact)
            .where(CompanyContact.cold_email_status == "draft_ready")
            .order_by(CompanyContact.company_name)
        )
        result = await db.execute(query)
        contacts = result.scalars().all()

        if not contacts:
            print("\n  No drafts to review. Run 'draft' first.\n")
            return

        print(f"\n{'='*70}")
        print(f"  {len(contacts)} COLD EMAIL DRAFTS READY FOR REVIEW")
        print(f"{'='*70}")

        for c in contacts:
            print(f"\n{'-'*70}")
            print(f"  ID: {c.id} | Company: {c.company_name} | Role: {c.contact_role}")
            print(f"  To: {c.contact_email} | Confidence: {c.confidence}")
            print(f"  Source: {c.source} | Verified: {c.is_verified}")
            print(f"{'-'*70}")
            print(f"  Subject: {c.cold_email_subject}")
            print(f"\n{c.cold_email_body}")
            print()

        print(f"\n  To approve: python run_outreach_pipeline.py approve --ids {','.join(str(c.id) for c in contacts[:5])}")
        print(f"  To send:    python run_outreach_pipeline.py send --ids <approved_ids>\n")


async def cmd_approve(args):
    """Approve specific drafts for sending."""
    await init_db()

    ids = [int(x.strip()) for x in args.ids.split(",")]

    async with AsyncSessionLocal() as db:
        from sqlalchemy import update
        await db.execute(
            update(CompanyContact)
            .where(CompanyContact.id.in_(ids))
            .values(cold_email_status="approved")
        )
        await db.commit()

    print(f"\n  [OK] Approved {len(ids)} drafts. Run 'send --ids {args.ids}' to dispatch.\n")


async def cmd_send(args):
    """Send approved cold emails via Gmail SMTP."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from datetime import datetime

    await init_db()

    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        print("\n  [ERR] SMTP credentials not set in .env. Add SMTP_USER and SMTP_PASSWORD.\n")
        return

    ids = [int(x.strip()) for x in args.ids.split(",")]

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CompanyContact).where(
                CompanyContact.id.in_(ids),
                CompanyContact.cold_email_status.in_(["approved", "draft_ready"]),
            )
        )
        contacts = result.scalars().all()

        if not contacts:
            print("\n  No approved drafts found for the given IDs.\n")
            return

        print(f"\n  Sending {len(contacts)} emails via {settings.SMTP_HOST}...\n")

        sent = 0
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)

            for c in contacts:
                try:
                    msg = MIMEMultipart()
                    msg["From"] = settings.SMTP_USER
                    msg["To"] = c.contact_email
                    msg["Subject"] = c.cold_email_subject
                    msg.attach(MIMEText(c.cold_email_body, "plain"))

                    server.sendmail(settings.SMTP_USER, c.contact_email, msg.as_string())

                    c.cold_email_status = "sent"
                    c.cold_email_sent_at = datetime.utcnow()
                    sent += 1
                    print(f"  [OK] Sent to {c.contact_email} ({c.company_name})")

                except Exception as e:
                    c.cold_email_status = "bounced"
                    print(f"  [ERR] Failed: {c.contact_email} -- {e}")

        await db.commit()

    print(f"\n  Done: {sent}/{len(contacts)} emails sent successfully.\n")


async def cmd_stats(args):
    """Show outreach pipeline statistics."""
    await init_db()

    async with AsyncSessionLocal() as db:
        total = (await db.execute(select(func.count(CompanyContact.id)))).scalar()
        companies = (await db.execute(
            select(func.count(func.distinct(CompanyContact.company_name)))
        )).scalar()

        print(f"\n{'='*50}")
        print(f"  OUTREACH PIPELINE STATS")
        print(f"{'='*50}")
        print(f"  Total contacts:     {total}")
        print(f"  Unique companies:   {companies}")

        for status in ["pending", "draft_ready", "approved", "sent", "replied", "bounced"]:
            count = (await db.execute(
                select(func.count(CompanyContact.id))
                .where(CompanyContact.cold_email_status == status)
            )).scalar()
            marker = {"pending": "[ ]", "draft_ready": "[D]", "approved": "[A]",
                     "sent": "[S]", "replied": "[R]", "bounced": "[X]"}.get(status, " - ")
            print(f"  {marker} {status:<15} {count}")

        print(f"{'='*50}\n")


async def cmd_full(args):
    """Run the full pipeline: enrich → draft → review."""
    await cmd_enrich(args)
    await cmd_draft(args)
    await cmd_review(args)


async def cmd_linkedin(args):
    """Generate LinkedIn search links for a company."""
    links = generate_linkedin_search_links(args.company)
    print(f"\n  LinkedIn Search Links for: {args.company}")
    print(f"  {'-'*50}")
    for name, url in links.items():
        print(f"  {name}: {url}")
    print()


# ──────────────────────────────────────────────────────────────────
# CLI Entry Point
# ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Cold Outreach Pipeline — Find contacts & send personalized cold emails"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # enrich
    p_enrich = subparsers.add_parser("enrich", help="Enrich company contacts from Excel sheets")
    p_enrich.add_argument("--source", default="freshers", choices=["freshers", "master", "all"])
    p_enrich.add_argument("--limit", type=int, default=None)

    # draft
    p_draft = subparsers.add_parser("draft", help="Generate AI cold email drafts")
    p_draft.add_argument("--limit", type=int, default=5)

    # review
    subparsers.add_parser("review", help="Review draft-ready cold emails")

    # approve
    p_approve = subparsers.add_parser("approve", help="Approve drafts for sending")
    p_approve.add_argument("--ids", required=True, help="Comma-separated contact IDs")

    # send
    p_send = subparsers.add_parser("send", help="Send approved cold emails via Gmail SMTP")
    p_send.add_argument("--ids", required=True, help="Comma-separated contact IDs")

    # stats
    subparsers.add_parser("stats", help="Show pipeline statistics")

    # full
    p_full = subparsers.add_parser("full", help="Run full pipeline: enrich → draft → review")
    p_full.add_argument("--source", default="freshers", choices=["freshers", "master", "all"])
    p_full.add_argument("--limit", type=int, default=5)

    # linkedin
    p_li = subparsers.add_parser("linkedin", help="Generate LinkedIn search links")
    p_li.add_argument("--company", required=True)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    cmd_map = {
        "enrich": cmd_enrich,
        "draft": cmd_draft,
        "review": cmd_review,
        "approve": cmd_approve,
        "send": cmd_send,
        "stats": cmd_stats,
        "full": cmd_full,
        "linkedin": cmd_linkedin,
    }

    asyncio.run(cmd_map[args.command](args))


if __name__ == "__main__":
    main()
