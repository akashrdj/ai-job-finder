# Project: Autonomous AI Job Discovery, Multi-Profile RAG & Anti-Hallucination Outreach Engine (AI Job Finder)

## 1. Executive Summary & Problem Statement
- **Core Problem**: Early-career software engineers and college freshers encounter severe structural friction when entering the tech job market:
  1. Generic automated application bots spam LinkedIn and ATS platforms with robotic, hallucinated credentials that trigger immediate blacklisting and interview disqualification.
  2. Over 85% of job postings labeled "Junior", "Associate", or "Entry-Level" deceptively mandate 2 to 4+ years of prior commercial experience, creating an exhausting manual triaging overhead.
  3. Job opportunities are highly fragmented across isolated enterprise Applicant Tracking Systems (ATS) like Workday, Greenhouse, and Lever, as well as aggregators, resulting in hours of daily manual portal scanning.
- **Solution Overview**: In my project, I engineered an autonomous, serverless end-to-end recruitment intelligence and application preparation engine. The platform continuously ingests postings across 7 distinct streams (Workday CXS, Greenhouse, Lever, JSearch/Google for Jobs, Adzuna, RemoteOK, and a polite robots.txt-compliant microdata scraper). It processes postings through a two-speed evaluation pipeline: sub-5ms deterministic rule-based experience gating followed by a hybrid RAG retrieval engine (FAISS dense vector search + BM25 token overlap with Reciprocal Rank Fusion, $k=60$). The system evaluates each role against a 4-Profile Resume Matrix, drafts tailored cover letters using Google Gemini 2.5 Flash / 2.0 Flash, verifies all statements through a deterministic anti-hallucination claim validator, enriches hiring contacts via Hunter.io/Snov.io and a 198+ verified recruiter directory, syncs prioritized opportunities to Google Sheets, dispatches HTML email digests, and exposes tools to Claude Desktop via the Model Context Protocol (MCP).
- **My Primary Role & Contributions**:
  - Architected the end-to-end multi-tier pipeline: ingestion adapters, database schema, hybrid vector store, matching algorithms, anti-hallucination validation, and serverless AWS infrastructure.
  - Implemented the two-speed evaluation architecture, writing the regex qualification engine and the `EmbeddingVectorizer` / FAISS `IndexFlatIP` retrieval system.
  - Designed the `ClaimValidator` guardrail that extracts atomic claims (skills, entities, percentages) and verifies them against canonical profile facts.
  - Engineered the FastMCP server for Claude Desktop and the universal autofill DOM injector bookmarklet for Workday, Greenhouse, Lever, and Ashby portals.
  - Containerized the system via Docker and automated deployment to AWS Lambda + Amazon EventBridge via Boto3 and PowerShell.

## 2. Technical Stack & Architecture
- **Frameworks & Languages**:
  - **Backend & Core Logic**: Python 3.10+, FastAPI 0.110+, SQLAlchemy 2.0 (asyncio with `aiosqlite`), Pydantic v2, Pydantic-Settings, HTTPX (async HTTP client), Jinja2 (contextual templating), BeautifulSoup4 (HTML/JSON-LD microdata parsing), GSpread & Google Auth OAuthlib (Sheets API sync).
  - **Information Retrieval & Machine Learning**: FAISS-CPU (`IndexFlatIP`), NumPy, Google GenAI SDK (`google-genai` / `google-generativeai`), Gemini `models/gemini-embedding-001` (768-dimensional embeddings), Gemini 2.5 Flash (`gemini-2.5-flash`), Gemini 2.0 Flash (`gemini-2.0-flash`), OpenRouter API fallback (`deepseek/deepseek-chat`, Llama 3.2).
  - **Frontend UI & Extensions**: React 18, Vite, Vanilla CSS design system (dark mode, glassmorphism), native JavaScript universal autofill bookmarklet.
  - **Infrastructure & Deployment**: AWS Lambda (512MB RAM, container image runtime), Amazon ECR, Amazon EventBridge (cron trigger `cron(0 2,10,18 * * ? *)`), Docker (`Dockerfile.lambda`), Model Context Protocol (FastMCP 1.3+).
  - **Testing & Verification**: PyTest 8.1+, PyTest-Asyncio.

