"""
Text chunker: splits extracted document text into overlapping chunks
suitable for embedding and retrieval.

Design decisions:
- 500–700 char chunks with 100-char overlap (as recommended in architecture plan)
- Chunk at sentence/paragraph boundaries where possible (reduces mid-sentence splits)
- Each chunk carries its source page and OCR confidence for downstream filtering
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

from app.ingestion.extractor import ExtractedDocument, RawPage


@dataclass
class Chunk:
    """A single text chunk ready for embedding."""

    chunk_id: str
    doc_id: str
    text: str
    source_page: int
    confidence: float  # inherited from source page
    extraction_method: str
    char_start: int  # approximate character offset in full_text
    chunk_index: int  # 0-based index within the document

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "text": self.text,
            "source_page": self.source_page,
            "confidence": self.confidence,
            "extraction_method": self.extraction_method,
            "char_start": self.char_start,
            "chunk_index": self.chunk_index,
        }


def _split_into_sentences(text: str) -> list[str]:
    """
    Split text into sentence-like units.
    Handles legal text patterns (e.g., numbered clauses, bullet points).
    """
    # Split on sentence-ending punctuation, numbered items, or paragraph breaks
    sentence_endings = re.compile(
        r"(?<=[.!?])\s+(?=[A-Z])"  # sentence end → capital
        r"|(?<=\n)(?=\d+[.)]\s)"   # numbered list items
        r"|\n{2,}"                  # paragraph breaks
    )
    parts = sentence_endings.split(text)
    return [p.strip() for p in parts if p.strip()]


def chunk_document(
    doc: ExtractedDocument,
    chunk_size: int = 600,
    overlap: int = 100,
) -> list[Chunk]:
    """
    Chunk an extracted document into overlapping text segments.

    Strategy:
    1. Process page-by-page to preserve source_page attribution
    2. Within each page, split at sentence/paragraph boundaries
    3. Accumulate sentences into chunks ~chunk_size chars
    4. Add overlap by carrying last N chars of previous chunk into next
    """
    chunks: list[Chunk] = []
    chunk_index = 0
    carry_over = ""  # overlap text carried from previous chunk

    for page in doc.pages:
        if not page.text.strip():
            continue

        text = page.text
        sentences = _split_into_sentences(text)

        current_chunk_text = carry_over
        current_start = 0

        for sentence in sentences:
            candidate = (current_chunk_text + " " + sentence).strip()

            if len(candidate) <= chunk_size:
                current_chunk_text = candidate
            else:
                # Emit the current chunk if it has content
                if current_chunk_text.strip():
                    chunk_id = f"{doc.doc_id}_chunk_{chunk_index:04d}"
                    chunks.append(
                        Chunk(
                            chunk_id=chunk_id,
                            doc_id=doc.doc_id,
                            text=current_chunk_text.strip(),
                            source_page=page.page_num,
                            confidence=page.confidence,
                            extraction_method=page.extraction_method,
                            char_start=current_start,
                            chunk_index=chunk_index,
                        )
                    )
                    chunk_index += 1

                    # Carry overlap: last `overlap` chars of the emitted chunk
                    carry_over = current_chunk_text[-overlap:].strip() if len(
                        current_chunk_text
                    ) > overlap else current_chunk_text
                    current_start += len(current_chunk_text) - overlap

                current_chunk_text = (carry_over + " " + sentence).strip()

        # Emit remaining text in this page
        if current_chunk_text.strip():
            chunk_id = f"{doc.doc_id}_chunk_{chunk_index:04d}"
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    doc_id=doc.doc_id,
                    text=current_chunk_text.strip(),
                    source_page=page.page_num,
                    confidence=page.confidence,
                    extraction_method=page.extraction_method,
                    char_start=current_start,
                    chunk_index=chunk_index,
                )
            )
            chunk_index += 1
            carry_over = current_chunk_text[-overlap:].strip()

    return chunks
