"""
Google Sheets Synchronizer
==========================
Synchronizes prioritized job postings to a live Google Sheet.

Supports two connection methods:
1. Webhook (Recommended) — Google Apps Script Webhook (Zero GCP setup, zero IAM restrictions)
2. Service Account — gspread with service_account.json
"""

import json
import base64
import logging
from typing import List, Dict, Any, Set, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

HEADERS = [
    "Date Added",
    "Fit Score",
    "Job Title",
    "Company",
    "Location",
    "Best Variant",
    "Matched Skills",
    "Apply URL",
    "Recruiter Email(s)",
    "Status"
]


class GoogleSheetsSync:
    def __init__(
        self,
        webhook_url: Optional[str] = None,
        service_account_json: Optional[str] = None,
        service_account_file: Optional[str] = None,
        sheet_id: Optional[str] = None,
        sheet_name: Optional[str] = None,
    ):
        self.webhook_url = webhook_url
        self.service_account_json = service_account_json
        self.service_account_file = service_account_file
        self.sheet_id = sheet_id
        self.sheet_name = sheet_name or "AI Job Finder - Opportunities"
        self._client = None
        self._worksheet = None

    def _get_client(self):
        """Authenticate with Google Sheets API via gspread."""
        if self._client:
            return self._client

        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]

        if self.service_account_json:
            raw = self.service_account_json.strip()
            if not raw.startswith("{"):
                try:
                    raw = base64.b64decode(raw).decode("utf-8")
                except Exception:
                    pass
            creds_data = json.loads(raw)
            credentials = Credentials.from_service_account_info(creds_data, scopes=scopes)
        elif self.service_account_file:
            credentials = Credentials.from_service_account_file(self.service_account_file, scopes=scopes)
        else:
            raise ValueError(
                "Neither webhook_url, GOOGLE_SERVICE_ACCOUNT_JSON, nor GOOGLE_SERVICE_ACCOUNT_FILE was provided."
            )

        self._client = gspread.authorize(credentials)
        return self._client

    def _get_worksheet(self):
        """Open target spreadsheet and worksheet via gspread."""
        if self._worksheet:
            return self._worksheet

        client = self._get_client()

        if self.sheet_id:
            sh = client.open_by_key(self.sheet_id)
        else:
            sh = client.open(self.sheet_name)

        try:
            ws = sh.sheet1
        except Exception:
            ws = sh.add_worksheet(title="Opportunities", rows=1000, cols=len(HEADERS))

        existing_rows = ws.get_all_values()
        if not existing_rows or not existing_rows[0]:
            logger.info("Initializing Google Sheet header row...")
            ws.append_row(HEADERS)
            try:
                ws.format("A1:J1", {"textFormat": {"bold": True}})
            except Exception as e:
                logger.debug(f"Could not format header: {e}")

        self._worksheet = ws
        return ws

    def get_existing_urls(self) -> Set[str]:
        """Fetch all existing Apply URLs in the sheet for deduplication."""
        try:
            ws = self._get_worksheet()
            col_vals = ws.col_values(8) # Column H is 'Apply URL'
            return set(u.strip() for u in col_vals[1:] if u.strip())
        except Exception as e:
            logger.warning(f"Could not read existing URLs from Google Sheet: {e}")
            return set()

    def sync_jobs(
        self,
        scored_jobs: List[Dict[str, Any]],
        min_fit_score: float = 35.0,
    ) -> int:
        """
        Append newly discovered scored jobs to Google Sheets.
        Supports both Google Apps Script Webhook and gspread service account.
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        # ── Method 1: Google Apps Script Webhook ──
        if self.webhook_url:
            import httpx
            rows_data = []
            for item in scored_jobs:
                score = float(item.get("fit_score", 0.0))
                if score < min_fit_score:
                    continue
                url = (item.get("url") or "").strip()
                if not url:
                    continue
                skills_str = ", ".join(item.get("matched_skills", []))
                emails = item.get("recruiter_emails", [])
                emails_str = ", ".join(emails) if isinstance(emails, list) else str(emails)
                rows_data.append([
                    now_str,
                    f"{score:.1f}%",
                    item.get("title", ""),
                    item.get("company", ""),
                    item.get("location", "India / Remote"),
                    f"{item.get('selected_variant', 'sde')} | {item.get('experience_level', 'Fresher (0 YOE)')}",
                    skills_str,
                    url,
                    emails_str,
                    f"New ({item.get('experience_level', 'Fresher')})"
                ])

            if not rows_data:
                logger.info("No jobs meeting minimum fit score for Google Sheets.")
                return 0

            try:
                logger.info(f"Sending {len(rows_data)} jobs to Google Apps Script Webhook...")
                resp = httpx.post(
                    self.webhook_url,
                    json={"rows": rows_data},
                    timeout=30.0,
                    follow_redirects=True,
                )
                if resp.status_code == 200:
                    try:
                        res_json = resp.json()
                        added = res_json.get("rows_added", len(rows_data))
                    except Exception:
                        added = len(rows_data)
                    logger.info(f"Google Sheets Webhook appended {added} rows successfully.")
                    return added
                else:
                    logger.error(f"Google Sheets Webhook returned HTTP {resp.status_code}: {resp.text[:200]}")
                    return 0
            except Exception as e:
                logger.error(f"Error calling Google Sheets webhook: {e}")
                return 0

        # ── Method 2: gspread via Service Account ──
        existing_urls = self.get_existing_urls()
        rows_to_append = []
        for item in scored_jobs:
            score = float(item.get("fit_score", 0.0))
            if score < min_fit_score:
                continue

            url = (item.get("url") or "").strip()
            if not url or url in existing_urls:
                continue

            skills_str = ", ".join(item.get("matched_skills", []))
            emails = item.get("recruiter_emails", [])
            emails_str = ", ".join(emails) if isinstance(emails, list) else str(emails)

            rows_to_append.append([
                now_str,
                f"{score:.1f}%",
                item.get("title", ""),
                item.get("company", ""),
                item.get("location", "India / Remote"),
                f"{item.get('selected_variant', 'sde')} | {item.get('experience_level', 'Fresher (0 YOE)')}",
                skills_str,
                url,
                emails_str,
                f"New ({item.get('experience_level', 'Fresher')})"
            ])
            existing_urls.add(url)

        if not rows_to_append:
            logger.info("No new jobs to append to Google Sheets.")
            return 0

        ws = self._get_worksheet()
        logger.info(f"Appending {len(rows_to_append)} new jobs to Google Sheets via gspread...")
        ws.append_rows(rows_to_append, value_input_option="USER_ENTERED")
        return len(rows_to_append)
