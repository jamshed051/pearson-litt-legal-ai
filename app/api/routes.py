"""
FastAPI routes for the Legal Draft Assistant MVP.

Endpoints:
  POST /ingest              Upload and process a document
  GET  /documents           List processed documents
  GET  /documents/{doc_id}  Get document metadata and chunks
  POST /draft               Generate a grounded Case Fact Summary Memo
  GET  /draft/{draft_id}    Retrieve a draft
  POST /edit                Submit operator edit (triggers learning loop)
  GET  /memory              Inspect the correction memory
  GET  /health              Health check
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import DOCUMENTS_DIR, DRAFTS_DIR
from app.drafting.generator import generate_draft, load_draft, save_edited_draft
from app.ingestion.pipeline import ingest_document, load_processed_document
from app.learning.correction_memory import (
    get_active_preferences,
    get_full_memory,
    process_edit,
)
from app.retrieval.retriever import index_document, retrieve

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request / Response Models ─────────────────────────────────────────────────

class DraftRequest(BaseModel):
    doc_id: str
    query: Optional[str] = "Generate a comprehensive case fact summary memo"
    top_k: int = 5


class EditRequest(BaseModel):
    draft_id: str
    edited_text: str


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/health")
def health_check():
    """Quick health check."""
    return {"status": "ok", "service": "Legal Draft Assistant MVP"}


@router.post("/ingest")
async def ingest(file: UploadFile = File(...)):
    """
    Upload and process a document (PDF or image).

    Pipeline:
    1. Save upload to temp file
    2. Extract text (OCR if needed)
    3. Chunk and embed
    4. Build FAISS index
    5. Return doc_id and extraction summary
    """
    allowed_types = {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/tiff",
        "image/bmp",
    }
    # Also allow by extension in case content-type is wrong
    allowed_extensions = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}
    suffix = Path(file.filename or "upload").suffix.lower()

    if suffix not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Supported: {allowed_extensions}",
        )

    # Derive a clean doc_id from the original filename (strip extension, sanitize)
    import re as _re
    original_stem = Path(file.filename or "upload").stem
    clean_doc_id = _re.sub(r"[^a-zA-Z0-9_-]", "_", original_stem).strip("_") or "document"

    # Save to a temp file named after the original stem so doc_id is meaningful
    tmp_path = Path(tempfile.gettempdir()) / f"{clean_doc_id}{suffix}"

    content = await file.read()
    tmp_path.write_bytes(content)

    try:
        logger.info("Ingesting uploaded file: %s (%d bytes)", file.filename, len(content))
        processed = ingest_document(tmp_path)
        idx = index_document(processed)

        return {
            "doc_id": processed.doc_id,
            "file_name": file.filename,
            "file_type": processed.file_type,
            "page_count": processed.page_count,
            "chunk_count": len(processed.chunks),
            "total_chars": processed.total_chars,
            "avg_ocr_confidence": round(processed.avg_confidence, 3),
            "document_type": processed.metadata.get("document_type"),
            "parties_found": processed.metadata.get("parties", []),
            "dates_found": processed.metadata.get("dates", []),
            "status": "ready",
        }
    except Exception as exc:
        logger.error("Ingestion failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        tmp_path.unlink(missing_ok=True)


@router.get("/documents")
def list_documents():
    """List all processed documents."""
    docs = []
    for f in sorted(DOCUMENTS_DIR.glob("*.json")):
        try:
            with open(f) as fp:
                data = json.load(fp)
            docs.append({
                "doc_id": data["doc_id"],
                "document_type": data["metadata"].get("document_type"),
                "page_count": data["page_count"],
                "chunk_count": len(data["chunks"]),
                "avg_confidence": data["avg_confidence"],
            })
        except Exception:
            pass
    return {"documents": docs, "count": len(docs)}


@router.get("/documents/{doc_id}")
def get_document(doc_id: str):
    """Get full metadata and chunk list for a document."""
    try:
        doc = load_processed_document(doc_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    return {
        "doc_id": doc.doc_id,
        "metadata": doc.metadata,
        "page_count": doc.page_count,
        "chunk_count": len(doc.chunks),
        "avg_confidence": doc.avg_confidence,
        "chunks": [c.to_dict() for c in doc.chunks],
    }


@router.post("/draft")
def generate(req: DraftRequest):
    """
    Generate a grounded Case Fact Summary Memo.

    Retrieves top-k evidence chunks, injects active operator preferences,
    and generates a memo constrained to the retrieved evidence only.
    """
    # Load document metadata
    try:
        doc = load_processed_document(req.doc_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Document not found: {req.doc_id}")

    # Retrieve evidence
    try:
        chunks = retrieve(req.doc_id, req.query, top_k=req.top_k)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Index not found for {req.doc_id}. Was the document ingested?",
        )

    if not chunks:
        raise HTTPException(
            status_code=422,
            detail="No relevant evidence found — cannot generate grounded draft",
        )

    # Get operator preferences from learning loop
    preferences = get_active_preferences()

    # Generate draft
    try:
        draft = generate_draft(
            doc_id=req.doc_id,
            chunks=chunks,
            metadata=doc.metadata,
            operator_preferences=preferences,
        )
    except Exception as exc:
        err = str(exc)
        if "401" in err or "authentication" in err.lower() or "api_key" in err.lower():
            raise HTTPException(
                status_code=401,
                detail="LLM API authentication failed. Check your ANTHROPIC_API_KEY or OPENAI_API_KEY in .env",
            )
        raise HTTPException(status_code=500, detail=f"Draft generation failed: {err}")

    return {
        "draft_id": draft["draft_id"],
        "doc_id": draft["doc_id"],
        "draft_text": draft["draft_text"],
        "evidence_used": [
            {
                "chunk_id": c["chunk_id"],
                "source_page": c["source_page"],
                "confidence": c["confidence"],
                "relevance_score": c["relevance_score"],
                "text_preview": c["text"][:150] + "...",
            }
            for c in draft["evidence_used"]
        ],
        "operator_preferences_applied": draft["operator_preferences_applied"],
        "generated_at": draft["generated_at"],
    }


@router.get("/draft/{draft_id}")
def get_draft(draft_id: str):
    """Retrieve a previously generated draft by ID."""
    try:
        draft = load_draft(draft_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Draft not found: {draft_id}")
    return draft


@router.post("/edit")
def submit_edit(req: EditRequest):
    """
    Submit an operator's edited version of a draft.

    Triggers the learning loop:
    1. Saves the edited draft
    2. Analyzes the diff for reusable correction patterns
    3. Updates the correction memory
    4. Returns newly extracted patterns and updated preferences

    Future calls to POST /draft will automatically apply learned preferences.
    """
    try:
        draft = load_draft(req.draft_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Draft not found: {req.draft_id}")

    original_text = draft["draft_text"]
    if not original_text:
        raise HTTPException(status_code=422, detail="Original draft text is empty")

    # Save edited draft to disk
    save_edited_draft(req.draft_id, req.edited_text)

    # Process edit and extract patterns (gracefully degrades to heuristics if API fails)
    try:
        result = process_edit(
            draft_id=req.draft_id,
            doc_id=draft["doc_id"],
            original_text=original_text,
            edited_text=req.edited_text,
        )
    except Exception as exc:
        logger.error("Pattern extraction failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Edit processing failed: {exc}")

    return {
        "status": "edit_processed",
        "draft_id": req.draft_id,
        "new_patterns_extracted": result["new_patterns_extracted"],
        "total_patterns_in_memory": result["total_patterns_in_memory"],
        "active_preferences": result["active_preferences"],
        "new_patterns": result["new_patterns"],
        "message": (
            f"Extracted {result['new_patterns_extracted']} new patterns. "
            f"Future drafts will apply {len(result['active_preferences'])} active preferences."
        ),
    }


@router.get("/memory")
def get_memory():
    """
    Inspect the full correction memory.
    Shows all learned patterns and active preferences injected into future prompts.
    """
    memory = get_full_memory()
    return {
        "total_patterns": len(memory.get("patterns", [])),
        "active_preferences": memory.get("active_preferences", []),
        "all_patterns": memory.get("patterns", []),
    }
