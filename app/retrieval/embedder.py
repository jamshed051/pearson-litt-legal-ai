"""
Embedding module: converts text chunks into dense vectors using sentence-transformers.

Design:
- Singleton model instance (loaded once, reused)
- Batch encoding for efficiency
- Returns numpy float32 arrays compatible with FAISS
"""

from __future__ import annotations

import logging
import numpy as np
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

# Module-level model cache
_model = None


def get_model(model_name: str = "all-MiniLM-L6-v2"):
    """Load sentence-transformer model (singleton)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading embedding model: %s", model_name)
        _model = SentenceTransformer(model_name)
        logger.info("Embedding model loaded. Dimension: %d", _model.get_sentence_embedding_dimension())
    return _model


def embed_texts(texts: list[str], model_name: str = "all-MiniLM-L6-v2") -> np.ndarray:
    """
    Embed a list of texts into dense vectors.

    Returns:
        numpy array of shape (n_texts, embedding_dim), dtype float32
    """
    if not texts:
        return np.empty((0, 384), dtype=np.float32)

    model = get_model(model_name)
    embeddings = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=False,
        normalize_embeddings=True,  # L2-normalize for cosine similarity via dot product
        convert_to_numpy=True,
    )
    return embeddings.astype(np.float32)


def embed_query(query: str, model_name: str = "all-MiniLM-L6-v2") -> np.ndarray:
    """
    Embed a single query string.

    Returns:
        numpy array of shape (1, embedding_dim), dtype float32
    """
    return embed_texts([query], model_name=model_name)
