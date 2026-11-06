import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from app.ingestion.base import SourceAdapter, JobPosting
from app.ingestion.constants import (
    is_india_location, is_remote, is_tech_role, is_senior_title,
    FRESHER_ROLE_KEYWORDS,
)

logger = logging.getLogger(__name__)

# ── MNCs & FinTech Leaders with verified public Workday CXS APIs ─────────────
DEFAULT_WORKDAY_TARGETS = [
    # ✅ Confirmed Enterprise Tech Targets
    {"company": "nvidia",       "domain": "nvidia.wd5.myworkdayjobs.com",        "board": "NVIDIAExternalCareerSite",   "display": "NVIDIA"},
    {"company": "adobe",        "domain": "adobe.wd5.myworkdayjobs.com",         "board": "external_experienced",       "display": "Adobe"},
    {"company": "salesforce",   "domain": "salesforce.wd12.myworkdayjobs.com",   "board": "External_Career_Site",       "display": "Salesforce"},
    {"company": "mastercard",   "domain": "mastercard.wd1.myworkdayjobs.com",    "board": "CorporateCareers",           "display": "Mastercard"},
    {"company": "visa",         "domain": "visa.wd5.myworkdayjobs.com",          "board": "SearchJobs",                 "display": "Visa"},
    {"company": "paypal",       "domain": "paypal.wd1.myworkdayjobs.com",        "board": "jobs",                       "display": "PayPal"},
    {"company": "oracle",       "domain": "oracle.wd1.myworkdayjobs.com",        "board": "OracleExternalCareers",      "display": "Oracle"},
    {"company": "microsoft",    "domain": "microsoft.wd5.myworkdayjobs.com",     "board": "MSFTExternalCareers",        "display": "Microsoft"},
    {"company": "intel",        "domain": "intel.wd1.myworkdayjobs.com",         "board": "External",                   "display": "Intel"},
    {"company": "servicenow",   "domain": "servicenow.wd1.myworkdayjobs.com",    "board": "Careers",                    "display": "ServiceNow"},
    {"company": "uber",         "domain": "uber.wd5.myworkdayjobs.com",          "board": "uberExternalCareerSite",     "display": "Uber"},
    {"company": "dell",         "domain": "dell.wd1.myworkdayjobs.com",          "board": "External",                   "display": "Dell"},
    {"company": "vmware",       "domain": "vmware.wd1.myworkdayjobs.com",        "board": "VMwareCareers",              "display": "VMware"},
    # ── Cisco: board slug corrected (was missing, caused HTTP 422) ───────────
    {"company": "cisco",        "domain": "cisco.wd5.myworkdayjobs.com",         "board": "Cisco-University-Careers",   "display": "Cisco"},

    # ── Indian MNCs & IT Giants (were entirely absent — root cause for Accenture miss) ──
    {"company": "accenture",    "domain": "accenture.wd3.myworkdayjobs.com",     "board": "Accenture",                  "display": "Accenture"},
    {"company": "tcs",          "domain": "tcs.wd5.myworkdayjobs.com",           "board": "TCS",                        "display": "TCS"},
    {"company": "infosys",      "domain": "infosys.wd3.myworkdayjobs.com",       "board": "Infosys",                    "display": "Infosys"},
    {"company": "cognizant",    "domain": "cognizant.wd5.myworkdayjobs.com",     "board": "CognizantCareers",           "display": "Cognizant"},
    {"company": "capgemini",    "domain": "capgemini.wd3.myworkdayjobs.com",     "board": "Capgemini",                  "display": "Capgemini"},
    {"company": "hcl",          "domain": "hcltech.wd3.myworkdayjobs.com",       "board": "HCLTechCareers",             "display": "HCL Technologies"},
    {"company": "ltimindtree",  "domain": "ltimindtree.wd3.myworkdayjobs.com",   "board": "LTIMindtreeCareers",         "display": "LTIMindtree"},
    {"company": "mphasis",      "domain": "mphasis.wd3.myworkdayjobs.com",       "board": "MphasisCareers",             "display": "Mphasis"},
    # NOTE: Wipro does NOT use Workday (uses Taleo/SAP SuccessFactors) — removed from targets.
    # NOTE: Intuit was returning HTTP 401; board verified as "Intuit-Careers" below.
    {"company": "intuit",       "domain": "intuit.wd5.myworkdayjobs.com",        "board": "Intuit-Careers",             "display": "Intuit"},

    # ── Global Tech & Product Companies (India offices) ───────────────────────
    {"company": "samsung",      "domain": "samsung.wd3.myworkdayjobs.com",       "board": "Global",                     "display": "Samsung R&D"},
    {"company": "qualcomm",     "domain": "qualcomm.wd5.myworkdayjobs.com",      "board": "External",                   "display": "Qualcomm"},
    {"company": "amdocs",       "domain": "amdocs.wd3.myworkdayjobs.com",        "board": "AmDocsCareers",              "display": "Amdocs"},
    {"company": "micron",       "domain": "micron.wd1.myworkdayjobs.com",        "board": "External",                   "display": "Micron Technology"},
    {"company": "sap",          "domain": "sap.wd3.myworkdayjobs.com",           "board": "SAPCareers",                 "display": "SAP"},
    {"company": "siemens",      "domain": "siemens.wd3.myworkdayjobs.com",       "board": "SiemensCareers",             "display": "Siemens"},

    # ── Premier FinTech & Global Investment Banking Tech ──────────────────────
    {"company": "jpmc",         "domain": "jpmc.wd5.myworkdayjobs.com",          "board": "JPMC",                       "display": "JPMorgan Chase"},
    {"company": "barclays",     "domain": "barclays.wd3.myworkdayjobs.com",      "board": "BarclaysCareers",            "display": "Barclays"},
    {"company": "deutschebank", "domain": "deutschebank.wd3.myworkdayjobs.com",  "board": "DeutscheBankCareers",        "display": "Deutsche Bank"},
    {"company": "bnymellon",    "domain": "bnymellon.wd5.myworkdayjobs.com",     "board": "BNYMellonCareers",           "display": "BNY Mellon"},
    {"company": "aexp",         "domain": "aexp.wd3.myworkdayjobs.com",          "board": "AmexCareers",                "display": "American Express"},
    {"company": "blackrock",    "domain": "blackrock.wd1.myworkdayjobs.com",     "board": "BlackRock_Professional_Careers", "display": "BlackRock"},
    {"company": "citi",         "domain": "citi.wd5.myworkdayjobs.com",          "board": "CitiCareers",                "display": "Citi"},
    {"company": "wellsfargo",   "domain": "wellsfargo.wd1.myworkdayjobs.com",    "board": "WellsFargoJobs",             "display": "Wells Fargo"},
    {"company": "fidelity",     "domain": "fidelity.wd1.myworkdayjobs.com",      "board": "FidelityCareers",            "display": "Fidelity Investments"},
    {"company": "morganstanley","domain": "morganstanley.wd5.myworkdayjobs.com", "board": "External",                   "display": "Morgan Stanley"},
]

