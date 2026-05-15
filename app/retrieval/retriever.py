"""
Retrieval pipeline: embed document chunks, build index, and retrieve evidence.

Public API:
  index_document(doc)      → builds + saves FAISS index for a ProcessedDocument
  retrieve(doc_id, query)  → returns list[RetrievedChunk] for draft generation
"""

from __future__ import annotations

import logging
from typing import Optional

from app.config import EMBEDDING_MODEL, TOP_K_CHUNKS
from app.ingestion.pipeline import ProcessedDocument
from app.retrieval.embedder import embed_query, embed_texts
from app.retrieval.index import DocumentIndex, RetrievedChunk

logger = logging.getLogger(__name__)


def index_document(doc: ProcessedDocument) -> DocumentIndex:
    """
    Build and persist a FAISS index for a processed document.

    Steps:
    1. Extract text from all chunks
    2. Compute embeddings (batch)
    3. Build FAISS index
    4. Save to disk

    Returns the built DocumentIndex.
    """
    # Filter out empty / unreadable chunks
    valid_chunks = [c for c in doc.chunks if c.text.strip() and
                    c.text != "[OCR FAILED — page unreadable]"]

    if not valid_chunks:
        logger.warning("No valid chunks to index for doc %s", doc.doc_id)
        idx = DocumentIndex(doc.doc_id)
        idx.save()
        return idx

    texts = [c.text for c in valid_chunks]
    logger.info("Embedding %d chunks for doc %s...", len(texts), doc.doc_id)
    embeddings = embed_texts(texts, model_name=EMBEDDING_MODEL)

    idx = DocumentIndex(doc.doc_id)
    idx.build(valid_chunks, embeddings)
    idx.save()
    return idx


def retrieve(
    doc_id: str,
    query: str,
    top_k: int = TOP_K_CHUNKS,
) -> list[RetrievedChunk]:
    """
    Retrieve the most relevant chunks from a document for a given query.

    Args:
        doc_id: ID of the indexed document
        query:  The drafting task description or question
        top_k:  Number of chunks to return

    Returns:
        list of RetrievedChunk objects, sorted by relevance_score descending
    """
    if not DocumentIndex.exists(doc_id):
        raise FileNotFoundError(
            f"Index not found for doc_id={doc_id}. Run index_document() first."
        )

    idx = DocumentIndex.load(doc_id)
    query_emb = embed_query(query, model_name=EMBEDDING_MODEL)
    chunks = idx.search(query_emb, top_k=top_k)

    logger.info(
        "Retrieved %d chunks for query '%s...' from %s",
        len(chunks), query[:50], doc_id,
    )
    for i, c in enumerate(chunks):
        logger.debug(
            "  [%d] %s | sim=%.3f conf=%.2f relevance=%.3f",
            i + 1, c.chunk_id, c.similarity_score, c.confidence, c.relevance_score,
        )

    return chunks


def retrieve_multi(
    doc_ids: list[str],
    query: str,
    top_k: int = TOP_K_CHUNKS,
) -> list[RetrievedChunk]:
    """
    Retrieve from multiple documents and return globally sorted top-k.
    Useful when a case spans multiple uploaded files.
    """
    all_chunks: list[RetrievedChunk] = []
    for doc_id in doc_ids:
        try:
            chunks = retrieve(doc_id, query, top_k=top_k)
            all_chunks.extend(chunks)
        except FileNotFoundError:
            logger.warning("Skipping missing index for doc_id=%s", doc_id)

    all_chunks.sort(key=lambda c: c.relevance_score, reverse=True)
    return all_chunks[:top_k]