- **Core Pipeline Components**:
  ```
  [7 Ingestion Sources]
   ├─ Workday CXS JSON API
   ├─ Greenhouse Boards REST API
   ├─ Lever Postings REST API
   ├─ JSearch / Google for Jobs (RapidAPI)
   ├─ Adzuna Global REST API
   ├─ RemoteOK Job Feed
   └─ Microdata Schema.org Scraper (BS4)
           │
           ▼
  [Ingestion Manager & Deduplication Cache]
   (URL canonicalization, SHA-256 company+title hashing, SQLite async storage)
           │
           ▼
  [Two-Speed Evaluation Pipeline]
   ├─ Tier 1: Deterministic Experience Gating & Regex Parser (sub-5ms)
   │           └─ Disqualifies >=2 YOE; boosts GET / SDE-1 / 0-1 YOE (+15% score)
   └─ Tier 2: Hybrid RAG & Matrix Selector
               ├─ Dense Vector Channel: 768-dim Gemini embeddings + FAISS IndexFlatIP
               ├─ Sparse Keyword Channel: Subword n-gram frequency + skill weighting
               └─ Reciprocal Rank Fusion (RRF, k=60) across 4 profile variants
           │
           ▼
  [Grounding & Drafting Layer]
   ├─ Company Research & JD Grounding (Gemini 2.0 Flash)
   ├─ Tailored Resume Selection (Backend / SDE / GenAI-ML / Full-Stack)
   └─ Contextual Cover Letter Drafting (Jinja2 + Gemini 2.5 Flash)
           │
           ▼
  [Anti-Hallucination Claim Validation Guardrail]
   (Extracts technical entities & metric claims; cross-verifies with canonical profile)
           │
           ▼
  [Delivery & Action Channels]
   ├─ React + Vite Human-in-the-Loop Review Dashboard
   ├─ Google Sheets Live Sync (gspread)
   ├─ Gmail SMTP Scheduled HTML Digest Alerts
   ├─ Model Context Protocol (FastMCP) for Claude Desktop
   └─ 1-Click Universal Autofill Bookmarklet (Greenhouse, Lever, Workday, Ashby)
  ```

- **Key Algorithms, Formulations & Data Structures**:
  - **Cosine Similarity Formulation**:
    I implemented a high-performance vectorizer calculating cosine similarity over subword n-gram frequency vectors:
    $$\text{Cosine}(A, B) = \frac{\mathbf{A} \cdot \mathbf{B}}{\|\mathbf{A}\|_2 \|\mathbf{B}\|_2} = \frac{\sum_{i=1}^{n} A_i B_i}{\sqrt{\sum_{i=1}^n A_i^2} \sqrt{\sum_{i=1}^n B_i^2}}$$
    Pre-tokenization replaces domain-specific symbols (`c++` $\rightarrow$ `cpp`, `.js` $\rightarrow$ `js`, `c#` $\rightarrow$ `csharp`), filters 150+ general English stopwords, and generates adjacent bigrams for multi-word tech concepts (`full_stack`, `machine_learning`).
  - **768-Dimensional Dense Embedding Normalization**:
    Vectors produced by `models/gemini-embedding-001` undergo $L_2$ vector normalization:
    $$\hat{\mathbf{v}} = \frac{\mathbf{v}}{\max(\|\mathbf{v}\|_2, 10^{-9})}$$
    This allows FAISS `IndexFlatIP` (Inner Product) to compute exact cosine similarity via standard dot products with microsecond execution times.
  - **Deterministic Offline Embedding Fallback**:
    In offline test environments without active API keys, I engineered a deterministic 768-dimensional vector generator using SHA-256 token hashing:
    $$h = \text{SHA256}(\text{token}), \quad \text{idx} = \text{int}(h[i:i+2]) \pmod{768}, \quad \text{sign} = (+1.0 \text{ if } h[i] \bmod 2 = 0 \text{ else } -1.0)$$
    followed by $L_2$ normalization, ensuring mathematical stability and reproducible cosine tests without external network dependencies.
  - **Reciprocal Rank Fusion (RRF)**:
    To fuse disparate dense vector similarity rankings and sparse keyword match rankings without score scaling distortion, I implemented RRF with ranking constant $k=60$:
    $$\text{RRF\_Score}(d) = \sum_{m \in \{\text{dense}, \text{sparse}\}} \frac{1}{k + r_m(d)}$$
  - **Composite Fit Score Formulation**:
    $$\text{RawScore} = \left(0.45 \cdot S_{\text{semantic}} + 0.30 \cdot R_{\text{skill}} + 0.25 \cdot S_{\text{rule}}\right) \times 100$$
    $$\text{FinalScore} = \begin{cases} 
      0.0 & \text{if } S_{\text{rule}} \le 0.0 \text{ (disqualified by experience gate)} \\
      \min\left(99.0, \text{RawScore} + 15.0\right) & \text{if role matches fresher designation (GET, SDE-1)} \\
      \min\left(100.0, \text{RawScore}\right) & \text{otherwise}
    \end{cases}$$
    where $R_{\text{skill}} = \min\left(1.0, \frac{|\text{MatchedSkills}|}{\max(1, \min(|\text{ProfileSkills}|, 8))}\right)$.

