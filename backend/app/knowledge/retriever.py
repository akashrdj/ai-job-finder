"""
Hybrid Retriever (Dense Vector + Sparse Keyword with RRF)
=========================================================
Implements dual-channel retrieval:
1. Dense semantic search via Gemini Embeddings + FAISS
2. Sparse keyword matching with skill boosting
3. Reciprocal Rank Fusion (RRF) to merge and rerank evidence chunks
"""

from __future__ import annotations

import re
import math
import logging
from typing import List, Dict, Any, Optional, Set
from pathlib import Path

from app.knowledge.chunker import ProfileChunker, load_profile_from_file, EvidenceChunk
from app.knowledge.embeddings import GeminiEmbeddingClient, embed_text, embed_batch
from app.knowledge.vector_store import ProfileVectorStore

logger = logging.getLogger(__name__)

# Stopwords for keyword matching
_STOPWORDS = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "with",
    "by", "as", "is", "are", "was", "were", "be", "been", "of", "from",
    "that", "this", "it", "we", "you", "i", "our", "your", "their", "will"
}


def _tokenize(text: str) -> List[str]:
    """Extract lowercase alpha-numeric tokens excluding stopwords."""
    words = re.findall(r"\b[a-zA-Z0-9+#.-]+\b", text.lower())
    return [w for w in words if len(w) > 1 and w not in _STOPWORDS]


