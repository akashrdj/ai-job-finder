from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.database import get_db
from app.models.user_profile import UserProfile
from app.schemas.profile import UserProfileCreate, UserProfileUpdate, UserProfileResponse

router = APIRouter(prefix="/api/profile", tags=["profile"])

DEFAULT_CANDIDATE_DATA = {
    "full_name": "Alex Mercer",
    "email": "alex.mercer.tech@gmail.com",
    "phone": "+1 (555) 234-5678",
    "location": "Bengaluru, India / Remote",
    "github_url": "https://github.com/alexmercer-dev",
    "linkedin_url": "https://linkedin.com/in/alexmercer-dev",
    "portfolio_url": "https://alexmercer.dev",
    "skills": [
        "Python", "FastAPI", "React", "JavaScript", "TypeScript", "SQL",
        "PostgreSQL", "MongoDB", "Redis", "Docker", "Git", "REST APIs",
        "Data Structures & Algorithms", "PyTorch", "LangChain", "Node.js"
    ],
    "work_history": [
        {
            "company": "TechVanguard Labs",
            "title": "Software Engineering Intern",
            "location": "Remote",
            "start_date": "Jan 2024",
            "end_date": "Jun 2024",
            "bullets": [
                "Built asynchronous REST API endpoints in Python & FastAPI serving 15k+ daily requests with <80ms response time.",
                "Optimized PostgreSQL relational queries and database indexing, reducing query latency by 35%.",
                "Implemented Redis caching layer and background job workers for asynchronous event processing."
            ],
            "skills_used": ["Python", "FastAPI", "PostgreSQL", "Redis", "Docker"]
        }
    ],
    "projects": [
        {
            "name": "CloudScale Distributed Pipeline",
            "role": "Lead Developer",
            "description": "An asynchronous job processing engine with automated queue throttling and resilient error retry mechanisms.",
            "bullets": [
                "Engineered async task queue in Python supporting concurrent batch ingestion with backpressure control.",
                "Integrated Docker containerization and CI/CD automated test workflows."
            ],
            "tech_stack": ["Python", "FastAPI", "PostgreSQL", "Docker", "Redis"],
            "github_url": "https://github.com/alexmercer-dev/cloudscale-pipeline"
        },
        {
            "name": "GenAI Document Insight Assistant",
            "role": "Creator",
            "description": "RAG-powered conversational search system for complex technical documentation with real-time citation tracking.",
            "bullets": [
                "Implemented semantic vector search using embeddings and cosine similarity with grounded fact-checking.",
                "Built responsive full-stack interface in React and TypeScript."
            ],
            "tech_stack": ["Python", "LangChain", "PyTorch", "React", "TypeScript", "FastAPI"],
            "github_url": "https://github.com/alexmercer-dev/genai-assistant"
        },
        {
            "name": "Modern Full-Stack Task Hub",
            "role": "Full-Stack Engineer",
            "description": "Real-time task management application with collaborative state synchronization and JWT authentication.",
            "bullets": [
                "Built responsive UI in React with custom fluid components and CSS design system.",
                "Designed normalized relational database schema with PostgreSQL."
            ],
            "tech_stack": ["React", "TypeScript", "Node.js", "PostgreSQL", "TailwindCSS"],
            "github_url": "https://github.com/alexmercer-dev/fullstack-task-hub"
        }
    ],
    "education": [
        {
            "institution": "National Institute of Technology",
            "degree": "Bachelor of Technology",
            "field_of_study": "Computer Science & Engineering",
            "graduation_year": "2024",
            "cgpa_or_grade": "8.8 / 10.0"
        }
    ],
    "curated_variants": {
        "backend": {
            "title": "Backend Software Engineer",
            "summary": "Results-driven Software Engineer with strong background in Python, FastAPI, PostgreSQL, and distributed async systems. Proven ability to design high-throughput REST APIs, database indexing, and caching architectures with clean, testable code.",
            "highlighted_skills": ["Python", "FastAPI", "PostgreSQL", "Redis", "Docker", "REST APIs", "Microservices"],
            "key_bullet_points": [
                "Built high-performance async APIs handling 15k+ daily requests with <80ms latency.",
                "Engineered resilient distributed queuing pipelines with Redis and PostgreSQL optimization.",
                "Deep understanding of system design, relational data modeling, and concurrency."
            ],
            "cover_letter_template": "Dear Hiring Team at {{ company }},\n\nI am writing to express my strong enthusiasm for the {{ role }} position. With hands-on experience designing asynchronous backend services in Python, FastAPI, and PostgreSQL, I am eager to contribute to {{ company }}'s backend architecture.\n\n{{ summary }}\n\nIn my recent work, I {{ top_project_bullet }} Using {{ top_project_tech }}, I prioritized API throughput, clean schema design, and modular service boundaries.\n\nI would welcome the opportunity to bring my technical foundation and fast learning curve to {{ company }}. Thank you for your consideration!\n\nBest regards,\n{{ candidate_name }}\n{{ email }} | {{ phone }}"
        },
        "sde": {
            "title": "General SDE / Software Engineer",
            "summary": "Versatile Software Engineer with strong computer science fundamentals, data structures, algorithms, and problem-solving skills. Experienced in building robust end-to-end software, writing clean modular code, and rapidly mastering new technologies.",
            "highlighted_skills": ["Data Structures & Algorithms", "Python", "JavaScript", "SQL", "Git", "OOP", "System Design"],
            "key_bullet_points": [
                "Solid foundation in Algorithms, Data Structures, and Object-Oriented Design.",
                "Track record of shipping production-grade features across the full stack.",
                "Passionate about code quality, automated testing, and developer collaboration."
            ],
            "cover_letter_template": "Dear Hiring Team at {{ company }},\n\nI am thrilled to apply for the {{ role }} opening at {{ company }}. As a Software Engineer with a solid foundation in computer science principles and hands-on experience across the stack, I am eager to help build reliable software at {{ company }}.\n\n{{ summary }}\n\nRecently, I {{ top_project_bullet }} Leveraging {{ top_project_tech }}, I applied strong algorithmic thinking to deliver performant and maintainable solutions.\n\nI look forward to discussing how my skills and proactive attitude will benefit your team.\n\nSincerely,\n{{ candidate_name }}\n{{ email }} | {{ phone }}"
        },
        "genai_ml": {
            "title": "GenAI & Machine Learning Engineer",
            "summary": "AI/ML focused Engineer with hands-on expertise building LLM-powered applications, RAG pipelines, semantic search, vector embeddings, and Python microservices. Passionate about creating fact-grounded, reliable AI products.",
            "highlighted_skills": ["Python", "PyTorch", "LangChain", "Vector Embeddings", "RAG", "FastAPI", "Prompt Engineering"],
            "key_bullet_points": [
                "Developed RAG question-answering systems with semantic chunking and citation verification.",
                "Implemented vector similarity search and custom embedding evaluation pipelines.",
                "Integrated LLM APIs with deterministic guardrails to prevent hallucinations."
            ],
            "cover_letter_template": "Dear Hiring Team at {{ company }},\n\nI am writing to apply for the {{ role }} role at {{ company }}. With hands-on experience developing LLM pipelines, vector search, and AI-driven applications in Python and PyTorch, I am excited by {{ company }}'s AI initiatives.\n\n{{ summary }}\n\nIn my recent project, I {{ top_project_bullet }} Utilizing {{ top_project_tech }}, I focused on verifiable factual grounding and low-latency inference.\n\nI am eager to bring my passion for practical AI engineering to your team.\n\nBest regards,\n{{ candidate_name }}\n{{ email }} | {{ phone }}"
        },
        "fullstack": {
            "title": "Full-Stack Engineer",
            "summary": "Full-Stack Software Engineer skilled in building modern, responsive user interfaces in React/TypeScript combined with scalable async backend APIs in Python and Node.js. Focused on seamless user experiences and robust API integrations.",
            "highlighted_skills": ["React", "TypeScript", "JavaScript", "Python", "FastAPI", "PostgreSQL", "HTML5/CSS3"],
            "key_bullet_points": [
                "Built responsive, accessible web interfaces with modern state management in React.",
                "Connected full-stack frontends with async REST API backends and PostgreSQL databases.",
                "Ensured fluid responsiveness, micro-interactions, and fast time-to-interactive."
            ],
            "cover_letter_template": "Dear Hiring Team at {{ company }},\n\nI am writing to apply for the {{ role }} position at {{ company }}. With full-stack experience spanning modern React/TypeScript frontends and Python/PostgreSQL backends, I am excited about the prospect of building delightful end-to-end features for {{ company }}.\n\n{{ summary }}\n\nRecently, I {{ top_project_bullet }} Combining {{ top_project_tech }}, I delivered an intuitive user experience backed by scalable backend services.\n\nThank you for considering my application, and I look forward to speaking with your team!\n\nWarm regards,\n{{ candidate_name }}\n{{ email }} | {{ phone }}"
        }
    },
    "preferences": {
        "target_roles": [
            "Software Engineer", "Backend Developer", "Full Stack Developer",
            "Python Developer", "AI Engineer", "Data Engineer",
            "Graduate Engineer Trainee", "Associate Software Engineer",
            "Junior Developer", "Software Developer Intern", "SDE-1"
        ],
        "max_yoe": 1,
        "remote_only": False,
        "preferred_locations": [
            "Remote", "Bengaluru", "Bangalore", "Hyderabad", "Pune",
            "Delhi NCR", "Gurgaon", "Noida", "Mumbai", "Chennai"
        ],
        "min_salary": 0,
        "excluded_companies": [],
        "excluded_keywords": [
            "Staff Engineer", "Principal Engineer", "Director",
            "8+ years", "10+ years", "12+ years"
        ]
    }
}

@router.get("", response_model=UserProfileResponse)
async def get_active_profile(db: AsyncSession = Depends(get_db)):
    stmt = select(UserProfile).where(UserProfile.is_active == True)
    profile = (await db.execute(stmt)).scalars().first()

    if not profile:
        # Seed default initial candidate profile
        profile = UserProfile(**DEFAULT_CANDIDATE_DATA)
        db.add(profile)
        await db.commit()
        await db.refresh(profile)

    return profile

@router.post("", response_model=UserProfileResponse)
async def update_profile(data: UserProfileCreate, db: AsyncSession = Depends(get_db)):
    stmt = select(UserProfile).where(UserProfile.is_active == True)
    profile = (await db.execute(stmt)).scalars().first()

    if not profile:
        profile = UserProfile(**data.model_dump())
        db.add(profile)
    else:
        for key, val in data.model_dump().items():
            setattr(profile, key, val)

    await db.commit()
    await db.refresh(profile)
    return profile
