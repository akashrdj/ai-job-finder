import re
from typing import Dict, Any, List, Tuple
from app.models.user_profile import UserProfile
from app.models.job import Job

# ── Seniority Keywords that trigger HARD DISQUALIFICATION ──────────────────────
# Any role containing these in the title is definitively not for freshers.
SENIOR_TITLE_KEYWORDS = [
    "senior", "sr.", "sr ", "lead", "staff", "principal", "director",
    "head of", "head,", "vp", "vice president", "architect", "manager",
    "tech lead", "team lead", "engineering manager",
    "specialist ii", "specialist iii",
    "sde 2", "sde-2", "sde ii", "sde-ii", "sde2",
    "sde 3", "sde-3", "sde iii", "sde-iii", "sde3",
    "se 2", "se-2", "se ii", "se2",
    "swe 2", "swe-2", "swe ii", "swe2",
    "swe 3", "swe-3", "swe iii", "swe3",
]

# Regex pattern for level 2+ senior engineering designations (avoids false-matching years like 2026)
SENIOR_LEVEL_PATTERN = re.compile(
    r'\b(?:sde|swe|se|engineer|developer|analyst|specialist|level|lvl|grade)\s*[-_ ]?(?:2|3|4|5|ii|iii|iv|v)\b',
    re.IGNORECASE
)

# ── Fresher-Fit Bonus Titles (Pure Fresher / 0 YOE Target) ────────────────────
FRESHER_BONUS_TITLES = [
    "get", "graduate engineer trainee", "graduate trainee",
    "sde 1", "sde-1", "sde i", "sde1",
    "se 1", "se-1", "se i", "se1",
    "swe 1", "swe-1", "swe i", "swe1",
    "software engineer 1", "software engineer i",
    "associate software engineer", "associate sde", "associate developer",
    "associate engineer", "associate consultant", "associate analyst",
    "junior software engineer", "junior developer", "junior sde",
    "junior engineer", "junior data engineer", "junior analyst",
    "entry level", "entry-level",
    "fresher", "new grad", "new graduate",
    "campus hire", "campus recruit", "campus placement",
    "trainee", "intern", "internship",
    "member of technical staff", "mts",
    "software analyst", "technology analyst", "program analyst",
    "systems engineer 1", "systems engineer trainee",
    # ── FinTech & Investment Bank Fresher Programs ──
    "software engineer program", "sep", "new analyst", "graduate analyst",
    "technology analyst program", "tap", "summer analyst", "technology campus",
    "campus analyst", "engineering campus",
]

# Keywords in JD that explicitly signal fresher eligibility (0-N YOE)
FRESHER_JD_SIGNALS = [
    "0-1 year", "0 to 1 year", "0-2 year", "0 to 2 year", "0-3 year", "0 to 3 year",
    "0 - 1 year", "0 - 2 year", "0 - 3 year",
    "0-1 yrs", "0-2 yrs", "0-3 yrs",
    "0 to 1 yrs", "0 to 2 yrs", "0 to 3 yrs",
    "0+ years", "0 years", "0+ yrs",
    "freshers", "fresher", "fresh graduate", "recent graduate", "recent graduates",
    "batch of 2024", "batch of 2025", "batch of 2026",
    "2024 batch", "2025 batch", "2026 batch",
    "2024/2025", "2025/2026",
    "campus placement", "campus hiring", "campus recruit",
    "no experience required", "no prior experience", "entry level",
    "new grad", "new graduates", "fresher can apply", "freshers can apply",
]

# Negative experience phrases that indicate prior experience is mandatory (>0 YOE)
NON_FRESHER_PHRASES = [
    "at least 1 year", "at least 2 years", "at least 3 years",
    "minimum 1 year", "minimum 2 years", "minimum 3 years",
    "min 1 year", "min 2 years", "min 3 years",
    "1+ years of experience", "2+ years of experience", "3+ years of experience",
    "1+ year of experience", "2+ year of experience", "3+ year of experience",
    "1-2 years of experience", "2-3 years of experience", "2-4 years of experience",
    "1 to 2 years of experience", "2 to 3 years of experience",
    "prior industry experience required", "prior commercial experience required",
    "proven experience as a", "years of proven experience",
]

