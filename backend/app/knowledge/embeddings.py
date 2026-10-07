"""
Gemini Embedding Client (v2)
============================
Generates 768-dimensional semantic vector embeddings using Google's text-embedding-004.
Includes deterministic fallback for offline testing and local development without API keys.
"""

from __future__ import annotations

import math
import hashlib
import logging
from typing import List, Optional
from app.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSION = 768
DEFAULT_EMBEDDING_MODEL = "models/gemini-embedding-001"


def _l2_norm(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 1e-9:
        return [v / norm for v in vec]
    return vec


class GeminiEmbeddingClient:
    """Async client for generating text embeddings using Google GenAI SDK."""

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_EMBEDDING_MODEL):
        self.api_key = settings.GEMINI_API_KEY if api_key is None else api_key
        self.model = model
        self._genai_client = None

    def _get_client(self):
        if self._genai_client is None and self.api_key:
            try:
                from google import genai
                self._genai_client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Could not initialize google.genai client: {e}")
                self._genai_client = None
        return self._genai_client

    async def embed_text(self, text: str) -> List[float]:
        """Embed a single text string into a 768-dimensional float vector."""
        if not text or not text.strip():
            return [0.0] * EMBEDDING_DIMENSION

        client = self._get_client()
        if client:
            try:
                from google.genai import types
                config = types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSION)
                response = await client.aio.models.embed_content(
                    model=self.model,
                    contents=text.strip(),
                    config=config,
                )
                if response and response.embeddings:
                    values = response.embeddings[0].values
                    if len(values) == EMBEDDING_DIMENSION:
                        return _l2_norm(list(values))
            except Exception as e:
                logger.warning(f"Gemini embed_content call failed: {e}. Using deterministic fallback embedding.")

        # Deterministic fallback
        return self._deterministic_embedding(text)

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of text strings into float vectors."""
        if not texts:
            return []

        client = self._get_client()
        if client:
            try:
                from google.genai import types
                config = types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSION)
                clean_texts = [t.strip() if t and t.strip() else " " for t in texts]
                response = await client.aio.models.embed_content(
                    model=self.model,
                    contents=clean_texts,
                    config=config,
                )
                if response and response.embeddings:
                    return [_l2_norm(list(e.values)) for e in response.embeddings]
            except Exception as e:
                logger.warning(f"Gemini batch embed failed: {e}. Using deterministic fallback.")

        return [self._deterministic_embedding(t) for t in texts]

    @staticmethod
    def _deterministic_embedding(text: str) -> List[float]:
        """
        Generate a normalized, deterministic 768-dim float vector from text tokens.
        Preserves similarity for shared tokens even in offline/test environments.
        """
        vec = [0.0] * EMBEDDING_DIMENSION
        tokens = text.lower().split()
        if not tokens:
            vec[0] = 1.0
            return vec

        for token in tokens:
            # Hash token to pseudo-random coordinates
            h = hashlib.sha256(token.encode("utf-8")).digest()
            for i in range(0, min(len(h), 16), 2):
                idx = int.from_bytes(h[i:i+2], "big") % EMBEDDING_DIMENSION
                # Assign sign based on bit
                sign = 1.0 if (h[i] % 2 == 0) else -1.0
                vec[idx] += sign

        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 1e-9:
            vec = [v / norm for v in vec]
        else:
            vec[0] = 1.0
        return vec


# Global default client
_default_client = GeminiEmbeddingClient()


async def embed_text(text: str) -> List[float]:
    return await _default_client.embed_text(text)


async def embed_batch(texts: List[str]) -> List[List[float]]:
    return await _default_client.embed_batch(texts)
