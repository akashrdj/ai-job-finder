import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from app.ingestion.base import SourceAdapter, JobPosting
from app.ingestion.constants import (
    is_tech_role, is_senior_title,
)

logger = logging.getLogger(__name__)

# ── RemoteOK: Global remote board — all jobs accessible from India ────────────
# We tag ALL RemoteOK jobs as WFH = True.
# Uses shared tech role keywords for broad fresher-inclusive matching.

TECH_TAGS = {
    "python", "javascript", "typescript", "react", "node.js", "nodejs",
    "java", "golang", "go", "rust", "ruby", "php", "swift", "kotlin",
    "backend", "frontend", "fullstack", "devops", "cloud", "aws", "gcp",
    "azure", "docker", "kubernetes", "machine-learning", "ai", "nlp",
    "deep-learning", "data", "sql", "postgres", "mongodb", "redis",
    "fastapi", "django", "flask", "next.js", "vue", "angular", "mobile",
    "android", "ios", "engineer", "developer", "software"
}


def _is_tech_role_with_tags(title: str, tags: list) -> bool:
    """Check if role is tech-related using both title keywords and tags."""
    has_tech_title = is_tech_role(title)
    has_tech_tag = bool(TECH_TAGS.intersection({t.lower() for t in tags}))
    return has_tech_title or has_tech_tag


class RemoteOKAdapter(SourceAdapter):
    """
    Official RemoteOK Public API adapter.
    Endpoint: https://remoteok.com/api
    ALL jobs here are remote (WFH) — accessible from India.
    Filters: Tech/CS roles only. No hard seniority filter.
    """

    def __init__(self, name: str = "remoteok", config: Optional[Dict[str, Any]] = None):
        super().__init__(name, config)
        self.api_url = "https://remoteok.com/api"
        self.client_headers = {
            "User-Agent": "AIJobFinder-Client/1.0 (Job Matching Review Bot; contact@aijobfinder.local)"
        }

    def _clean_html(self, raw_html: str) -> str:
        if not raw_html:
            return ""
        soup = BeautifulSoup(raw_html, "html.parser")
        return soup.get_text(separator="\n", strip=True)

    async def fetch_new_postings(self, since: Optional[datetime] = None) -> List[JobPosting]:
        postings: List[JobPosting] = []
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(self.api_url, headers=self.client_headers, timeout=20.0)
                resp.raise_for_status()
                data = resp.json()

                # First element in RemoteOK array is legal/disclaimer — skip it
                job_items = [
                    item for item in data
                    if isinstance(item, dict) and "id" in item
                ]

                for item in job_items:
                    title = item.get("position", "")
                    tags = item.get("tags", [])

                    # ── Filter: Tech roles only (title + tags) ─────────────────
                    if not _is_tech_role_with_tags(title, tags):
                        continue

                    # ── NO hard senior filter — flag for scoring ───────────────
                    is_senior = is_senior_title(title)

                    posted_date = None
                    date_str = item.get("date")
                    if date_str:
                        try:
                            posted_date = datetime.fromisoformat(
                                date_str.replace("Z", "+00:00")
                            ).replace(tzinfo=None)
                        except Exception:
                            pass

                    if since and posted_date and posted_date < since:
                        continue

                    company = item.get("company", "Remote Company")
                    raw_desc = item.get("description", "")
                    clean_desc = self._clean_html(raw_desc)
                    if tags:
                        clean_desc = f"Tech Stack: {', '.join(tags)}\n\n" + clean_desc

                    url = (
                        item.get("url")
                        or f"https://remoteok.com/remote-jobs/{item.get('id')}"
                    )

                    salary_min = item.get("salary_min")
                    salary_max = item.get("salary_max")

                    # RemoteOK location field: "Worldwide", "USA only", blank, etc.
                    raw_location = item.get("location") or "Worldwide / Remote"
                    display_location = "Remote / Work From Home (Worldwide)"
                    if raw_location and raw_location.lower() not in ("", "worldwide", "anywhere"):
                        display_location = f"Remote — {raw_location}"

                    posting = JobPosting(
                        source_name=self.name,
                        external_id=str(item.get("id")),
                        title=title,
                        company=company,
                        location=display_location,
                        is_remote=True,  # ALL RemoteOK jobs are WFH
                        description=clean_desc,
                        url=url,
                        salary_min=float(salary_min) if salary_min else None,
                        salary_max=float(salary_max) if salary_max else None,
                        salary_currency="USD",
                        posted_date=posted_date,
                        raw_metadata={
                            "tags": tags,
                            "remoteok_id": item.get("id"),
                            "is_senior": is_senior,
                            "work_type": "wfh"
                        }
                    )
                    postings.append(posting)

        except Exception as e:
            logger.warning(f"Error fetching RemoteOK API: {e}")

        logger.info(f"RemoteOK: {len(postings)} WFH tech jobs (accessible from India)")
        return postings