# Regex patterns for extracting candidate years of experience requirements
EXP_RANGE_PATTERN = re.compile(
    r'(\d+)\+?\s*(?:[-–to]+|\s+to\s+)\s*(\d+)\+?\s*(?:years?|yrs?|yoe)\s+(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+|software\s+|hands-on\s+|work\s+)?(?:experience|exp)',
    re.IGNORECASE
)
EXP_DIRECT_RANGE = re.compile(
    r'\b(\d+)\s*(?:[-–to]+|\s+to\s+)\s*(\d+)\s*(?:years?|yrs?|yoe)\b',
    re.IGNORECASE
)
EXP_SINGLE_PATTERN = re.compile(
    r'(\d+)\+?\s*(?:years?|yrs?|yoe)\s+(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+|software\s+|hands-on\s+|work\s+)?(?:experience|exp)',
    re.IGNORECASE
)
EXP_DIRECT_PLUS = re.compile(
    r'\b([2-9]|\d{2,})\+\s*(?:years?|yrs?|yoe)\b',
    re.IGNORECASE
)
EXP_MIN_PATTERN = re.compile(
    r'(?:minimum|min|at\s+least|more\s+than)\s+(\d+)\+?\s*(?:years?|yrs?|yoe)',
    re.IGNORECASE
)
EXP_PREFIX_COLON = re.compile(
    r'(?:experience|exp|eligibility|requirements?)\s*[:\-–]\s*(\d+)\+?\s*(?:[-–to]+\s*(\d+)\+?)?\s*(?:years?|yrs?|yoe)?',
    re.IGNORECASE
)
EXP_CONTEXT_PATTERN = re.compile(
    r'(?:experience|qualifications|requirements|eligibility)[^\.\n\r]{0,80}?(\d+)\+?\s*(?:[-–to]+|\s+to\s+)?\s*(\d+)?\+?\s*(?:years?|yrs?)',
    re.IGNORECASE
)

# Comprehensive tech requirement keywords for gap analysis
COMMON_TECH_REQUIREMENTS = [
    # Languages
    "Python", "JavaScript", "TypeScript", "Java", "C++", "Go", "Golang", "Rust", "Kotlin", "Swift",
    "Ruby", "PHP", "Scala", "R", "MATLAB", "Dart", "C#",
    # Frontend
    "React", "Vue.js", "Angular", "Next.js", "Svelte", "HTML5", "CSS3", "Tailwind", "Redux",
    "React Native", "Flutter", "Webpack", "Vite",
    # Backend
    "FastAPI", "Django", "Flask", "Node.js", "Express.js", "Spring Boot", "NestJS", "Rails",
    "GraphQL", "REST APIs", "gRPC", "WebSockets",
    # Databases
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "SQLite", "DynamoDB",
    "Cassandra", "BigQuery", "Snowflake", "Supabase",
    # Cloud & DevOps
    "AWS", "GCP", "Azure", "Docker", "Kubernetes", "Terraform", "Ansible",
    "CI/CD", "Jenkins", "GitHub Actions", "GitLab CI", "Helm",
    "Lambda", "EC2", "S3", "Cloud Run", "Vercel",
    # AI / ML
    "PyTorch", "TensorFlow", "Keras", "Scikit-learn", "Pandas", "NumPy",
    "LLMs", "LangChain", "OpenAI API", "Hugging Face", "ONNX",
    "RAG", "Vector Embeddings", "Pinecone", "Weaviate", "FAISS",
    "MLflow", "Weights & Biases", "Airflow",
    # Observability / Data
    "Kafka", "RabbitMQ", "Celery", "Prometheus", "Grafana", "OpenTelemetry",
    "Spark", "Flink", "dbt", "Airbyte",
    # Tools & Practices
    "Git", "Linux", "Bash", "Microservices", "System Design", "OOP",
    "Data Structures & Algorithms", "Unit Testing", "pytest", "Jest",
]


