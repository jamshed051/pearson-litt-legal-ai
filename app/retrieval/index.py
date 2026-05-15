"""
FAISS vector index: build, save, load, and search.

Each document gets its own FAISS index keyed by doc_id.
Low-confidence chunks are penalized in scoring but not excluded entirely —
the retrieval layer applies a confidence weight to the similarity score.

Evidence inspection:
  retrieve_chunks() returns RetrievedChunk objects that include:
  - the chunk text
  - the cosine similarity score
  - the OCR confidence of the source page
  - the combined relevance_score = similarity * confidence_weight
  - the chunk_id for citation in the draft
"""

from __future__ import annotations

import json
import logging
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from app.config import INDEXES_DIR, MIN_CONFIDENCE_THRESHOLD
from app.ingestion.chunker import Chunk

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """A chunk returned by the retrieval layer, with full evidence metadata."""

    chunk_id: str
    doc_id: str
    text: str
    source_page: int
    confidence: float
    similarity_score: float   # raw cosine similarity (0–1)
    relevance_score: float    # similarity × confidence_weight (used for ranking)
    chunk_index: int

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "text": self.text,
            "source_page": self.source_page,
            "confidence": self.confidence,
            "similarity_score": round(self.similarity_score, 4),
            "relevance_score": round(self.relevance_score, 4),
            "chunk_index": self.chunk_index,
        }


class DocumentIndex:
    """
    FAISS index for a single document.

    Stores:
    - embeddings matrix  (n_chunks × dim)
    - chunk metadata list (parallel to embeddings)
    """

    def __init__(self, doc_id: str):
        self.doc_id = doc_id
        self._index = None         # faiss.IndexFlatIP
        self._chunks: list[Chunk] = []

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    def build(self, chunks: list[Chunk], embeddings: np.ndarray) -> None:
        """Build the FAISS index from pre-computed embeddings."""
        import faiss

        if len(chunks) != embeddings.shape[0]:
            raise ValueError(
                f"Chunk count {len(chunks)} != embedding count {embeddings.shape[0]}"
            )

        dim = embeddings.shape[1]
        # Inner product on L2-normalized vectors = cosine similarity
        self._index = faiss.IndexFlatIP(dim)
        self._index.add(embeddings)
        self._chunks = chunks
        logger.info(
            "Built FAISS index for %s: %d chunks, dim=%d",
            self.doc_id, len(chunks), dim,
        )

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
        min_confidence: float = MIN_CONFIDENCE_THRESHOLD,
    ) -> list[RetrievedChunk]:
        """
        Retrieve top-k most relevant chunks.

        Confidence weighting:
        - Chunks with confidence < min_confidence get a 0.5× penalty
        - This keeps low-quality OCR results retrievable but deprioritized
        """
        if self._index is None or self._index.ntotal == 0:
            logger.warning("Empty index for doc %s", self.doc_id)
            return []

        k = min(top_k * 2, self._index.ntotal)  # over-fetch for confidence filtering
        scores, indices = self._index.search(query_embedding, k)

        results: list[RetrievedChunk] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:  # FAISS returns -1 for padding
                continue
            chunk = self._chunks[idx]
            # Confidence weight: penalize low-quality OCR
            conf_weight = 1.0 if chunk.confidence >= min_confidence else 0.5
            relevance = float(score) * conf_weight

            results.append(
                RetrievedChunk(
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    text=chunk.text,
                    source_page=chunk.source_page,
                    confidence=chunk.confidence,
                    similarity_score=float(score),
                    relevance_score=relevance,
                    chunk_index=chunk.chunk_index,
                )
            )

        # Sort by relevance (already sorted by similarity from FAISS, but confidence
        # weighting may change the order)
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results[:top_k]

    def save(self) -> None:
        """Persist index and chunk metadata to disk."""
        import faiss

        index_dir = INDEXES_DIR / self.doc_id
        index_dir.mkdir(parents=True, exist_ok=True)

        faiss.write_index(self._index, str(index_dir / "index.faiss"))
        with open(index_dir / "chunks.pkl", "wb") as f:
            pickle.dump(self._chunks, f)

        logger.info("Saved index for %s to %s", self.doc_id, index_dir)

    @classmethod
    def load(cls, doc_id: str) -> "DocumentIndex":
        """Load a persisted index from disk."""
        import faiss

        index_dir = INDEXES_DIR / doc_id
        if not index_dir.exists():
            raise FileNotFoundError(f"No index found for doc_id={doc_id}")

        obj = cls(doc_id)
        obj._index = faiss.read_index(str(index_dir / "index.faiss"))
        with open(index_dir / "chunks.pkl", "rb") as f:
            obj._chunks = pickle.load(f)

        logger.info(
            "Loaded index for %s: %d chunks", doc_id, len(obj._chunks)
        )
        return obj

    @classmethod
    def exists(cls, doc_id: str) -> bool:
        index_dir = INDEXES_DIR / doc_id
        return (index_dir / "index.faiss").exists()