class HybridRetriever:
    """Combines vector search and keyword matching with Reciprocal Rank Fusion."""

    def __init__(
        self,
        vector_store: Optional[ProfileVectorStore] = None,
        embedding_client: Optional[GeminiEmbeddingClient] = None,
        rrf_constant: int = 60
    ):
        self.vector_store = vector_store or ProfileVectorStore()
        self.embedding_client = embedding_client or GeminiEmbeddingClient()
        self.rrf_constant = rrf_constant

    async def initialize_from_profile(
        self,
        profile_data: Optional[Dict[str, Any]] = None,
        cache_dir: Optional[Path | str] = None
    ) -> int:
        """
        Populate the vector store from profile data or cached store.
        Returns the number of indexed evidence chunks.
        """
        # Try loading from cache first
        if cache_dir and self.vector_store.load(cache_dir):
            logger.info(f"Loaded {self.vector_store.count()} chunks from cache at {cache_dir}")
            return self.vector_store.count()

        data = profile_data or load_profile_from_file()
        if not data:
            logger.warning("No profile data found to initialize HybridRetriever.")
            return 0

        chunker = ProfileChunker(data)
        chunks = chunker.chunk()
        if not chunks:
            logger.warning("No evidence chunks extracted from profile.")
            return 0

        # Compute embeddings in batch
        texts_to_embed = [
            f"{c.source_detail}: {c.text} (Skills: {', '.join(c.skills)})"
            for c in chunks
        ]
        embeddings = await self.embedding_client.embed_batch(texts_to_embed)

        for chunk, emb in zip(chunks, embeddings):
            chunk.embedding = emb

        self.vector_store.add_chunks(chunks)

        if cache_dir:
            self.vector_store.save(cache_dir)

        logger.info(f"HybridRetriever initialized with {self.vector_store.count()} indexed chunks.")
        return self.vector_store.count()

    def _keyword_search(
        self,
        query_text: str,
        query_skills: Optional[List[str]] = None,
        top_k: int = 15,
        filter_source: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Token-overlap and skill-boosted keyword scoring.
        """
        query_tokens = set(_tokenize(query_text))
        target_skills_lower = {s.lower() for s in (query_skills or [])}

        scored: List[tuple[float, Dict[str, Any]]] = []

        for chunk in self.vector_store.chunks:
            if filter_source and chunk.get("source") != filter_source:
                continue

            chunk_text = chunk.get("text", "")
            chunk_tokens = set(_tokenize(chunk_text))
            chunk_skills = {s.lower() for s in chunk.get("skills", [])}

            # 1. Token overlap (Jaccard / intersection)
            shared_tokens = query_tokens.intersection(chunk_tokens)
            token_score = len(shared_tokens) / (math.log(len(chunk_tokens) + 2) + 1.0)

            # 2. Skill match bonus
            matched_skills = target_skills_lower.intersection(chunk_skills)
            skill_score = len(matched_skills) * 2.0

            # 3. Metric presence bonus
            metric_bonus = 0.5 if chunk.get("has_metric") else 0.0

            total_score = token_score + skill_score + metric_bonus
            if total_score > 0:
                chunk_copy = dict(chunk)
                chunk_copy["keyword_score"] = float(total_score)
                chunk_copy["matched_skills"] = list(matched_skills)
                scored.append((total_score, chunk_copy))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:top_k]]

    def _rrf_merge(
        self,
        vector_ranked: List[Dict[str, Any]],
        keyword_ranked: List[Dict[str, Any]],
        top_k: int = 8
    ) -> List[Dict[str, Any]]:
        """
        Reciprocal Rank Fusion (RRF):
        Combines disparate rankings without requiring score normalization.
        score = sum(1.0 / (k + rank))
        """
        chunk_map: Dict[str, Dict[str, Any]] = {}
        rrf_scores: Dict[str, float] = {}

        # Process vector ranks (1-indexed)
        for rank, chunk in enumerate(vector_ranked, start=1):
            cid = chunk["chunk_id"]
            chunk_map[cid] = chunk
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (self.rrf_constant + rank))

        # Process keyword ranks (1-indexed)
        for rank, chunk in enumerate(keyword_ranked, start=1):
            cid = chunk["chunk_id"]
            if cid not in chunk_map:
                chunk_map[cid] = chunk
            else:
                # Merge any keyword specific annotations
                chunk_map[cid]["keyword_score"] = chunk.get("keyword_score", 0.0)
                if "matched_skills" in chunk:
                    chunk_map[cid]["matched_skills"] = chunk["matched_skills"]

            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (self.rrf_constant + rank))

        sorted_cids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)

        results: List[Dict[str, Any]] = []
        for cid in sorted_cids[:top_k]:
            res = dict(chunk_map[cid])
            res["fused_score"] = float(rrf_scores[cid])
            # Ensure vector_score and keyword_score are present
            res.setdefault("vector_score", 0.0)
            res.setdefault("keyword_score", 0.0)
            results.append(res)

        return results

    async def retrieve(
        self,
        query_text: str,
        query_skills: Optional[List[str]] = None,
        top_k: int = 8,
        filter_source: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve the top_k most relevant evidence chunks for an arbitrary query.
        """
        if self.vector_store.count() == 0:
            await self.initialize_from_profile()

        if self.vector_store.count() == 0:
            return []

        # 1. Vector Search
        query_embedding = await self.embedding_client.embed_text(query_text)
        vector_results = self.vector_store.search(
            query_embedding,
            top_k=top_k * 2,
            filter_source=filter_source
        )

        # 2. Keyword Search
        keyword_results = self._keyword_search(
            query_text,
            query_skills=query_skills,
            top_k=top_k * 2,
            filter_source=filter_source
        )

        # 3. Fuse rankings via RRF
        return self._rrf_merge(vector_results, keyword_results, top_k=top_k)

    async def retrieve_evidence_for_job(
        self,
        job_title: str,
        job_description: str,
        required_skills: Optional[List[str]] = None,
        top_k: int = 8
    ) -> List[Dict[str, Any]]:
        """
        Specialized retriever for Job Descriptions:
        Formulates a high-signal search query from title, top skills, and JD text.
        """
        skills_str = ", ".join(required_skills or [])
        # Construct dense query capturing domain, role, and key technologies
        composite_query = f"{job_title}. Key requirements: {skills_str}. {job_description[:500]}"

        return await self.retrieve(
            query_text=composite_query,
            query_skills=required_skills,
            top_k=top_k
        )

    async def retrieve_for_skills(
        self,
        skills: List[str],
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Retrieve authentic evidence verifying proficiency in specific skills."""
        query = f"Proficient in {', '.join(skills)}"
        return await self.retrieve(query_text=query, query_skills=skills, top_k=top_k)


# Singleton instance
_global_retriever: Optional[HybridRetriever] = None


async def get_hybrid_retriever() -> HybridRetriever:
    """Access or lazily initialize the singleton HybridRetriever."""
    global _global_retriever
    if _global_retriever is None:
        _global_retriever = HybridRetriever()
        await _global_retriever.initialize_from_profile()
    return _global_retriever