def extract_experience_requirements(text: str) -> List[int]:
    """
    Extract all candidate minimum years of experience mentioned in the job description.
    Filters out company age / business years by looking for experience context.
    """
    mins: List[int] = []
    # Check range pattern: e.g. "0-2 years of experience"
    for m in EXP_RANGE_PATTERN.finditer(text):
        try:
            mins.append(int(m.group(1)))
        except ValueError:
            pass
    # Check direct range pattern: e.g. "3-5 years", "3 to 5 yrs"
    for m in EXP_DIRECT_RANGE.finditer(text):
        try:
            mins.append(int(m.group(1)))
        except ValueError:
            pass
    # Check single pattern: e.g. "5+ years of experience"
    for m in EXP_SINGLE_PATTERN.finditer(text):
        try:
            mins.append(int(m.group(1)))
        except ValueError:
            pass
    # Check direct plus: e.g. "3+ years", "4+ yrs"
    for m in EXP_DIRECT_PLUS.finditer(text):
        try:
            mins.append(int(m.group(1)))
        except ValueError:
            pass
    # Check min pattern: e.g. "minimum 3 years"
    for m in EXP_MIN_PATTERN.finditer(text):
        try:
            mins.append(int(m.group(1)))
        except ValueError:
            pass
    # Check prefix pattern: e.g. "Experience: 3-5 years"
    for m in EXP_PREFIX_COLON.finditer(text):
        try:
            mins.append(int(m.group(1)))
        except ValueError:
            pass
    # Check context pattern
    for m in EXP_CONTEXT_PATTERN.finditer(text):
        try:
            mins.append(int(m.group(1)))
        except ValueError:
            pass
    return mins


