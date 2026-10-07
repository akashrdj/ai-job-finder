"""
Knowledge Base and Retrieval Engine (v2)
========================================
Converts candidate profile facts into atomic, verifiable evidence chunks
and powers hybrid vector (Gemini Embeddings + FAISS) + keyword (BM25/RRF) retrieval.
"""

from app.knowledge.chunker import ProfileChunker, EvidenceChunk
from app.knowledge.embeddings import GeminiEmbeddingClient, embed_text, embed_batch
from app.knowledge.vector_store import ProfileVectorStore
from app.knowledge.retriever import HybridRetriever, get_hybrid_retriever

__all__ = [
    "ProfileChunker",
    "EvidenceChunk",
    "GeminiEmbeddingClient",
    "embed_text",
    "embed_batch",
    "ProfileVectorStore",
    "HybridRetriever",
    "get_hybrid_retriever",
]