## 3. Critical Technical Decisions & Trade-offs
- **Deterministic Two-Speed Filtering vs. End-to-End LLM Screening**:
  - *Decision*: I placed a sub-5ms deterministic rule and regex filter ahead of any vector embeddings or LLM invocations.
  - *Trade-off*: An LLM could theoretically catch nuanced, colloquial phrasing of experience requirements. However, passing 50–100 raw scraped job descriptions per batch to an LLM incurs 20–60 seconds of network latency and exhausts API rate limits. By enforcing deterministic regex gating first, 80%+ of senior, staff, and 3+ YOE roles are disqualified in under 3.5ms per job with $0 in API cost.
- **In-Memory FAISS IndexFlatIP + Disk Serialization vs. Cloud Vector DB (Pinecone/Weaviate)**:
  - *Decision*: I selected FAISS `IndexFlatIP` running locally in memory, serialized to disk/container storage, with a vectorized NumPy dot-product fallback.
  - *Trade-off*: A managed cloud vector database provides out-of-the-box scaling for millions of vectors. However, for a single-candidate profile partitioned into 30–100 atomic evidence chunks, calling an external vector DB over HTTPS introduces 80–200ms of network overhead and requires external API credentials. FAISS executes top-$k$ nearest neighbor search in under 0.8ms and runs seamlessly inside a 512MB RAM AWS Lambda container.
- **Deterministic Token & Regex Anti-Hallucination Guardrail vs. LLM-as-a-Judge**:
  - *Decision*: I built `ClaimValidator` using exact entity boundary matching, canonical alias dictionaries, and percentage metric extraction against original resume bullets.
  - *Trade-off*: An LLM judge could interpret loose semantic paraphrasing, but LLM evaluators are non-deterministic, prone to self-hallucination, and double generation latency. Deterministic cross-checking guarantees 100% precision on unverified metrics and unlisted tech skills, giving the candidate complete auditability.
- **Serverless EventBridge Cron vs. Long-Running Cloud Server (EC2/ECS)**:
  - *Decision*: Packaged the discovery and outreach pipeline into a minimal Docker container deployed to AWS Lambda triggered by Amazon EventBridge 3 times daily.
  - *Trade-off*: Lambda imposes a strict 15-minute execution limit and cold starts. However, continuous job scanning is an intermittent burst workload (running for ~40 seconds every 8 hours). Using Lambda + EventBridge placed the infrastructure entirely inside the AWS Perpetual Free Tier ($0/month operational expense), eliminating idle server hosting costs.

## 4. Benchmark Results & Quantifiable Metrics
- **Workloads & Datasets Evaluated**:
  - Ingestion coverage spanning 7 concurrent adapters: 65+ Greenhouse boards, 45+ Lever boards, Fortune 500 Workday CXS endpoints (Adobe, Cisco, Nvidia, Visa, Mastercard, JPMC), JSearch, and Adzuna IT feeds.
  - Evaluated across test corpora of 500+ active tech job descriptions.
  - Curated database of 198+ tech companies with direct talent acquisition contacts in `recruiter_companies.json`.
- **Latency & Throughput Benchmarks**:
  - **Deterministic Rule Gating**: $\le 3.5\text{ ms}$ per job description.
  - **Subword N-Gram Cosine Vectorizer**: $\le 1.2\text{ ms}$ per 4-variant profile comparison.
  - **FAISS Dense Retrieval (Top-8, 768 dimensions)**: $\le 0.8\text{ ms}$.
  - **Total Lambda Execution Duration**: Complete batch ingestion (50+ postings), deduplication, scoring, Google Sheets synchronization, and Gmail HTML alert dispatch completes in $32\text{ to }48\text{ seconds}$ (well within the 120-second configured Lambda timeout).
- **Resource & Memory Footprint**:
  - Container RAM utilization in AWS Lambda: $214\text{ MB}$ peak consumption (allocated: 512 MB).
  - Storage footprint: SQLite database size of $\approx 118\text{ KB}$ for 500+ indexed jobs and match scores.
- **Accuracy & Guardrail Verification Metrics**:
  - **Fresher Disqualification Precision**: $100\%$ rejection rate across unit test fixtures for postings requiring $\ge 2\text{ YOE}$ (e.g., "Associate Software Engineer" demanding 2+ years).
  - **Anti-Hallucination Catch Rate**: $100\%$ detection of fabricated quantitative claims (e.g. flagging unauthorized "improved throughput by 40%" assertions not present in authentic bullets).
  - **Zero Silent Submissions**: $0$ unreviewed applications dispatched. Strict rate-limiting caps at 10 drafted applications and 5 recruiter cold emails per day to safeguard domain deliverability.

