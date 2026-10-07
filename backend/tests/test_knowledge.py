"""
Unit & Integration Tests for Knowledge Base & Hybrid Retrieval (Phase 1)
========================================================================
Validates atomic profile chunking, Gemini/fallback embeddings, FAISS vector store,
and hybrid RRF retrieval accuracy.
"""

import pytest
import numpy as np
from pathlib import Path

from app.knowledge.chunker import (
    ProfileChunker,
    EvidenceChunk,
    detect_ownership,
    detect_metrics,
    extract_matched_skills,
    load_profile_from_file,
)
from app.knowledge.embeddings import (
    GeminiEmbeddingClient,
    embed_text,
    embed_batch,
    EMBEDDING_DIMENSION,
)
from app.knowledge.vector_store import ProfileVectorStore
from app.knowledge.retriever import HybridRetriever


SAMPLE_PROFILE = {
    "full_name": "Akash R Jadhav",
    "email": "akash@example.com",
    "skills": ["Python", "FastAPI", "Java", "OpenTelemetry", "PyTorch", "Docker", "Grafana", "Prometheus"],
    "work_history": [
        {
            "company": "CitiusTech (Client: Evident Microscopy)",
            "title": "Developer Intern",
            "start_date": "May 2026",
            "end_date": "Aug 2026",
            "bullets": [
                "Designed and deployed an end-to-end, zero-code telemetry pipeline using OpenTelemetry Java Agent, Collector, Prometheus, Loki, and Grafana for full-stack observability.",
                "Engineered a low-latency shared-memory ring buffer (MappedByteBuffer) using custom OTLP-compliant reader/writers for real-time telemetry streaming."
            ],
            "skills_used": ["Java", "OpenTelemetry", "Grafana", "Prometheus"]
        }
    ],
    "projects": [
        {
            "name": "AI Job Finder",
            "role": "Creator / Cloud Architect",
            "description": "Serverless job aggregation pipeline that ingests fresher-targeted roles from 7 sources.",
            "bullets": [
                "Built a serverless job aggregation pipeline that ingests fresher-targeted roles from 7 sources and scores fit with 82% accuracy.",
                "Implemented a human-in-the-loop Vite + React review dashboard."
            ],
            "tech_stack": ["Python", "FastAPI", "React", "Docker"]
        }
    ],
    "education": [
        {
            "institution": "PES University",
            "degree": "Bachelor of Technology",
            "field_of_study": "Computer Science and Engineering",
            "graduation_year": "2026",
            "cgpa_or_grade": "8.00 / 10.0"
        }
    ],
    "certifications": [
        "Oracle Cloud Infrastructure 2025 Multicloud Architect Professional"
    ]
}


# --- Chunker Tests ---

def test_detect_ownership():
    assert detect_ownership("Architected a multi-cloud serverless backend") == "led"
    assert detect_ownership("Engineered low-latency shared-memory ring buffer") == "built"
    assert detect_ownership("Designed and deployed an end-to-end telemetry pipeline") == "built"
    assert detect_ownership("Assisted senior engineers in bug resolution") == "contributed"
    assert detect_ownership("Utilized Git for version control") == "used"


def test_detect_metrics():
    assert detect_metrics("Achieved 82% accuracy on validation dataset") is True
    assert detect_metrics("Ingested roles from 7 sources") is True
    assert detect_metrics("Scored CGPA of 8.00 / 10.0") is True
    assert detect_metrics("Developed software modules using clean code") is False


def test_extract_matched_skills():
    skills = ["Python", "FastAPI", "OpenTelemetry", "Java", "Docker"]
    text = "Built a telemetry streaming pipeline using OpenTelemetry and Java for real-time metrics."
    matched = extract_matched_skills(text, skills)
    assert "OpenTelemetry" in matched
    assert "Java" in matched
    assert "Python" not in matched


def test_profile_chunking():
    chunker = ProfileChunker(SAMPLE_PROFILE)
    chunks = chunker.chunk()

    assert len(chunks) >= 6
    chunk_ids = [c.chunk_id for c in chunks]

    # Verify work history chunk
    otel_chunk = next((c for c in chunks if "citiustech" in c.chunk_id and "bullet_1" in c.chunk_id), None)
    assert otel_chunk is not None
    assert "OpenTelemetry" in otel_chunk.skills
    assert otel_chunk.ownership_level == "built"

    # Verify project chunk with metric
    job_finder_chunk = next((c for c in chunks if "ai_job_finder" in c.chunk_id and "bullet_1" in c.chunk_id), None)
    assert job_finder_chunk is not None
    assert job_finder_chunk.has_metric is True
    assert "Python" in job_finder_chunk.skills

    # Verify education chunk
    edu_chunk = next((c for c in chunks if c.source == "education"), None)
    assert edu_chunk is not None
    assert "8.00" in edu_chunk.text


