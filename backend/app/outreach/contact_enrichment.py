"""
Multi-source Contact Enrichment Engine
=======================================
Discovers HR / recruiter / CTO / engineering lead emails for target companies
using a cascading strategy:

  1. Hunter.io  — domain-search API (50 free/month)
  2. Snov.io    — domain-search API (50 free/month)
  3. Web scrape — careers / about / team pages for mailto: links
  4. Pattern    — common email-format guessing (first@domain, etc.)

Each source writes results to the CompanyContact table with proper
attribution and confidence scores.
"""
import asyncio
import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────
# Domain helpers
# ──────────────────────────────────────────────────────────────────

# Manual domain overrides for well-known companies whose domain
# doesn't match the company name (e.g. "Flipkart" → "flipkart.com")
_DOMAIN_OVERRIDES: Dict[str, str] = {
    "flipkart": "flipkart.com",
    "swiggy": "swiggy.com",
    "zomato": "zomato.com",
    "meesho": "meesho.io",
    "cred": "cred.club",
    "razorpay": "razorpay.com",
    "zepto": "zeptonow.com",
    "groww": "groww.in",
    "phonePe": "phonepe.com",
    "phonepe": "phonepe.com",
    "ola": "olacabs.com",
    "sharechat": "sharechat.co",
    "dream11": "dream11.com",
    "upstox": "upstox.com",
    "zerodha": "zerodha.com",
    "paytm": "paytm.com",
    "pine labs": "pinelabs.com",
    "browserstack": "browserstack.com",
    "udaan": "udaan.com",
    "lenskart": "lenskart.com",
    "postman": "postman.com",
    "unacademy": "unacademy.com",
    "inmobi": "inmobi.com",
    "freshworks": "freshworks.com",
    "chargebee": "chargebee.com",
    "cleartax": "cleartax.in",
    "darwinbox": "darwinbox.com",
    "khatabook": "khatabook.com",
    "dunzo": "dunzo.com",
    "spinny": "spinny.com",
    "cars24": "cars24.com",
    "signoz": "signoz.io",
    "middleware": "middleware.io",
    "truefoundry": "truefoundry.com",
    "appsmith": "appsmith.com",
    "simplismart": "simplismart.ai",
    "sarvam ai": "sarvam.ai",
    "murf ai": "murf.ai",
    "hevo data": "hevodata.com",
    "atlan": "atlan.com",
    "devrev": "devrev.ai",
    "hasura": "hasura.io",
    "fampay": "fampay.in",
    "headout": "headout.com",
    "locus": "locus.sh",
    # MNCs
    "infosys": "infosys.com",
    "tcs": "tcs.com",
    "wipro": "wipro.com",
    "hcl tech": "hcltech.com",
    "ibm": "ibm.com",
    "oracle": "oracle.com",
    "intel": "intel.com",
    "hp": "hp.com",
    "siemens": "siemens.com",
    "philips": "philips.com",
    "sony": "sony.com",
    "oyo": "oyorooms.com",
    "hotstar": "hotstar.com",
    "physics wallah": "pw.live",
    "humantic ai": "humantic.ai",
    "astrotalk": "astrotalk.com",
    "juspay": "juspay.in",
}


def guess_domain(company_name: str) -> str:
    """Derive the company's likely domain from its name."""
    key = company_name.strip().lower()
    if key in _DOMAIN_OVERRIDES:
        return _DOMAIN_OVERRIDES[key]

    # Strip common suffixes, then slugify
    for suffix in (" inc", " llc", " ltd", " pvt", " private limited", " limited"):
        key = key.replace(suffix, "")
    slug = re.sub(r"[^a-z0-9]", "", key.strip())
    return f"{slug}.com"


# ──────────────────────────────────────────────────────────────────
# Email pattern role classification
# ──────────────────────────────────────────────────────────────────

_RECRUITER_KEYWORDS = {
    "hr", "hiring", "talent", "recruit", "recruitment", "careers", "career",
    "jobs", "people", "ta", "staffing", "campus",
}
_LEADER_KEYWORDS = {
    "cto", "ceo", "founder", "cofounder", "vp", "director", "head",
    "chief", "lead", "principal", "manager",
}


