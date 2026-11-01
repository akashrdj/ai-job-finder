# AI Job Finder — Project Card

### One-liner
Autonomous job engine scanning 8+ feeds, gating 0-1 YOE roles, matching a 4-variant resume matrix, and verifying claims [VERIFIED: README.md:16-19].

### Problem
Freshers waste hundreds of hours screening job feeds where 85%+ of entry-level listings mandate 2-4+ YOE, while bots cause disqualification through hallucinated claims [VERIFIED: ai_job_finder.md:8-9].

### My Role
[UNKNOWN: ASK USER]. Git shows 1 commit by akashrdj [VERIFIED: git log]. Profile claims Creator / Cloud Architect [VERIFIED: my_profile.json:66]. Team size: 1 recorded in git [INFERRED].

### Stack
- Languages: Python (>=3.10) [VERIFIED: README.md:7], JavaScript [VERIFIED: frontend/package.json:5]
- Frameworks: FastAPI, React 18, Vite, APScheduler, Jinja2 [VERIFIED: backend/requirements.txt:1, 9, 14, frontend/package.json:12, 18]
- Data/AI: SQLAlchemy, aiosqlite, SQLite, FAISS-CPU, Google GenAI SDK [VERIFIED: backend/requirements.txt:5, 7, 11, 20, backend/app/config.py:16]
- Infra: AWS Lambda container, EventBridge, FastMCP, gspread [VERIFIED: Dockerfile.lambda:2, deploy_aws.py:44, backend/requirements.txt:17, 22]
- Testing: PyTest [VERIFIED: backend/requirements.txt:15]

### Key Design Decisions
- Two-Speed Pipeline -> 15-min regex discovery; slow lane LLM drafting capped at 10/day -> prevents quota exhaustion -> Alt: LLM scoring per raw posting [VERIFIED: backend/app/scheduler/scheduler_service.py:88-405].
- Deterministic Fact-Checking -> ClaimValidator checks skills and metrics via profile set intersection -> eliminates hallucinations -> Alt: LLM self-evaluation [VERIFIED: backend/app/drafting/claim_validator.py:50-137].
- 4-Curated Profiles Matrix -> Selects pre-structured variants and reorders authentic bullets -> guarantees factual ATS fit -> Alt: generative bullet drafting [VERIFIED: backend/app/matching/engine.py:20-46, backend/app/drafting/resume_drafter.py:14-58].

### Measured Numbers
- Database stores 787 jobs, 813 scores, 1 profile in backend/job_finder.db [VERIFIED: SQLite query].
- Historical report: Greenhouse (586 raw, 65 filtered), RemoteOK (100 raw, 13 filtered), Workday (40 raw, 4 filtered), Lever (14 raw, 2 filtered) [VERIFIED: backend/api_test_report.json:13-191].
- Recruiter directory contains 198 company email mappings [VERIFIED: recruiter_companies.json:1].

### Scope and Limits
Functional prototype. Ingestion, gating, and UI work. FresherInspectionAgent is decoupled [VERIFIED: backend/tests/test_strict_fresher_rules.py:118]. MCP server has attribute bugs [VERIFIED: backend/mcp_server/server.py:75]. langgraph is unused [VERIFIED: backend/requirements.txt:21].

### Atomic Facts for Resume Use
- Ingests jobs across 8+ sources including Greenhouse, Lever, Workday CXS, and LinkedIn [VERIFIED: backend/app/ingestion/manager.py:70-85].
- Disqualifies listings mandating >=2 YOE using 7 regex patterns [VERIFIED: backend/app/matching/rules.py:80-189, 268].
- Ranks candidate fit against a 4-profile resume matrix using TF-IDF vectorizer [VERIFIED: backend/app/matching/engine.py:20-46].
- Indexes profile achievements using FAISS IndexFlatIP with Reciprocal Rank Fusion (k=60) [VERIFIED: backend/app/knowledge/retriever.py:38-230].
- Validates cover letters against profile facts, flagging unverified skills and metrics [VERIFIED: backend/app/drafting/claim_validator.py:50-137].
- Deploys containerized pipeline to AWS Lambda triggered every 8 hours by EventBridge [VERIFIED: Dockerfile.lambda:1-14, deploy_aws.py:40-46].

### Open Questions
1. Exact personal contribution breakdown vs potential external collaborators?
2. Has AWS Lambda been deployed in production or tested only locally?
3. What are the real application submission counts and response rates?
4. Is assessmnet.py an orphan file that can be deleted?
5. Over what specific date range was the codebase developed?

