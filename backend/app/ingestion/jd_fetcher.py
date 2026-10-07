import logging
import asyncio
from typing import Optional, Dict
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# In-memory URL cache to avoid redundant network calls
_JD_CACHE: Dict[str, str] = {}


class JobDescriptionFetcher:
    """
    Asynchronous web fetcher to retrieve full job descriptions from career pages
    when aggregator APIs (like Adzuna or JSearch) provide only short snippets.
    Zero-cost, lightweight (HTTP only, no headless browser or Apify required).
    """

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self.headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def fetch_full_description(self, url: str) -> Optional[str]:
        """
        Fetches the destination URL, follows redirects, and extracts article/body text.
        Returns cleaned text or None if fetch fails.
        """
        if not url or not url.startswith("http"):
            return None

        if url in _JD_CACHE:
            return _JD_CACHE[url]

        try:
            async with httpx.AsyncClient(
                headers=self.headers,
                timeout=self.timeout,
                follow_redirects=True,
                verify=False
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    logger.debug(f"HTTP {resp.status_code} fetching JD from {url}")
                    return None

                soup = BeautifulSoup(resp.text, "html.parser")

                # Remove non-content tags
                for element in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
                    element.decompose()

                # 1. First attempt: Check for schema.org JobPosting JSON-LD
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        import json
                        data = json.loads(script.string or "{}")
                        items = data.get("@graph", [data]) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                        for item in items:
                            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                                desc_html = item.get("description", "")
                                if desc_html:
                                    clean_desc = BeautifulSoup(desc_html, "html.parser").get_text(separator="\n", strip=True)
                                    if len(clean_desc) > 200:
                                        _JD_CACHE[url] = clean_desc
                                        return clean_desc
                    except Exception:
                        pass

                # 2. Second attempt: Check common job description container classes
                job_container = soup.find(class_=lambda c: c and any(term in c.lower() for term in ["job-description", "jobdescription", "description", "content", "job_details"]))
                if job_container:
                    text = job_container.get_text(separator="\n", strip=True)
                    if len(text) > 300:
                        _JD_CACHE[url] = text
                        return text

                # 3. Third attempt: Main or article tags
                main_elem = soup.find("main") or soup.find("article")
                if main_elem:
                    text = main_elem.get_text(separator="\n", strip=True)
                    if len(text) > 300:
                        _JD_CACHE[url] = text
                        return text

                # 4. Fallback to body text
                body_text = soup.body.get_text(separator="\n", strip=True) if soup.body else ""
                lines = [l.strip() for l in body_text.splitlines() if len(l.strip()) > 30]
                text = "\n".join(lines)
                if len(text) > 300:
                    _JD_CACHE[url] = text[:4000]
                    return text[:4000]

        except Exception as e:
            logger.debug(f"Failed to fetch full JD from {url}: {e}")

        return None