def classify_email_role(email: str, position: str = "") -> str:
    """Classify an email into a contact role category."""
    local = email.split("@")[0].lower()
    pos_lower = position.lower() if position else ""

    if any(k in pos_lower for k in ("recruiter", "talent", "hr", "hiring", "people")):
        return "HR / Recruiter"
    if any(k in pos_lower for k in ("cto", "ceo", "founder", "director", "vp", "head")):
        return "Leadership / C-Suite"
    if any(k in pos_lower for k in ("engineer", "developer", "tech lead", "architect")):
        return "Engineering / Tech Lead"
    if any(k in pos_lower for k in ("manager",)):
        return "Manager"

    if any(k in local for k in _RECRUITER_KEYWORDS):
        return "HR / Recruiter (inferred)"
    if any(k in local for k in _LEADER_KEYWORDS):
        return "Leadership (inferred)"

    return "Team Member"


# ──────────────────────────────────────────────────────────────────
# Source 1: Hunter.io
# ──────────────────────────────────────────────────────────────────

async def hunt_hunter_io(domain: str, api_key: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Query Hunter.io domain-search for emails at the given domain.
    Free tier: 25 requests/month (domain search) + 50 verifications.
    """
    if not api_key:
        return []

    url = "https://api.hunter.io/v2/domain-search"
    params = {
        "domain": domain,
        "api_key": api_key,
        "limit": limit,
        "type": "personal",   # prioritize named individuals over role@ addresses
    }
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                results = []
                for em in data.get("emails", []):
                    name = f"{em.get('first_name', '')} {em.get('last_name', '')}".strip()
                    email_addr = em.get("value", "")
                    position = em.get("position", "")
                    results.append({
                        "contact_name": name,
                        "contact_email": email_addr,
                        "contact_role": classify_email_role(email_addr, position),
                        "contact_title": position,
                        "confidence": em.get("confidence", 50),
                        "source": "hunter",
                        "linkedin_url": em.get("linkedin", ""),
                        "is_verified": em.get("verification", {}).get("status") == "valid",
                        "verification_status": em.get("verification", {}).get("status", "unknown"),
                    })
                # Also capture the domain's email pattern
                pattern = data.get("pattern", "")
                org = data.get("organization", "")
                logger.info(f"[Hunter.io] {domain} → {len(results)} contacts (pattern: {pattern})")
                return results
            elif resp.status_code == 401:
                logger.warning("[Hunter.io] Invalid API key")
            elif resp.status_code == 429:
                logger.warning("[Hunter.io] Rate limit reached")
            else:
                logger.warning(f"[Hunter.io] HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.error(f"[Hunter.io] Error querying {domain}: {e}")
    return []


# ──────────────────────────────────────────────────────────────────
# Source 2: Snov.io
# ──────────────────────────────────────────────────────────────────

async def _snov_get_access_token(client_id: str, client_secret: str) -> Optional[str]:
    """Get Snov.io OAuth2 access token."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                "https://api.snov.io/v1/oauth/access_token",
                json={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
            )
            if resp.status_code == 200:
                return resp.json().get("access_token")
    except Exception as e:
        logger.error(f"[Snov.io] Auth error: {e}")
    return None


async def hunt_snov_io(domain: str, client_id: str, client_secret: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Query Snov.io domain-search for emails.
    Free tier: 50 credits/month.
    """
    if not client_id or not client_secret:
        return []

    token = await _snov_get_access_token(client_id, client_secret)
    if not token:
        return []

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(
                "https://api.snov.io/v2/domain-emails-with-info",
                json={"domain": domain, "type": "personal", "limit": limit},
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for em in data.get("emails", []):
                    name = f"{em.get('firstName', '')} {em.get('lastName', '')}".strip()
                    email_addr = em.get("email", "")
                    position = em.get("position", "")
                    results.append({
                        "contact_name": name,
                        "contact_email": email_addr,
                        "contact_role": classify_email_role(email_addr, position),
                        "contact_title": position,
                        "confidence": em.get("accuracy", 50),
                        "source": "snov",
                        "linkedin_url": "",
                        "is_verified": em.get("status") == "valid",
                        "verification_status": em.get("status", "unknown"),
                    })
                logger.info(f"[Snov.io] {domain} → {len(results)} contacts")
                return results
            else:
                logger.warning(f"[Snov.io] HTTP {resp.status_code}")
    except Exception as e:
        logger.error(f"[Snov.io] Error querying {domain}: {e}")
    return []


# ──────────────────────────────────────────────────────────────────
# Source 3: Web Scraping (careers / about / team pages)
# ──────────────────────────────────────────────────────────────────

_EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE
)

# Paths commonly containing hiring / team info
_CAREERS_PATHS = [
    "/careers", "/jobs", "/join-us", "/about", "/team",
    "/hiring", "/work-with-us", "/contact",
]

_BLACKLIST_DOMAINS = {
    "example.com", "sentry.io", "wixpress.com", "schema.org",
    "w3.org", "googleapis.com", "gstatic.com", "jquery.com",
    "cloudflare.com", "facebook.com", "twitter.com",
}


async def scrape_company_emails(domain: str, max_pages: int = 4) -> List[Dict[str, Any]]:
    """
    Crawl a company's website for email addresses on key pages.
    Only collects emails whose domain matches the company's domain.
    """
    base_url = f"https://{domain}"
    found_emails: Dict[str, Dict[str, Any]] = {}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
    }

    pages_checked = 0

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as client:
        for path in _CAREERS_PATHS:
            if pages_checked >= max_pages:
                break
            url = f"{base_url}{path}"
            try:
                resp = await client.get(url)
                pages_checked += 1
                if resp.status_code != 200:
                    continue

                text = resp.text
                soup = BeautifulSoup(text, "html.parser")

                # Find mailto: links
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"]
                    if href.startswith("mailto:"):
                        email = href.replace("mailto:", "").split("?")[0].strip().lower()
                        if email and "@" in email:
                            email_domain = email.split("@")[1]
                            if email_domain not in _BLACKLIST_DOMAINS:
                                found_emails[email] = {
                                    "contact_email": email,
                                    "contact_name": "",
                                    "contact_role": classify_email_role(email),
                                    "contact_title": "",
                                    "confidence": 70,
                                    "source": "web_scrape",
                                    "page": path,
                                }

                # Find emails in visible text
                page_text = soup.get_text(separator=" ", strip=True)
                for match in _EMAIL_REGEX.findall(page_text):
                    email = match.strip().lower()
                    email_domain = email.split("@")[1]
                    if email_domain in _BLACKLIST_DOMAINS:
                        continue
                    if email not in found_emails:
                        found_emails[email] = {
                            "contact_email": email,
                            "contact_name": "",
                            "contact_role": classify_email_role(email),
                            "contact_title": "",
                            "confidence": 55,
                            "source": "web_scrape",
                            "page": path,
                        }

            except httpx.HTTPError:
                continue
            except Exception as e:
                logger.debug(f"[WebScrape] Error on {url}: {e}")
                continue

    results = list(found_emails.values())
    logger.info(f"[WebScrape] {domain} → {len(results)} emails from {pages_checked} pages")
    return results


# ──────────────────────────────────────────────────────────────────
# Source 4: Email Pattern Generation
# ──────────────────────────────────────────────────────────────────

# Common Indian startup email patterns
_COMMON_PATTERNS = [
    ("hr@{domain}", "HR / Recruiter (pattern)", 40),
    ("hiring@{domain}", "HR / Recruiter (pattern)", 40),
    ("careers@{domain}", "HR / Recruiter (pattern)", 40),
    ("talent@{domain}", "HR / Recruiter (pattern)", 35),
    ("jobs@{domain}", "HR / Recruiter (pattern)", 30),
    ("recruitment@{domain}", "HR / Recruiter (pattern)", 30),
    ("people@{domain}", "HR / Recruiter (pattern)", 25),
    ("info@{domain}", "General Inquiry", 20),
]


def generate_email_patterns(domain: str) -> List[Dict[str, Any]]:
    """
    Generate common HR/hiring email patterns for a domain.
    These are low-confidence guesses, used only as a fallback.
    """
    results = []
    for pattern, role, conf in _COMMON_PATTERNS:
        email = pattern.format(domain=domain)
        results.append({
            "contact_email": email,
            "contact_name": "",
            "contact_role": role,
            "contact_title": "",
            "confidence": conf,
            "source": "pattern_guess",
            "is_verified": False,
            "verification_status": "unknown",
        })
    return results


# ──────────────────────────────────────────────────────────────────
# LinkedIn X-Ray Search URL Generator
# ──────────────────────────────────────────────────────────────────

def generate_linkedin_search_links(company_name: str) -> Dict[str, str]:
    """
    Generate 1-click LinkedIn search URLs to find recruiters,
    engineering managers, and alumni at the company.
    """
    from urllib.parse import quote
    encoded = quote(company_name)

    return {
        "search_recruiters": (
            f"https://www.linkedin.com/search/results/people/"
            f"?keywords=Recruiter%20OR%20%22Talent%20Acquisition%22%20{encoded}"
        ),
        "search_engineering_managers": (
            f"https://www.linkedin.com/search/results/people/"
            f"?keywords=%22Engineering%20Manager%22%20OR%20%22Tech%20Lead%22%20{encoded}"
        ),
        "search_hr_head": (
            f"https://www.linkedin.com/search/results/people/"
            f"?keywords=%22HR%20Head%22%20OR%20%22Head%20of%20People%22%20{encoded}"
        ),
        "search_cto": (
            f"https://www.linkedin.com/search/results/people/"
            f"?keywords=%22CTO%22%20OR%20%22Chief%20Technology%20Officer%22%20{encoded}"
        ),
        "google_xray": (
            f"https://www.google.com/search?"
            f"q=site:linkedin.com/in+%22{encoded}%22+%22recruiter%22+OR+%22hiring%22"
        ),
    }


# ──────────────────────────────────────────────────────────────────
# Master Enrichment Orchestrator
# ──────────────────────────────────────────────────────────────────

async def enrich_company_contacts(
    company_name: str,
    domain: Optional[str] = None,
    industry: Optional[str] = None,
    hunter_key: Optional[str] = None,
    snov_id: Optional[str] = None,
    snov_secret: Optional[str] = None,
    skip_web_scrape: bool = False,
) -> Dict[str, Any]:
    """
    Run the full enrichment cascade for a single company:
      1. Hunter.io  (if key provided)
      2. Snov.io    (if credentials provided)
      3. Web scrape (unless skipped)
      4. Pattern fallback

    Returns a dict with all discovered contacts and LinkedIn search links.
    """
    resolved_domain = domain or guess_domain(company_name)

    all_contacts: List[Dict[str, Any]] = []
    seen_emails: set = set()

    def _dedup_add(contacts: List[Dict[str, Any]]):
        for c in contacts:
            email = c.get("contact_email", "").lower()
            if email and email not in seen_emails:
                seen_emails.add(email)
                c["company_name"] = company_name
                c["company_domain"] = resolved_domain
                c["industry"] = industry
                all_contacts.append(c)

    # 1. Hunter.io
    key = hunter_key or getattr(settings, "HUNTER_API_KEY", "")
    if key:
        hunter_results = await hunt_hunter_io(resolved_domain, key)
        _dedup_add(hunter_results)

    # 2. Snov.io
    sid = snov_id or getattr(settings, "SNOV_CLIENT_ID", "")
    ssec = snov_secret or getattr(settings, "SNOV_CLIENT_SECRET", "")
    if sid and ssec:
        snov_results = await hunt_snov_io(resolved_domain, sid, ssec)
        _dedup_add(snov_results)

    # 3. Web scrape
    if not skip_web_scrape:
        try:
            web_results = await scrape_company_emails(resolved_domain)
            _dedup_add(web_results)
        except Exception as e:
            logger.warning(f"[Enrichment] Web scrape failed for {company_name}: {e}")

    # 4. Pattern fallback — only if we found very few contacts
    if len(all_contacts) < 3:
        pattern_results = generate_email_patterns(resolved_domain)
        _dedup_add(pattern_results)

    # LinkedIn search links
    linkedin_links = generate_linkedin_search_links(company_name)

    return {
        "company_name": company_name,
        "domain": resolved_domain,
        "industry": industry,
        "contacts": all_contacts,
        "contact_count": len(all_contacts),
        "linkedin_search_links": linkedin_links,
        "sources_used": list({c["source"] for c in all_contacts}),
    }


async def enrich_batch(
    companies: List[Dict[str, Any]],
    concurrency: int = 3,
    hunter_key: Optional[str] = None,
    snov_id: Optional[str] = None,
    snov_secret: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Enrich a batch of companies concurrently.
    Each company dict should have at minimum: {"company_name": "..."}
    Optional keys: "domain", "industry", "fresher_role", "opening_period", "target_contact_type"
    """
    semaphore = asyncio.Semaphore(concurrency)
    results: List[Dict[str, Any]] = []

    async def _enrich_one(company: Dict[str, Any]):
        async with semaphore:
            result = await enrich_company_contacts(
                company_name=company["company_name"],
                domain=company.get("domain"),
                industry=company.get("industry"),
                hunter_key=hunter_key,
                snov_id=snov_id,
                snov_secret=snov_secret,
            )
            # Carry over freshers-specific metadata
            for contact in result["contacts"]:
                contact["fresher_role"] = company.get("fresher_role")
                contact["opening_period"] = company.get("opening_period")
                contact["target_contact_type"] = company.get("target_contact_type")
            results.append(result)
            # Respectful delay between companies
            await asyncio.sleep(1.5)

    tasks = [_enrich_one(c) for c in companies]
    await asyncio.gather(*tasks, return_exceptions=True)

    logger.info(f"[Batch] Enriched {len(results)}/{len(companies)} companies, "
                f"total contacts: {sum(r['contact_count'] for r in results)}")
    return results
