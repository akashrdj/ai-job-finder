import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from app.config import settings
from app.models.job import Job
from app.models.match_score import MatchScore
from app.models.application_draft import ApplicationDraft

logger = logging.getLogger(__name__)

class EmailNotifier:
    """
    Sends real-time Gmail alerts for high-fit job matches.
    Uses 0 LLM tokens via standard SMTP.
    """

    @classmethod
    async def send_new_match_alert(cls, job: Job, match_score: MatchScore, draft: ApplicationDraft) -> bool:
        if not settings.ENABLE_EMAIL_ALERTS or not settings.SMTP_USER or not settings.SMTP_PASSWORD:
            return False

        recipient = settings.ALERT_RECIPIENT_EMAIL or settings.SMTP_USER

        subject = f"🎯 [Job Match: {match_score.score}%] {job.title} at {job.company}"
        
        body_text = f"""New High-Fit Job Match Found!

Role: {job.title}
Company: {job.company}
Location: {job.location or 'Not specified'} (Remote: {job.is_remote})
Match Score: {match_score.score}/100
Selected Profile: {match_score.selected_variant.upper()}

Direct Apply Link:
{job.url}

--- Tailored Cover Letter ---
{draft.cover_letter}

--- Why This Matched ---
{match_score.rationale}

Log in to your AI Job Finder Review Queue to inspect the full resume diff and outreach kit.
"""

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_USER
        msg["To"] = recipient
        msg.attach(MIMEText(body_text, "plain"))

        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                server.starttls()
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.SMTP_USER, recipient, msg.as_string())
            logger.info(f"Successfully sent email alert for job {job.id} to {recipient}")
            return True
        except Exception as e:
            logger.warning(f"Failed to send email alert: {e}")
            return False
