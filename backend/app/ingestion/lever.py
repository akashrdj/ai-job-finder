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

# ── India-active companies using Lever ────────────────────────────────────────
# Expanded list: 40+ companies with India/Remote hiring on Lever.
DEFAULT_LEVER_COMPANIES = [
    # ── Indian Startups & Unicorns ─────────────────────────────────────────────
    "razorpay",          # Fintech — Bengaluru
    "swiggy",            # Food-tech — Bengaluru
    "cred",              # Fintech — Bengaluru
    "zepto",             # Quick commerce — Mumbai
    "meesho",            # Social commerce — Bengaluru
    "groww",             # Fintech investments — Bengaluru
    "inmobi",            # Ad tech — Bengaluru
    "browserstack",      # Testing SaaS — Mumbai
    "postman",           # API tooling — Bengaluru
    "cashfree",          # Payments — Bengaluru
    "khatabook",         # SMB SaaS — Bengaluru
    "slice",             # Fintech — Bengaluru
    "navi",              # Fintech — Bengaluru
    "paytm",             # Payments — Noida
    "moengage",          # Customer engagement — Mumbai
    "zinier",            # Field service — Bengaluru
    "sarvam",            # AI — Bengaluru
    "yellow-ai",         # Conversational AI — Bengaluru
    "simpplr",           # Intranet SaaS — Bengaluru
    "rocketlane",        # Project mgmt — Chennai
    "blinkit",           # Quick commerce — Gurugram
    "darwinbox",         # HR SaaS — Hyderabad
    "capillarytech",     # Retail tech — Bengaluru

    # ── Global Companies with India/Remote Hiring ──────────────────────────────
    "scale",             # AI data — US, hires India remote
    "benchling",         # Life sciences SaaS — remote-friendly
    "linear",            # Project mgmt — fully remote
    "coinbase",          # Crypto — remote/India
    "stripe",            # Payments — remote
    "ramp",              # Fintech — remote
    "plaid",             # Fintech infra — remote
    "deel",              # HR global — remote
    "loom",              # Video — remote
    "rippling",          # HR tech — India office
    "anyscale",          # Ray ML — remote
    "weights-and-biases", # ML platform — remote
    "labelbox",          # ML data — remote
    "replit",            # Cloud IDE — remote
    "sourcegraph",       # Code search — remote
    "posthog",           # Analytics — remote
    "cal-com",           # Scheduling — remote
    "langchain",         # LLM framework — remote
    "huggingface",       # ML/AI — remote
]


class LeverAdapter(SourceAdapter):
    """
    Official Lever Postings API adapter — India-focused.
    API: https://api.lever.co/v0/postings/{company}?mode=json
    Filters:
      - India-located OR remote/WFH roles
      - Tech/CS roles only (broad fresher keywords)
      - No hard seniority filter — scoring engine handles prioritization
    """

    def __init__(self, name: str = "lever", config: Optional[Dict[str, Any]] = None):
        super().__init__(name, config)
        self.companies = self.config.get("companies", DEFAULT_LEVER_COMPANIES)
        self.client_headers = {
            "User-Agent": "AIJobFinder-Client/1.0 (Job Matching Review Bot; contact@aijobfinder.local)"
        }

    def _clean_html(self, raw_html: str) -> str:
        if not raw_html:
            return ""
        soup = BeautifulSoup(raw_html, "html.parser")
        return soup.get_text(separator="\n", strip=True)

    async def fetch_company_jobs(
        self, client: httpx.AsyncClient, company: str, since: Optional[datetime] = None
    ) -> List[JobPosting]:
        url = f"https://api.lever.co/v0/postings/{company}?mode=json"
        postings: List[JobPosting] = []
        try:
            resp = await client.get(url, headers=self.client_headers, timeout=15.0)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            jobs = resp.json()
            if not isinstance(jobs, list):
                return []

            for j in jobs:
                title = j.get("text", "").strip()

                # ── Filter: Tech roles only (using shared fresher keywords) ────
                if not is_tech_role(title):
                    continue

                # ── NO hard senior filter — let scoring engine handle it ───────
                is_senior = is_senior_title(title)

                created_at_ms = j.get("createdAt")
                posted_date = None
                if created_at_ms:
                    try:
                        posted_date = datetime.utcfromtimestamp(created_at_ms / 1000.0)
                    except Exception:
                        pass

                if since and posted_date and posted_date < since:
                    continue

                categories = j.get("categories", {})
                location = categories.get("location", "Not Specified")
                workplace_type = j.get("workplaceType", "")

                # ── Build description ─────────────────────────────────────────
                desc_parts = [self._clean_html(j.get("descriptionPlain", ""))]
                for lst in j.get("lists", []):
                    desc_parts.append(f"\n{lst.get('text', '')}:")
                    desc_parts.append(self._clean_html(lst.get("content", "")))
                full_desc = "\n".join(filter(None, desc_parts))

                # ── Filter: India or Remote only ─────────────────────────────
                if not is_india_or_remote(location, title, full_desc):
                    continue

                is_wfh = is_remote(location, title, full_desc) or workplace_type.lower() in ("remote", "hybrid")
                if is_wfh and location in ("Not Specified", ""):
                    location = "Remote / Work From Home"

                posting = JobPosting(
                    source_name=self.name,
                    external_id=f"{company}_{j.get('id')}",
                    title=title,
                    company=company.title(),
                    location=location,
                    is_remote=is_wfh,
                    description=full_desc,
                    url=j.get("hostedUrl", ""),
                    posted_date=posted_date,
                    raw_metadata={
                        "company": company,
                        "lever_id": j.get("id"),
                        "team": categories.get("team"),
                        "is_senior": is_senior,
                        "work_type": "wfh" if is_wfh else "onsite"
                    }
                )
                postings.append(posting)

        except Exception as e:
            logger.warning(f"Error fetching Lever company '{company}': {e}")

        return postings

    async def fetch_new_postings(self, since: Optional[datetime] = None) -> List[JobPosting]:
        all_postings: List[JobPosting] = []
        async with httpx.AsyncClient() as client:
            for company in self.companies:
                jobs = await self.fetch_company_jobs(client, company, since)
                all_postings.extend(jobs)
                logger.info(f"Lever '{company}': {len(jobs)} India/Remote tech jobs")
        return all_postings
