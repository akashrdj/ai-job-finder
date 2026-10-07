"""
FAISS-Backed Vector Store for Profile Evidence Chunks
=====================================================
Indexes evidence chunks using FAISS IndexFlatIP (cosine similarity)
with fast metadata filtering, disk serialization, and numpy fallback.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
import numpy as np

try:
    import faiss
    _FAISS_AVAILABLE = True
except ImportError:
    _FAISS_AVAILABLE = False

from app.knowledge.chunker import EvidenceChunk

logger = logging.getLogger(__name__)


class ProfileVectorStore:
    """In-memory vector store using FAISS (or NumPy fallback) for candidate evidence."""

    def __init__(self, dimension: int = 768):
        self.dimension = dimension
        self.chunks: List[Dict[str, Any]] = []
        self._index = None
        self._vectors_cache: Optional[np.ndarray] = None
        self._init_index()

    def _init_index(self):
        if _FAISS_AVAILABLE:
            self._index = faiss.IndexFlatIP(self.dimension)
        else:
            self._index = None
            logger.warning("FAISS not available; utilizing NumPy vectorized dot product fallback.")

    def add_chunks(self, chunks: List[Union[EvidenceChunk, Dict[str, Any]]]):
        """Add evidence chunks with pre-computed embeddings into the vector index."""
        if not chunks:
            return

        normalized_chunks: List[Dict[str, Any]] = []
        vectors_to_add: List[List[float]] = []

        for c in chunks:
            data = c.to_dict() if isinstance(c, EvidenceChunk) else dict(c)
            emb = data.get("embedding")
            if not emb or len(emb) != self.dimension:
                logger.debug(f"Skipping chunk {data.get('chunk_id')}: missing or invalid embedding dimensions.")
                continue

            normalized_chunks.append(data)
            vectors_to_add.append(emb)

        if not vectors_to_add:
            logger.warning("No valid vectors to add to ProfileVectorStore.")
            return

        arr = np.array(vectors_to_add, dtype="float32")
        # Normalize vectors for cosine similarity (Inner Product)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        arr = arr / norms

        if _FAISS_AVAILABLE and self._index is not None:
            self._index.add(arr)
        else:
            if self._vectors_cache is None:
                self._vectors_cache = arr
            else:
                self._vectors_cache = np.vstack([self._vectors_cache, arr])

        self.chunks.extend(normalized_chunks)
        logger.info(f"Vector store now holds {len(self.chunks)} evidence vectors.")

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filter_source: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for most relevant evidence chunks given a query embedding.
        Returns top_k chunks sorted by cosine similarity.
        """
        if not self.chunks:
            return []

        q_vec = np.array([query_embedding], dtype="float32")
        q_norm = np.linalg.norm(q_vec)
        if q_norm > 0:
            q_vec = q_vec / q_norm

        # If filtering by source, retrieve more candidates first
        fetch_k = min(len(self.chunks), top_k * 3 if filter_source else top_k)
        results: List[Dict[str, Any]] = []

        if _FAISS_AVAILABLE and self._index is not None and self._index.ntotal > 0:
            scores, indices = self._index.search(q_vec, fetch_k)
            for j, idx in enumerate(indices[0]):
                if idx < 0 or idx >= len(self.chunks):
                    continue
                chunk_copy = dict(self.chunks[idx])
                chunk_copy["vector_score"] = float(scores[0][j])
                if filter_source and chunk_copy.get("source") != filter_source:
                    continue
                results.append(chunk_copy)
                if len(results) >= top_k:
                    break
        else:
            # NumPy vectorized fallback
            if self._vectors_cache is None and self.chunks:
                # Rebuild matrix from chunk embeddings
                all_embs = [c["embedding"] for c in self.chunks]
                self._vectors_cache = np.array(all_embs, dtype="float32")
                norms = np.linalg.norm(self._vectors_cache, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                self._vectors_cache = self._vectors_cache / norms

            if self._vectors_cache is not None and len(self._vectors_cache) > 0:
                sims = np.dot(self._vectors_cache, q_vec.T).flatten()
                ranked_indices = np.argsort(-sims)
                for idx in ranked_indices:
                    chunk_copy = dict(self.chunks[idx])
                    chunk_copy["vector_score"] = float(sims[idx])
                    if filter_source and chunk_copy.get("source") != filter_source:
                        continue
                    results.append(chunk_copy)
                    if len(results) >= top_k:
                        break

        return results

    def save(self, dir_path: Union[str, Path]) -> bool:
        """Serialize index and chunks to disk."""
        target_dir = Path(dir_path)
        target_dir.mkdir(parents=True, exist_ok=True)

        try:
            chunks_path = target_dir / "profile_chunks.json"
            with open(chunks_path, "w", encoding="utf-8") as f:
                json.dump(self.chunks, f, indent=2)

            if _FAISS_AVAILABLE and self._index is not None:
                index_path = target_dir / "profile_index.faiss"
                faiss.write_index(self._index, str(index_path))

            logger.info(f"Saved ProfileVectorStore to {target_dir}")
            return True
        except Exception as e:
            logger.error(f"Failed to save vector store to {target_dir}: {e}")
            return False

    def load(self, dir_path: Union[str, Path]) -> bool:
        """Load index and chunks from disk if they exist."""
        target_dir = Path(dir_path)
        chunks_path = target_dir / "profile_chunks.json"
        if not chunks_path.exists():
            return False

        try:
            with open(chunks_path, "r", encoding="utf-8") as f:
                self.chunks = json.load(f)

            index_path = target_dir / "profile_index.faiss"
            if _FAISS_AVAILABLE and index_path.exists():
                self._index = faiss.read_index(str(index_path))
            else:
                self._init_index()
                # Re-add vectors
                if self.chunks:
                    vecs = [c["embedding"] for c in self.chunks if "embedding" in c]
                    if vecs:
                        arr = np.array(vecs, dtype="float32")
                        norms = np.linalg.norm(arr, axis=1, keepdims=True)
                        norms[norms == 0] = 1.0
                        arr = arr / norms
                        if _FAISS_AVAILABLE and self._index is not None:
                            self._index.add(arr)
                        else:
                            self._vectors_cache = arr

            logger.info(f"Loaded ProfileVectorStore from {target_dir} ({len(self.chunks)} items).")
            return True
        except Exception as e:
            logger.error(f"Failed to load vector store from {target_dir}: {e}")
            return False

    def count(self) -> int:
        return len(self.chunks)

    def clear(self):
        self.chunks.clear()
        self._vectors_cache = None
        self._init_index()