class RuleEvaluator:
    @classmethod
    def is_fresher_job(cls, job: Job) -> bool:
        """
        Determines if a job explicitly targets freshers (0 YOE, GET, Trainee, Associate, SDE-1).
        """
        title_lower = job.title.lower()
        if any(ft in title_lower for ft in FRESHER_BONUS_TITLES):
            return True
        desc_lower = (job.description or "").lower()
        if any(sig in desc_lower for sig in FRESHER_JD_SIGNALS):
            return True
        mins = extract_experience_requirements(desc_lower)
        if mins and min(mins) == 0:
            return True
        return False

    @classmethod
    def evaluate(cls, job: Job, profile: UserProfile) -> Tuple[float, List[str], List[str], List[str]]:
        """
        Evaluate hard rules and keyword matches with strict fresher qualification.
        Returns:
            - rule_score: 0.0 (disqualified) to 1.5+ (fresher match with bonus)
            - matched_skills: list of skills matched in JD
            - missing_requirements: list of key JD requirements not in profile
            - rule_reasons: human-readable list of rule check outcomes
        """
        preferences = profile.preferences or {}
        excluded_companies = [c.lower() for c in preferences.get("excluded_companies", [])]
        excluded_keywords = [k.lower() for k in preferences.get("excluded_keywords", [])]
        preferred_locations = [loc.lower() for loc in preferences.get("preferred_locations", [])]
        remote_only = preferences.get("remote_only", False)

        job_text = f"{job.title} {job.location or ''} {job.description}".lower()
        title_lower = job.title.lower()
        desc_lower = (job.description or "").lower()
        rule_reasons: List[str] = []
        rule_score = 1.0

        # 1. Company Blacklist
        if job.company.lower() in excluded_companies:
            rule_reasons.append(f"Disqualified: Company '{job.company}' is in excluded list.")
            return 0.0, [], [], rule_reasons

        # 2. Excluded Keywords
        for kw in excluded_keywords:
            if kw in job_text:
                rule_reasons.append(f"Disqualified: Contains excluded keyword '{kw}'.")
                return 0.0, [], [], rule_reasons

        # 3. Seniority Title Check — HARD DISQUALIFICATION
        # Jobs for Senior, Staff, Lead, Architect, or Level 2/3/4/II/III roles MUST be eliminated for freshers.
        for sen_kw in SENIOR_TITLE_KEYWORDS:
            if sen_kw in title_lower:
                rule_reasons.append(f"Disqualified: Seniority keyword in title ('{sen_kw}'). Candidate seeks fresher/entry roles.")
                return 0.0, [], [], rule_reasons

        level_match = SENIOR_LEVEL_PATTERN.search(title_lower)
        if level_match:
            matched_term = level_match.group(0)
            rule_reasons.append(f"Disqualified: Senior level designation in title ('{matched_term}'). Candidate seeks fresher/entry roles.")
            return 0.0, [], [], rule_reasons

        # 4. STRICT FRESHER EXPERIENCE CHECK — HARD DISQUALIFICATION FOR MIN YOE >= 2
        # Check explicit fresher signals in JD text
        explicit_fresher_signals = [
            "0-1 year", "0 to 1 year", "0-2 year", "0 to 2 year", "0-1 yrs", "0 to 1 yrs",
            "batch of 2024", "batch of 2025", "batch of 2026", "2024 batch", "2025 batch", "2026 batch",
            "fresher", "freshers", "recent graduate", "recent graduates", "no experience required", "no prior experience"
        ]
        has_explicit_0yoe_signal = any(sig in desc_lower for sig in explicit_fresher_signals)

        extracted_mins = extract_experience_requirements(job.description or "")
        if extracted_mins:
            min_req = min(extracted_mins)
            # If minimum required experience is 2+ years (e.g. 2, 3, 4, 5+), it is NOT for a fresher
            if min_req >= 2:
                if not has_explicit_0yoe_signal:
                    rule_reasons.append(
                        f"Disqualified: Job requires minimum {min_req}+ years of experience. Filtered out per strict 0-YOE fresher policy."
                    )
                    return 0.0, [], [], rule_reasons

            elif min_req == 1:
                # 1 year requirement — only allow if fresher signals exist or entry title
                if not has_explicit_0yoe_signal and not any(ft in title_lower for ft in FRESHER_BONUS_TITLES):
                    rule_reasons.append(
                        "Disqualified: Job requires prior 1+ year industry experience without fresher eligibility."
                    )
                    return 0.0, [], [], rule_reasons

            if 0 in extracted_mins:
                rule_score *= 1.35
                rule_reasons.append("🎯 Pure Fresher Experience: JD explicitly specifies 0 YOE minimum.")

        # Check negative experience phrases if no explicit 0 YOE signal was found
        if not has_explicit_0yoe_signal and not (extracted_mins and 0 in extracted_mins):
            for neg_phrase in NON_FRESHER_PHRASES:
                if neg_phrase in desc_lower:
                    rule_reasons.append(
                        f"Disqualified: Job requires prior experience ('{neg_phrase}'). Filtered out per strict 0-YOE fresher policy."
                    )
                    return 0.0, [], [], rule_reasons

        # 5. Pure Fresher Title & JD Boost
        is_fresher = cls.is_fresher_job(job)
        if is_fresher:
            rule_score *= 1.40  # +40% rule boost for verified fresher roles
            rule_reasons.append("🎯 Fresher Priority: Matches verified fresher / graduate / associate pattern.")

        # 6. Location / Remote Check
        if remote_only and not job.is_remote:
            rule_score *= 0.4
            rule_reasons.append("Location Warning: Job is not marked remote.")
        elif job.location and preferred_locations:
            loc_match = any(ploc in (job.location or "").lower() for ploc in preferred_locations) or job.is_remote
            if not loc_match:
                rule_score *= 0.8
                rule_reasons.append(f"Location note: Location '{job.location}' outside preferred list.")

        # 7. Skills Matching & Extraction
        all_candidate_skills = profile.skills or []
        matched_skills: List[str] = []
        
        for skill in all_candidate_skills:
            pattern = rf'\b{re.escape(skill.lower())}\b'
            if re.search(pattern, job_text):
                matched_skills.append(skill)

        # Build a lowercase set of candidate skills for fast lookup
        candidate_skills_lower = {s.lower() for s in all_candidate_skills}

        missing_requirements: List[str] = []
        for req in COMMON_TECH_REQUIREMENTS:
            if req.lower() not in candidate_skills_lower:
                pattern = rf'\b{re.escape(req.lower())}\b'
                if re.search(pattern, job_text):
                    missing_requirements.append(req)

        if matched_skills:
            rule_reasons.append(f"Matched {len(matched_skills)} core skills: {', '.join(matched_skills[:6])}.")
        if missing_requirements:
            rule_reasons.append(f"Potential tech stack gaps: {', '.join(missing_requirements)}.")

        return max(0.0, min(1.5, rule_score)), matched_skills, missing_requirements, rule_reasons