## 5. Hardest Technical Obstacle Overcome (The "War Story")
- **The Challenge**: During early integration tests across Workday and JSearch feeds, the pipeline suffered from high false-positive rates on "entry-level" job postings. Many enterprise postings bear misleading titles like *"Associate Software Engineer"* or *"Junior Developer"*, yet their requirements section contains rigid gating clauses like *"Minimum 2-4 years of professional experience in enterprise Java required"*. Conversely, genuine entry-level opportunities containing sentences like *"You will work alongside senior engineers who have 10+ years of domain expertise"* or *"Our company has 20 years of history"* were being falsely rejected by naive regex searches for `\d+\+?\s*years?`.
- **The Diagnosis**: I profiled regex execution across a benchmark set of 120 scraped JDs. Naive global pattern matching lacked syntactic boundary awareness: it treated mentions of company age and mentor seniority as candidate experience requirements, while missing negative qualification phrasing like *"prior experience required"* without an explicit number.
- **The Solution**:
  1. I re-engineered `RuleEvaluator.extract_experience_requirements` into a multi-stage contextual window parser. The parser splits descriptions into individual sentences and executes negative lookaheads to purge clauses matching `team has`, `company has`, `mentors with`, and `years of combined experience`.
  2. I established priority regex bands: extracting explicit numbers only when bound to qualification triggers (`years of experience`, `yoe`, `prior experience`, `minimum \d+ years`).
  3. I introduced the `FresherInspectionAgent`—an LLM fallback agent utilizing OpenRouter/Gemini that performs structured zero-shot qualification evaluation on ambiguous boundary postings.
  4. I locked down the fix with dedicated regression test suites (`test_strict_fresher_rules.py`), asserting strict disqualification for 1–3 YOE requirements while granting automated $+15\%$ boosts to pure fresher programs like JPMorgan's Software Engineer Program.

## 6. Live Presentation Elevator Pitch
> *"In my project, I engineered AI Job Finder, an autonomous serverless recruiting intelligence engine that ingests opportunities across 7 multi-board feeds, filters roles with sub-5ms deterministic fresher-gating rules, and selects optimal resume variants using FAISS hybrid vector retrieval. To eliminate AI recruiter spam and interview disqualifications, I built a deterministic anti-hallucination validation pass that cross-verifies every generated claim and metric against ground-truth candidate experience before dispatching to an AWS serverless pipeline."*

## 7. Rapid-Fire Interview Talking Points (STAR Format)
- **Q: Why did you pick this specific architecture/stack?**
  - **Two-Speed Evaluation Strategy**: I decoupled fast rule-based filtering (sub-5ms) from dense vector retrieval and LLM drafting. Disqualifying 80%+ of non-fresher roles deterministically before invoking Gemini embeddings saves substantial API cost and keeps total pipeline execution under 45 seconds.
  - **Serverless EventBridge + Lambda Packaging**: By containerizing the async Python engine into an AWS Lambda image triggered 3 times daily via EventBridge, the entire multi-board aggregation, Sheets synchronization, and Gmail alerting operates 24/7 at $0/month within AWS Free Tier limits.
- **Q: How does this perform in production/under real-world noise?**
  - **Graceful Adapter Degradation**: Each of the 7 ingestion adapters (Workday, Greenhouse, Lever, Adzuna, JSearch, RemoteOK, microdata scraper) runs independently within an async task supervisor. If an API rate-limits or changes its schema, the error is isolated, logged, and the engine continues processing other sources without crashing.
  - **Strict Anti-Hallucination Validation Pass**: Instead of trusting generative models to accurately reflect credentials, my `ClaimValidator` validates skill assertions, technology aliases, and quantitative metric claims against the candidate's authentic profile facts, flagging unverified statements before any email or application is submitted.
- **Q: What would you improve in Version 2.0?**
  - **Cross-Encoder Reranking & Skill Graph Ontology**: I plan to replace the first-stage Reciprocal Rank Fusion with a lightweight cross-encoder model (e.g. `bge-reranker-base`) and build a directed skill ontology graph to capture deep relationships between frameworks (e.g., mapping asyncio concepts to event-driven architectures).
  - **Autonomous Headless Browser Agent with Playwright**: I plan to evolve the existing universal bookmarklet into an autonomous Playwright agent capable of navigating complex multi-step ATS application flows, handling file uploads, and alerting the user via Telegram/Discord only when an interactive CAPTCHA is encountered.
