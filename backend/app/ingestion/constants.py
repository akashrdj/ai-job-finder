"""
Shared constants for all ingestion adapters.
Centralises fresher-targeted role keywords, India location terms,
remote signals, and seniority markers to avoid duplication.
"""

# ── Fresher-Targeted Role Keywords ────────────────────────────────────────────
# These are the titles/keywords that indicate a role suitable for 0-1 YOE.
# We search broadly and let the matching engine score & prioritize.
FRESHER_ROLE_KEYWORDS = [
    # ── Explicit fresher / entry-level designations ───────────────────────────
    "get", "graduate engineer trainee", "graduate trainee",
    "sde 1", "sde-1", "sde i", "sde1",
    "se 1", "se-1", "se i", "se1",
    "software engineer 1", "software engineer i",
    "associate software engineer", "associate sde", "associate developer",
    "associate engineer", "associate consultant",
    "junior software engineer", "junior developer", "junior sde",
    "junior engineer", "junior data engineer", "junior analyst",
    "entry level", "entry-level",
    "fresher", "new grad", "new graduate",
    "campus hire", "campus recruit", "campus placement",
    "trainee", "intern", "internship",
    "member of technical staff", "mts",
    "software analyst", "technology analyst", "program analyst",
    "systems engineer", "analyst trainee",

    # ── Generic tech role titles (still needed for broad coverage) ────────────
    "software engineer", "software developer", "sde", "swe",
    "backend engineer", "backend developer",
    "frontend engineer", "frontend developer",
    "fullstack engineer", "fullstack developer", "full stack",
    "full-stack engineer", "full-stack developer",
    "data engineer", "data analyst", "data scientist",
    "ml engineer", "machine learning engineer",
    "ai engineer", "genai engineer",
    "devops engineer", "cloud engineer", "platform engineer",
    "site reliability engineer", "sre",
    "qa engineer", "quality engineer", "test engineer",
    "mobile developer", "android developer", "ios developer",
    "engineer", "developer", "software",
]

# ── India Location Keywords (case-insensitive match) ──────────────────────────
INDIA_LOCATION_KEYWORDS = [
    "india", "bengaluru", "bangalore", "hyderabad", "pune", "mumbai",
    "delhi", "gurugram", "gurgaon", "noida", "chennai", "kolkata",
    "ahmedabad", "jaipur", "thiruvananthapuram", "kochi", "coimbatore",
    "lucknow", "chandigarh", "indore", "bhopal", "nagpur", "visakhapatnam",
]

# ── Remote / WFH Signals ─────────────────────────────────────────────────────
REMOTE_SIGNALS = [
    "remote", "work from home", "wfh", "anywhere", "worldwide",
    "fully distributed", "hybrid", "virtual", "telecommute",
    "work from anywhere",
]

# ── Seniority Keywords (used for scoring penalty & filtering) ─────────
SENIOR_TITLE_KEYWORDS = [
    "senior", "sr.", "sr ", "lead", "staff", "principal", "director",
    "head of", "vp ", "vice president", "architect", "manager", "cto", "cpo",
    "sde 2", "sde-2", "sde ii", "sde-ii", "sde2", "sde 3", "sde-3", "sde iii", "sde3",
    "se 2", "se-2", "se ii", "se2", "se 3", "se-3", "se iii", "se3",
    "swe 2", "swe-2", "swe ii", "swe2", "swe 3", "swe-3", "swe iii", "swe3",
    "level 2", "level 3", "level ii", "level iii", "grade 2", "grade 3",
]

FRESHER_SEARCH_QUERIES = [
    "SDE 1",
    "Associate Software Engineer",
    "Graduate Engineer Trainee",
    "Junior Software Developer",
    "Software Engineer fresher",
    "Software Analyst",
    "Member of Technical Staff",
    "Backend Developer entry level",
    "Frontend Developer junior",
    "Data Analyst fresher",
    "ML Engineer entry level",
    "DevOps Engineer junior",
    "Full Stack Developer fresher",
    "Software Engineer Intern",
    "Technology Analyst",
    "Systems Engineer",
    "QA Engineer fresher",
    # ── FinTech & Investment Bank Fresher Programs ──
    "Software Engineer Program",
    "New Analyst Goldman Sachs",
    "Graduate Analyst Barclays",
    "Technology Analyst Program",
]


def is_india_location(location: str) -> bool:
    """Check if a location string indicates India."""
    loc_lower = location.lower()
    return any(kw in loc_lower for kw in INDIA_LOCATION_KEYWORDS)


def is_india_or_remote(location: str, title: str = "", description: str = "") -> bool:
    """Check if a job is in India or is remote/WFH accessible."""
    combined = f"{location} {title} {description[:300]}".lower()
    india_match = any(kw in combined for kw in INDIA_LOCATION_KEYWORDS)
    remote_match = any(sig in combined for sig in REMOTE_SIGNALS)
    return india_match or remote_match


def is_remote(location: str, title: str = "", description: str = "") -> bool:
    """Check if a job is remote/WFH."""
    combined = f"{location} {title} {description[:500]}".lower()
    return any(sig in combined for sig in REMOTE_SIGNALS)


def is_tech_role(title: str) -> bool:
    """Check if a job title is a tech/CS role.

    Extended to catch AI/ML/consulting-style titles (e.g. 'AI & Analytics Associate',
    'Analyst - Artificial Intelligence') that MNCs like Accenture use instead of
    startup-style titles ('ML Engineer').
    """
    title_lower = title.lower()
    # Primary check: matches any known tech/fresher keyword
    if any(kw in title_lower for kw in FRESHER_ROLE_KEYWORDS):
        return True
    # Secondary check: AI/ML terms that MNCs use in consulting-flavoured titles
    _AI_ML_EXTRAS = [
        "artificial intelligence", "machine learning", "deep learning",
        "data science", "natural language", "computer vision", "mlops",
        "generative", "genai", "llm", "analytics", "automation",
        "robotics", "cloud", "devops", "platform", "infrastructure",
        "cybersecurity", "security", "blockchain", "iot", "embedded",
    ]
    return any(kw in title_lower for kw in _AI_ML_EXTRAS)


def is_senior_title(title: str) -> bool:
    """Check if a title indicates a senior-level position."""
    title_lower = title.lower()
    return any(kw in title_lower for kw in SENIOR_TITLE_KEYWORDS)
