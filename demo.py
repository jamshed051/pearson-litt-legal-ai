"""
End-to-end demo script: runs the full pipeline on sample documents.

What this demonstrates:
1. Document ingestion (extraction + chunking + metadata + indexing)
2. Grounded retrieval (top-5 evidence chunks with scores)
3. Draft generation (Case Fact Summary Memo)
4. Operator edit simulation
5. Learning loop (pattern extraction + correction memory)
6. Improved draft generation (preferences applied)

Run: python demo.py
"""

import json
import sys
from pathlib import Path

# Add parent to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent))

from app.ingestion.pipeline import ingest_document
from app.retrieval.retriever import index_document, retrieve
from app.drafting.generator import generate_draft, save_edited_draft
from app.learning.correction_memory import process_edit, get_active_preferences


def separator(title: str):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def run_demo():
    sample_dir = Path("sample_docs")

    # ── Step 0: Check for sample documents ────────────────────────────────────
    separator("STEP 0: Generate Sample Documents")
    lease_path = sample_dir / "lease_agreement.pdf"
    notice_path = sample_dir / "eviction_notice.pdf"

    if not lease_path.exists() or not notice_path.exists():
        print("Sample documents not found. Generating...")
        from sample_docs.generate_samples import (
            create_lease_agreement,
            create_eviction_notice,
            create_property_inspection_note,
        )
        create_lease_agreement()
        create_eviction_notice()
        create_property_inspection_note()
    else:
        print(f"Found: {lease_path}")
        print(f"Found: {notice_path}")

    # ── Step 1: Ingest documents ───────────────────────────────────────────────
    separator("STEP 1: Document Ingestion")

    print(f"\nIngesting: {lease_path.name}")
    lease_doc = ingest_document(lease_path)
    print(f"  → doc_id:         {lease_doc.doc_id}")
    print(f"  → pages:          {lease_doc.page_count}")
    print(f"  → chunks:         {len(lease_doc.chunks)}")
    print(f"  → avg confidence: {lease_doc.avg_confidence:.2f}")
    print(f"  → doc type:       {lease_doc.metadata['document_type']}")
    print(f"  → parties:        {lease_doc.metadata['parties'][:3]}")
    print(f"  → dates:          {lease_doc.metadata['dates'][:3]}")

    print(f"\nIngesting: {notice_path.name}")
    notice_doc = ingest_document(notice_path)
    print(f"  → doc_id:         {notice_doc.doc_id}")
    print(f"  → chunks:         {len(notice_doc.chunks)}")
    print(f"  → avg confidence: {notice_doc.avg_confidence:.2f}")
    print(f"  → doc type:       {notice_doc.metadata['document_type']}")
    print(f"  → dates:          {notice_doc.metadata['dates'][:5]}")

    # ── Step 2: Build indexes ──────────────────────────────────────────────────
    separator("STEP 2: Build FAISS Indexes")

    print("\nBuilding index for lease_agreement...")
    index_document(lease_doc)
    print("  → Done")

    print("Building index for eviction_notice...")
    index_document(notice_doc)
    print("  → Done")

    # ── Step 3: Retrieval ──────────────────────────────────────────────────────
    separator("STEP 3: Grounded Retrieval")

    query = "Generate a comprehensive case fact summary memo for this case"
    print(f"\nQuery: '{query}'")

    print(f"\nTop 5 chunks from eviction_notice:")
    chunks = retrieve(notice_doc.doc_id, query, top_k=5)
    for i, chunk in enumerate(chunks, 1):
        print(f"\n  [{i}] {chunk.chunk_id}")
        print(f"       page={chunk.source_page} | "
              f"confidence={chunk.confidence:.2f} | relevance={chunk.relevance_score:.3f}")
        print(f"       Text: {chunk.text[:120]}...")

    # ── Step 4: Generate draft (no preferences yet) ───────────────────────────
    separator("STEP 4: Draft Generation (Round 1 — No Learned Preferences)")

    draft = generate_draft(
        doc_id=notice_doc.doc_id,
        chunks=chunks,
        metadata=notice_doc.metadata,
        operator_preferences=[],  # no preferences yet
    )
    print(f"\nDraft ID: {draft['draft_id']}")
    print(f"Evidence chunks used: {len(draft['evidence_used'])}")
    print(f"\n{'─' * 40}")
    print(draft["draft_text"])
    print(f"{'─' * 40}")

    # ── Step 5: Simulate operator edit ────────────────────────────────────────
    separator("STEP 5: Operator Edit Simulation")

    simulated_edit = draft["draft_text"] + """

CHRONOLOGICAL TIMELINE
[Added by operator — this section was missing from the AI draft]

- January 15, 2023:  Lease agreement signed [eviction_notice_chunk_0000]
- February 1, 2023:  Lease term commenced [eviction_notice_chunk_0000]
- December 1, 2024:  First missed rent payment ($3,200.00) [eviction_notice_chunk_0001]
- January 1, 2025:   Second missed rent payment ($3,200.00) [eviction_notice_chunk_0001]
- February 1, 2025:  Third missed rent payment ($3,200.00) [eviction_notice_chunk_0001]
- February 15, 2025: Property inspection — damage found [eviction_notice_chunk_0002]
- March 8, 2025:     Notice to Pay or Quit served via certified mail [eviction_notice_chunk_0003]

NOTE [operator]: Removed claim "Tenant intentionally damaged property" — this is unsupported
by evidence. The inspection note documents damage but does not establish intent.
"""

    print("\nOperator made two key edits:")
    print("  1. Added explicit chronological timeline section")
    print("  2. Removed unsupported intent claim")
    print("\nSubmitting edit to learning loop...")

    save_edited_draft(draft["draft_id"], simulated_edit)

    # ── Step 6: Learning loop ──────────────────────────────────────────────────
    separator("STEP 6: Learning Loop — Pattern Extraction")

    result = process_edit(
        draft_id=draft["draft_id"],
        doc_id=notice_doc.doc_id,
        original_text=draft["draft_text"],
        edited_text=simulated_edit,
    )

    print(f"\nPatterns extracted: {result['new_patterns_extracted']}")
    for pattern in result["new_patterns"]:
        print(f"\n  Type: {pattern['type']}")
        print(f"  Pattern: {pattern['pattern']}")
        print(f"  Trigger: {pattern['trigger']}")
        print(f"  Reason:  {pattern['reason']}")

    print(f"\nActive preferences after learning:")
    for pref in result["active_preferences"]:
        print(f"  → {pref}")

    # ── Step 7: Improved draft ────────────────────────────────────────────────
    separator("STEP 7: Improved Draft Generation (Round 2 — With Learned Preferences)")

    preferences = get_active_preferences()
    print(f"\nApplying {len(preferences)} learned preferences...")

    improved_draft = generate_draft(
        doc_id=notice_doc.doc_id,
        chunks=chunks,
        metadata=notice_doc.metadata,
        operator_preferences=preferences,
    )

    print(f"\nImproved Draft ID: {improved_draft['draft_id']}")
    print(f"Preferences applied: {len(improved_draft['operator_preferences_applied'])}")
    print(f"\n{'─' * 40}")
    print(improved_draft["draft_text"])
    print(f"{'─' * 40}")

    # ── Step 8: Save outputs ───────────────────────────────────────────────────
    separator("STEP 8: Saving Sample Outputs")

    outputs_dir = Path("outputs")
    outputs_dir.mkdir(exist_ok=True)

    # Save initial draft
    with open(outputs_dir / "sample_draft_v1.json", "w") as f:
        json.dump(draft, f, indent=2)
    print(f"Saved: outputs/sample_draft_v1.json")

    # Save improved draft
    with open(outputs_dir / "sample_draft_v2_improved.json", "w") as f:
        json.dump(improved_draft, f, indent=2)
    print(f"Saved: outputs/sample_draft_v2_improved.json")

    # Save correction memory snapshot
    from app.learning.correction_memory import get_full_memory
    with open(outputs_dir / "correction_memory_snapshot.json", "w") as f:
        json.dump(get_full_memory(), f, indent=2)
    print(f"Saved: outputs/correction_memory_snapshot.json")

    separator("DEMO COMPLETE")
    print("\nFull pipeline demonstrated:")
    print("  ✓ Document ingestion (extraction + OCR + chunking + metadata)")
    print("  ✓ FAISS vector indexing with confidence weighting")
    print("  ✓ Grounded retrieval with evidence inspection")
    print("  ✓ Case Fact Summary Memo generation")
    print("  ✓ Operator edit capture")
    print("  ✓ Correction pattern extraction")
    print("  ✓ Improved draft with learned preferences")
    print("\nTo run the API server:")
    print("  uvicorn main:app --reload --port 8000")
    print("  Then visit: http://localhost:8000/docs")
    print()


if __name__ == "__main__":
    run_demo()