def test_chunk_real_profile():
    data = load_profile_from_file()
    assert data, "Should find and load my_profile.json from repo"
    chunker = ProfileChunker(data)
    chunks = chunker.chunk()
    assert len(chunks) >= 20, f"Expected at least 20 chunks from my_profile.json, got {len(chunks)}"


# --- Embeddings Tests ---

@pytest.mark.asyncio
async def test_deterministic_embedding_properties():
    client = GeminiEmbeddingClient(api_key="")  # Force deterministic mode
    emb1 = await client.embed_text("OpenTelemetry observability pipeline")
    emb2 = await client.embed_text("OpenTelemetry observability pipeline")
    emb3 = await client.embed_text("Culinary baking recipes and pastry")

    assert len(emb1) == EMBEDDING_DIMENSION
    assert emb1 == emb2, "Embeddings for identical text must be identical"

    # Check L2 normalization
    norm = np.linalg.norm(np.array(emb1))
    assert np.isclose(norm, 1.0, atol=1e-3)

    # Cosine similarity between related vs unrelated
    sim_related = np.dot(emb1, emb2)
    sim_unrelated = np.dot(emb1, emb3)
    assert sim_related > sim_unrelated


@pytest.mark.asyncio
async def test_embed_batch():
    texts = ["FastAPI web backend", "PyTorch neural network", "Docker containerization"]
    embs = await embed_batch(texts)
    assert len(embs) == 3
    for emb in embs:
        assert len(emb) == EMBEDDING_DIMENSION


# --- Vector Store Tests ---

def test_vector_store_add_and_search(tmp_path):
    store = ProfileVectorStore(dimension=4)

    # Fake 4-dimensional chunks
    chunks = [
        EvidenceChunk(
            chunk_id="c1",
            text="Python backend developer with FastAPI",
            source="projects",
            source_detail="Project A",
            skills=["Python", "FastAPI"],
            embedding=[1.0, 0.0, 0.0, 0.0]
        ),
        EvidenceChunk(
            chunk_id="c2",
            text="Computer Vision engineer with PyTorch",
            source="work_history",
            source_detail="Internship B",
            skills=["PyTorch"],
            embedding=[0.0, 1.0, 0.0, 0.0]
        ),
    ]

    store.add_chunks(chunks)
    assert store.count() == 2

    # Query closest to c1
    results = store.search([1.0, 0.1, 0.0, 0.0], top_k=2)
    assert len(results) == 2
    assert results[0]["chunk_id"] == "c1"
    assert results[0]["vector_score"] > results[1]["vector_score"]

    # Test filtering by source
    work_results = store.search([1.0, 0.0, 0.0, 0.0], top_k=2, filter_source="work_history")
    assert len(work_results) == 1
    assert work_results[0]["chunk_id"] == "c2"

    # Test save and load roundtrip
    assert store.save(tmp_path) is True
    new_store = ProfileVectorStore(dimension=4)
    assert new_store.load(tmp_path) is True
    assert new_store.count() == 2
    reloaded_res = new_store.search([0.0, 1.0, 0.0, 0.0], top_k=1)
    assert reloaded_res[0]["chunk_id"] == "c2"


# --- Hybrid Retriever Tests ---

@pytest.mark.asyncio
async def test_hybrid_retriever_e2e():
    retriever = HybridRetriever()
    indexed_count = await retriever.initialize_from_profile(profile_data=SAMPLE_PROFILE)
    assert indexed_count > 0

    # Query for Observability / Telemetry role
    results = await retriever.retrieve_evidence_for_job(
        job_title="Observability / SRE Engineer",
        job_description="Looking for an engineer with Java, OpenTelemetry, Prometheus, and Grafana to build telemetry pipelines.",
        required_skills=["OpenTelemetry", "Grafana", "Prometheus", "Java"],
        top_k=3
    )

    assert len(results) > 0
    top_chunk = results[0]
    assert "OpenTelemetry" in top_chunk["skills"] or "Grafana" in top_chunk["skills"]
    assert top_chunk.get("fused_score", 0.0) > 0.0
    assert "vector_score" in top_chunk
    assert "keyword_score" in top_chunk


@pytest.mark.asyncio
async def test_hybrid_retriever_skill_search():
    retriever = HybridRetriever()
    await retriever.initialize_from_profile(profile_data=SAMPLE_PROFILE)

    evidence = await retriever.retrieve_for_skills(["FastAPI", "Python"], top_k=3)
    assert len(evidence) > 0
    matched_skills = [s for item in evidence for s in item.get("skills", [])]
    assert "FastAPI" in matched_skills or "Python" in matched_skills