# Fresher-specific search terms for Workday CXS API
# Split into two groups: core SWE terms + AI/ML terms.
# Kept separate so we can tune / disable AI-only search independently.
WORKDAY_SEARCH_TERMS = [
    # ── Core SWE / Fresher terms ─────────────────────────────────────────────
    "software engineer", "developer", "data", "technology", "analyst",
    "intern", "associate", "trainee", "graduate", "junior", "fresher",
    "sde", "get", "entry level", "software engineer program", "new analyst",
    "systems engineer", "platform engineer", "cloud engineer",

    # ── AI / ML / Data Science terms (were entirely missing — caused Accenture miss) ──
    "machine learning", "artificial intelligence", "data science",
    "deep learning", "natural language processing", "nlp",
    "computer vision", "mlops", "ml engineer", "ai engineer",
    "generative ai", "genai", "large language model", "llm",
    "data scientist", "applied scientist", "research engineer",
    "ai analytics", "analytics engineer",
]


class WorkdayAdapter(SourceAdapter):
    """
    Standardised Workday CXS Public Career Search API — India-focused.
    Endpoint: https://{domain}/wday/cxs/{company}/{board}/jobs
    Searches for tech/engineering roles with fresher-specific terms.
    Filters to India + Remote. No hard seniority filter.
    """

    def __init__(self, name: str = "workday", config: Optional[Dict[str, Any]] = None):
        super().__init__(name, config)
        self.targets = self.config.get("targets", DEFAULT_WORKDAY_TARGETS)
        self.client_headers = {
            "Content-Type": "application/json",
            "User-Agent": "AIJobFinder-Client/1.0 (Job Matching Review Bot; contact@aijobfinder.local)"
        }

    async def fetch_workday_target(
        self, client: httpx.AsyncClient, target: Dict[str, str], since: Optional[datetime] = None
    ) -> List[JobPosting]:
        domain = target["domain"]
        company = target["company"]
        board = target["board"]
        display_name = target.get("display", company.title())
        url = f"https://{domain}/wday/cxs/{company}/{board}/jobs"

        postings: List[JobPosting] = []

        seen_ids: set = set()
        for term in WORKDAY_SEARCH_TERMS:
            payload = {
                "appliedFacets": {},
                "limit": 20,
                "offset": 0,
                "searchText": term
            }
            try:
                resp = await client.post(url, json=payload, headers=self.client_headers, timeout=15.0)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                items = data.get("jobPostings", [])

                for item in items:
                    external_path = item.get("externalPath", "")
                    title = item.get("title", "")
                    location = item.get("locationsText", "Not Specified")
                    posted_on = item.get("postedOn", "")

                    # ── Dedup within this fetch session ──────────────────────
                    uid = f"{company}_{external_path}"
                    if uid in seen_ids:
                        continue
                    seen_ids.add(uid)

                    # ── Filter: Tech roles only ───────────────────────────────
                    if not is_tech_role(title):
                        continue

                    # ── NO hard senior filter — flag for scoring ──────────────
                    is_senior = is_senior_title(title)

                    # ── Filter: India or Remote ───────────────────────────────
                    is_wfh = is_remote(location, title)
                    is_india = is_india_location(location)
                    if not is_india and not is_wfh:
                        continue

                    external_id = f"{company}_{external_path.strip('/').replace('/', '_')}"
                    full_url = f"https://{domain}/en-US/{board}{external_path}"

                    # Normalise location label
                    if is_wfh and not is_india:
                        display_location = "Remote / Work From Home"
                    else:
                        display_location = location

                    # Fetch full job description from CXS detail endpoint
                    full_desc = await self._fetch_full_description(client, domain, company, board, external_path)
                    if not full_desc:
                        full_desc = (
                            f"Role: {title}\nCompany: {display_name}\n"
                            f"Location: {display_location}\nPosted: {posted_on}"
                        )

                    posting = JobPosting(
                        source_name=self.name,
                        external_id=external_id,
                        title=title,
                        company=display_name,
                        location=display_location,
                        is_remote=is_wfh,
                        description=full_desc,
                        url=full_url,
                        posted_date=datetime.utcnow(),
                        raw_metadata={
                            "company": company,
                            "workday_target": target,
                            "postedOn": posted_on,
                            "is_senior": is_senior,
                            "work_type": "wfh" if is_wfh else "onsite"
                        }
                    )
                    postings.append(posting)

            except Exception as e:
                logger.warning(f"Error fetching Workday '{company}' (term='{term}'): {e}")

        return postings

    async def _fetch_full_description(
        self, client: httpx.AsyncClient, domain: str, company: str, board: str, external_path: str
    ) -> Optional[str]:
        """Fetch the complete, unclipped job description from Workday CXS detail endpoint."""
        detail_url = f"https://{domain}/wday/cxs/{company}/{board}{external_path}"
        try:
            resp = await client.get(
                detail_url,
                headers={"Accept": "application/json", "User-Agent": self.client_headers["User-Agent"]},
                timeout=10.0
            )
            if resp.status_code == 200:
                data = resp.json()
                info = data.get("jobPostingInfo", {})
                html_desc = info.get("jobDescription", "")
                if html_desc:
                    return BeautifulSoup(html_desc, "html.parser").get_text(separator="\n", strip=True)
        except Exception as e:
            logger.debug(f"Could not fetch full Workday detail for {detail_url}: {e}")
        return None

    async def fetch_new_postings(self, since: Optional[datetime] = None) -> List[JobPosting]:
        all_postings: List[JobPosting] = []
        async with httpx.AsyncClient() as client:
            for target in self.targets:
                jobs = await self.fetch_workday_target(client, target, since)
                all_postings.extend(jobs)
                logger.info(f"Workday '{target['display']}': {len(jobs)} India/Remote tech jobs")
        return all_postings
