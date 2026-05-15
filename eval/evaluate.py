"""
Evaluation script for the Legal Draft Assistant MVP.

Metrics:
1. Retrieval Precision  — are retrieved chunks genuinely relevant to the query?
2. Grounding Score      — does the draft cite evidence for each key claim?
3. Hallucination Rate   — are there claims not supported by any chunk?
4. Edit Improvement     — do drafts after operator edits improve?

Run: python eval/evaluate.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── 1. Retrieval Precision ─────────────────────────────────────────────────────

def evaluate_retrieval_precision(chunks: list[dict], query: str) -> dict:
    """
    Manual relevance scoring for retrieved chunks.
    Uses keyword overlap as a proxy for relevance.
    """
    query_terms = set(re.findall(r"\b\w{4,}\b", query.lower()))
    scores = []

    for chunk in chunks:
        text = chunk.get("text", "").lower()
        chunk_terms = set(re.findall(r"\b\w{4,}\b", text))
        if not query_terms:
            scores.append(0.0)
            continue
        overlap = len(query_terms & chunk_terms) / len(query_terms)
        # Weight by OCR confidence
        confidence = chunk.get("confidence", 1.0)
        weighted = overlap * confidence
        scores.append(weighted)

    avg_precision = sum(scores) / len(scores) if scores else 0.0
    return {
        "query": query,
        "chunk_count": len(chunks),
        "chunk_scores": [round(s, 3) for s in scores],
        "avg_precision": round(avg_precision, 3),
        "relevant_at_5": sum(1 for s in scores[:5] if s > 0.1),
    }


# ── 2. Grounding Score ────────────────────────────────────────────────────────

def evaluate_grounding(draft_text: str, evidence_chunk_ids: list[str]) -> dict:
    """
    Check what fraction of factual sentences in the draft cite a chunk ID.
    """
    # Find all citation patterns like [doc_chunk_0001]
    cited_ids = re.findall(r"\[([a-z0-9_]+_chunk_\d+)\]", draft_text)
    cited_set = set(cited_ids)
    evidence_set = set(evidence_chunk_ids)

    # Sentences with citations
    sentences = [s.strip() for s in re.split(r"[.!?\n]", draft_text) if s.strip()]
    sentences_with_citations = [s for s in sentences if re.search(r"\[.*?chunk_\d+\]", s)]
    sentences_with_uncertainty = [s for s in sentences if "[UNCERTAIN" in s or "[NOT FOUND" in s]

    grounding_rate = len(sentences_with_citations) / len(sentences) if sentences else 0.0
    valid_citations = len(cited_set & evidence_set)
    invalid_citations = len(cited_set - evidence_set)

    return {
        "total_sentences": len(sentences),
        "sentences_with_citations": len(sentences_with_citations),
        "sentences_with_uncertainty_flags": len(sentences_with_uncertainty),
        "grounding_rate": round(grounding_rate, 3),
        "unique_chunk_ids_cited": len(cited_set),
        "valid_citations": valid_citations,
        "invalid_citations": invalid_citations,
        "citation_accuracy": round(
            valid_citations / len(cited_set) if cited_set else 1.0, 3
        ),
    }


# ── 3. Hallucination Proxy ────────────────────────────────────────────────────

def estimate_hallucination_rate(draft_text: str, evidence_texts: list[str]) -> dict:
    """
    Proxy for hallucination: check if key noun phrases in the draft
    appear in the evidence. High miss rate → likely hallucination.
    """
    combined_evidence = " ".join(evidence_texts).lower()

    # Extract named entities and key terms from draft (simple regex approach)
    draft_entities = re.findall(
        r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b",  # proper nouns
        draft_text
    )
    draft_entities = list(set(draft_entities))

    supported = []
    unsupported = []
    for entity in draft_entities:
        if entity.lower() in combined_evidence:
            supported.append(entity)
        else:
            unsupported.append(entity)

    hallucination_rate = len(unsupported) / len(draft_entities) if draft_entities else 0.0

    return {
        "entities_checked": len(draft_entities),
        "supported_entities": len(supported),
        "unsupported_entities": len(unsupported),
        "estimated_hallucination_rate": round(hallucination_rate, 3),
        "unsupported_list": unsupported[:10],  # show first 10 for review
    }


# ── 4. Edit Improvement Score ─────────────────────────────────────────────────

def evaluate_edit_improvement(
    draft_before: str,
    draft_after: str,
    patterns_learned: list[dict],
) -> dict:
    """
    Check whether patterns learned from edits are reflected in subsequent drafts.
    """
    results = []
    for pattern in patterns_learned:
        pattern_text = pattern.get("pattern", "").lower()
        # Extract key terms from pattern instruction
        key_terms = re.findall(r"\b\w{5,}\b", pattern_text)

        # Check if these terms appear more in after vs before draft
        before_matches = sum(1 for t in key_terms if t in draft_before.lower())
        after_matches = sum(1 for t in key_terms if t in draft_after.lower())

        improved = after_matches >= before_matches
        results.append({
            "pattern": pattern.get("pattern"),
            "before_signal": before_matches,
            "after_signal": after_matches,
            "improved": improved,
        })

    improvement_rate = (
        sum(1 for r in results if r["improved"]) / len(results)
        if results else 1.0
    )

    return {
        "patterns_checked": len(results),
        "patterns_improved": sum(1 for r in results if r["improved"]),
        "improvement_rate": round(improvement_rate, 3),
        "details": results,
    }


# ── Main eval runner ──────────────────────────────────────────────────────────

def run_evaluation(doc_id: str):
    """Run the full evaluation suite for a given document."""
    from app.ingestion.pipeline import load_processed_document
    from app.retrieval.retriever import retrieve
    from app.learning.correction_memory import get_full_memory

    print(f"\n{'='*60}")
    print(f"EVALUATION REPORT — {doc_id}")
    print(f"{'='*60}\n")

    # Load document
    try:
        doc = load_processed_document(doc_id)
        print(f"Document type: {doc.metadata['document_type']}")
        print(f"Pages: {doc.page_count} | Chunks: {len(doc.chunks)} | Avg confidence: {doc.avg_confidence:.2f}")
    except FileNotFoundError:
        print(f"Document {doc_id} not found. Run ingestion first.")
        return

    # ── Test retrieval precision ──────────────────────────────────────────────
    print("\n── 1. RETRIEVAL PRECISION ──")
    query = "Generate a comprehensive case fact summary memo"
    chunks = retrieve(doc_id, query)
    retrieval_metrics = evaluate_retrieval_precision(
        [c.to_dict() for c in chunks], query
    )
    print(f"Chunks retrieved: {retrieval_metrics['chunk_count']}")
    print(f"Avg precision score: {retrieval_metrics['avg_precision']}")
    print(f"Relevant at top-5: {retrieval_metrics['relevant_at_5']}")

    # ── Check for saved drafts ────────────────────────────────────────────────
    print("\n── 2. GROUNDING SCORE ──")
    drafts_dir = Path(__file__).parent.parent / "data" / "drafts"
    doc_drafts = list(drafts_dir.glob(f"draft_{doc_id}_*.json"))

    if doc_drafts:
        latest_draft_path = sorted(doc_drafts)[-1]
        with open(latest_draft_path) as f:
            draft = json.load(f)

        evidence_ids = [c["chunk_id"] for c in draft.get("evidence_used", [])]
        grounding = evaluate_grounding(draft["draft_text"], evidence_ids)
        print(f"Total sentences: {grounding['total_sentences']}")
        print(f"Sentences with citations: {grounding['sentences_with_citations']}")
        print(f"Grounding rate: {grounding['grounding_rate']:.1%}")
        print(f"Citation accuracy: {grounding['citation_accuracy']:.1%}")

        # ── Hallucination estimate ────────────────────────────────────────────
        print("\n── 3. HALLUCINATION ESTIMATE ──")
        evidence_texts = [c["text"] for c in draft.get("evidence_used", [])]
        hallucination = estimate_hallucination_rate(draft["draft_text"], evidence_texts)
        print(f"Entities checked: {hallucination['entities_checked']}")
        print(f"Supported: {hallucination['supported_entities']}")
        print(f"Estimated hallucination rate: {hallucination['estimated_hallucination_rate']:.1%}")
        if hallucination["unsupported_list"]:
            print(f"Potentially unsupported: {hallucination['unsupported_list'][:5]}")
    else:
        print(f"No drafts found for {doc_id}. Run POST /api/v1/draft first.")

    # ── Correction memory ─────────────────────────────────────────────────────
    print("\n── 4. CORRECTION MEMORY ──")
    memory = get_full_memory()
    print(f"Total patterns learned: {len(memory.get('patterns', []))}")
    print(f"Active preferences: {len(memory.get('active_preferences', []))}")
    for pref in memory.get("active_preferences", []):
        print(f"  → {pref}")

    print(f"\n{'='*60}")
    print("Evaluation complete.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    import sys
    doc_id = sys.argv[1] if len(sys.argv) > 1 else "lease_agreement"
    run_evaluation(doc_id)
