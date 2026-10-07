import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from app.ingestion.base import SourceAdapter, JobPosting
from app.ingestion.constants import (
    is_india_or_remote, is_remote, is_tech_role, is_senior_title,
)

logger = logging.getLogger(__name__)

# ── India-active tech companies using Greenhouse ──────────────────────────────
# Expanded list: 60+ boards covering startups, unicorns, and global tech cos
# with India/Remote hiring presence.
DEFAULT_GREENHOUSE_BOARDS = [
    # ── Indian Unicorns & Startups ─────────────────────────────────────────────
    "razorpay",          # Fintech — Bengaluru
    "postman",           # API tools — Bengaluru HQ
    "swiggy",            # Food-tech — Bengaluru
    "zepto",             # Quick commerce — Mumbai/Bengaluru
    "meesho",            # Social commerce — Bengaluru
    "groww",             # Fintech — Bengaluru
    "browserstack",      # Testing platform — Mumbai
    "hasura",            # GraphQL — Bengaluru
    "clevertap",         # Mobile analytics — Mumbai
    "springworks",       # HR SaaS — Bengaluru
    "phonepe",           # Payments — Bengaluru
    "rupeek",            # Fintech — Bengaluru
    "urbancompany",      # Home services — Gurugram
    "ninjacart",         # Agri-tech — Bengaluru
    "khatabook",         # SMB SaaS — Bengaluru
    "leadsquared",       # CRM SaaS — Bengaluru
    "wingify",           # VWO — testing SaaS — Delhi
    "helpshift",         # Customer support AI — Pune
    "haptik",            # Conversational AI — Mumbai
    "locus-sh",          # Logistics AI — Bengaluru
    "unacademy",         # Ed-tech — Bengaluru
    "smallcase",         # Fintech investing — Bengaluru
    "classplus",         # Ed-tech — Noida
    "innovaccer",        # Health-tech — Noida
    "fynd",              # E-commerce — Mumbai

    # ── Global Companies with India Offices ─────────────────────────────────────
    "github",            # Remote-friendly, hires in India
    "gitlab",            # Fully remote — hires in India
    "hashicorp",         # Remote-first — hires in India
    "canonical",         # Ubuntu/Linux — fully remote
    "dbtlabs",           # Data tools — remote
    "datadog",           # Observability — India offices
    "mongodb",           # Database — Hyderabad
    "figma",             # Design — remote-friendly
    "notion",            # Productivity — remote
    "vercel",            # Frontend cloud — remote
    "supabase",          # Open-source Firebase — remote
    "retool",            # Internal tools — remote
    "netlify",           # Jamstack — remote
    "grafana",           # Observability — remote
    "elastic",           # Search — India offices
    "cockroachlabs",     # Distributed DB — remote
    "planetscale",       # MySQL platform — remote
    "snyk",              # Security — India offices
    "docker",            # Containers — remote
    "airbyte",           # Data integration — remote
    "dagster",           # Data orchestration — remote
    "temporal",          # Workflow engine — remote
    "materialize",       # Streaming DB — remote

    # ── Enterprise with Greenhouse India Boards ──────────────────────────────────
    "atlassian",         # Bengaluru large office
    "freshworks",        # Chennai HQ
    "druva",             # Cloud data — Pune
    "chargebee",         # Billing SaaS — Chennai
    "zoho",              # SaaS suite — Chennai
    "turing",            # Remote dev platform — Palo Alto + India
    "gojek",             # Super-app — Bengaluru
    "grab",              # Ride-hailing — Bengaluru
    "stripe",            # Payments — remote/India
    "twilio",            # Communications — India
    "okta",              # Identity — India offices
    "pagerduty",         # Incident mgmt — India
    "samsara",           # IoT — India
    "servicenow",        # IT workflow — Hyderabad
    "thoughtspot",       # Analytics BI — Bengaluru
]


class GreenhouseAdapter(SourceAdapter):
    """
    Official Greenhouse Job Board API adapter — India-focused.
    API Docs: https://developers.greenhouse.io/job-board.html
    Filters:
      - India-located OR remote/WFH roles
      - CS/Tech/Engineering roles (broad fresher keywords)
      - No hard seniority filter — scoring engine handles prioritization
    """

    def __init__(self, name: str = "greenhouse", config: Optional[Dict[str, Any]] = None):
        super().__init__(name, config)
        self.boards = self.config.get("boards", DEFAULT_GREENHOUSE_BOARDS)
        self.client_headers = {
            "User-Agent": "AIJobFinder-Client/1.0 (Job Matching Review Bot; contact@aijobfinder.local)"
        }

    def _clean_html(self, raw_html: str) -> str:
        if not raw_html:
            return ""
        soup = BeautifulSoup(raw_html, "html.parser")
        return soup.get_text(separator="\n", strip=True)

    async def fetch_board_jobs(
        self, client: httpx.AsyncClient, board: str, since: Optional[datetime] = None
    ) -> List[JobPosting]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
        postings: List[JobPosting] = []
        try:
            resp = await client.get(url, headers=self.client_headers, timeout=15.0)
            if resp.status_code == 404:
                logger.info(f"Greenhouse board not found: {board}")
                return []
            resp.raise_for_status()
            data = resp.json()
            jobs = data.get("jobs", [])

            for j in jobs:
                title = j.get("title", "").strip()

                # ── Filter: Tech roles only (using shared fresher keywords) ────
                if not is_tech_role(title):
                    continue

                # ── NO hard senior filter — let scoring engine handle it ───────
                is_senior = is_senior_title(title)

                updated_at_str = j.get("updated_at")
                posted_date = None
                if updated_at_str:
                    try:
                        posted_date = datetime.fromisoformat(
                            updated_at_str.replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                    except Exception:
                        pass

                if since and posted_date and posted_date < since:
                    continue

                raw_content = j.get("content", "")
                clean_desc = self._clean_html(raw_content)

                location_name = ""
                if isinstance(j.get("location"), dict):
                    location_name = j.get("location", {}).get("name", "")

                # ── Filter: India or Remote only ─────────────────────────────
                if not is_india_or_remote(location_name, title, clean_desc):
                    continue

                apply_url = j.get(
                    "absolute_url",
                    f"https://boards.greenhouse.io/{board}/jobs/{j.get('id')}"
                )
                is_wfh = is_remote(location_name, title, clean_desc)

                # Normalise location label
                if is_wfh and not location_name:
                    location_name = "Remote / Work From Home"

                posting = JobPosting(
                    source_name=self.name,
                    external_id=f"{board}_{j.get('id')}",
                    title=title,
                    company=board.replace("-", " ").title(),
                    location=location_name or "India (Location TBC)",
                    is_remote=is_wfh,
                    description=clean_desc,
                    url=apply_url,
                    posted_date=posted_date,
                    raw_metadata={
                        "board": board,
                        "greenhouse_id": j.get("id"),
                        "departments": j.get("departments", []),
                        "is_senior": is_senior,
                        "work_type": "wfh" if is_wfh else "onsite"
                    }
                )
                postings.append(posting)

        except Exception as e:
            logger.warning(f"Error fetching Greenhouse board '{board}': {e}")

        return postings

    async def fetch_new_postings(self, since: Optional[datetime] = None) -> List[JobPosting]:
        all_postings: List[JobPosting] = []
        async with httpx.AsyncClient() as client:
            for board in self.boards:
                board_postings = await self.fetch_board_jobs(client, board, since)
                all_postings.extend(board_postings)
                logger.info(f"Greenhouse '{board}': {len(board_postings)} India/Remote tech jobs")
        return all_postings
