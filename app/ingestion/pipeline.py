"""
Ingestion pipeline: orchestrates extraction → chunking → metadata extraction → persistence.

Entry point: ingest_document(path) → ProcessedDocument
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    DOCUMENTS_DIR,
    TEXT_EXTRACTION_MIN_CHARS,
)
from app.ingestion.chunker import Chunk, chunk_document
from app.ingestion.extractor import ExtractedDocument, extract_document
from app.ingestion.metadata_extractor import extract_metadata

logger = logging.getLogger(__name__)


@dataclass
class ProcessedDocument:
    """Full output of the ingestion pipeline for a single document."""

    doc_id: str
    source_path: str
    file_type: str
    metadata: dict
    chunks: list[Chunk]
    avg_confidence: float
    total_chars: int
    page_count: int

    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "source_path": self.source_path,
            "file_type": self.file_type,
            "metadata": self.metadata,
            "chunks": [c.to_dict() for c in self.chunks],
            "avg_confidence": self.avg_confidence,
            "total_chars": self.total_chars,
            "page_count": self.page_count,
        }


def ingest_document(
    path: Path,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
    min_chars: int = TEXT_EXTRACTION_MIN_CHARS,
    save: bool = True,
) -> ProcessedDocument:
    """
    Full ingestion pipeline:
    1. Extract text (with OCR fallback for scanned pages)
    2. Chunk text with overlap
    3. Extract structured metadata
    4. Persist to data/documents/{doc_id}.json

    Args:
        path: Path to the document (PDF or image)
        chunk_size: Target chars per chunk
        overlap: Overlap chars between consecutive chunks
        min_chars: Min chars per page before OCR fallback triggers
        save: Whether to persist the result to disk

    Returns:
        ProcessedDocument with chunks ready for embedding
    """
    logger.info("Ingesting document: %s", path.name)

    # Step 1: Extract text
    extracted: ExtractedDocument = extract_document(path, min_chars=min_chars)
    logger.info(
        "Extracted %d pages, avg confidence=%.2f, method breakdown: %s",
        len(extracted.pages),
        extracted.avg_confidence,
        {m: sum(1 for p in extracted.pages if p.extraction_method == m)
         for m in set(p.extraction_method for p in extracted.pages)},
    )

    # Step 2: Chunk
    chunks: list[Chunk] = chunk_document(extracted, chunk_size=chunk_size, overlap=overlap)
    logger.info("Created %d chunks from %s", len(chunks), path.name)

    # Step 3: Extract metadata from full text
    metadata = extract_metadata(extracted.full_text, extracted.doc_id)
    logger.info(
        "Metadata: type=%s, parties=%d, dates=%d",
        metadata["document_type"],
        len(metadata["parties"]),
        len(metadata["dates"]),
    )

    processed = ProcessedDocument(
        doc_id=extracted.doc_id,
        source_path=str(path),
        file_type=extracted.file_type,
        metadata=metadata,
        chunks=chunks,
        avg_confidence=extracted.avg_confidence,
        total_chars=sum(p.char_count for p in extracted.pages),
        page_count=len(extracted.pages),
    )

    # Step 4: Persist
    if save:
        out_path = DOCUMENTS_DIR / f"{extracted.doc_id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(processed.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info("Saved processed document to %s", out_path)

    return processed


def load_processed_document(doc_id: str) -> ProcessedDocument:
    """Load a previously ingested document from disk."""
    from app.ingestion.chunker import Chunk

    doc_path = DOCUMENTS_DIR / f"{doc_id}.json"
    if not doc_path.exists():
        raise FileNotFoundError(f"No processed document found for doc_id={doc_id}")

    with open(doc_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    chunks = [Chunk(**c) for c in data["chunks"]]
    return ProcessedDocument(
        doc_id=data["doc_id"],
        source_path=data["source_path"],
        file_type=data["file_type"],
        metadata=data["metadata"],
        chunks=chunks,
        avg_confidence=data["avg_confidence"],
        total_chars=data["total_chars"],
        page_count=data["page_count"],
    )
