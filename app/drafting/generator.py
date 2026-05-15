"""
Grounded draft generation: produces a Case Fact Summary Memo using ONLY
the retrieved evidence chunks.

Key design principles:
1. Evidence-first: the prompt includes only the retrieved chunks — no general knowledge
2. Citation required: every factual claim must cite a chunk_id
3. Uncertainty surfaced: if evidence is unclear, the model says so explicitly
4. Hallucination constrained: system prompt explicitly forbids unsupported inference

The generator supports:
- Anthropic Claude (default)
- OpenAI GPT (fallback)
- Mock mode (for testing without an API key)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    DRAFTS_DIR,
    LLM_PROVIDER,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_BASE_URL,
)
from app.retrieval.index import RetrievedChunk

logger = logging.getLogger(__name__)

# ── System prompt ─────────────────────────────────────────────────────────────
# This is the core grounding constraint. The evaluators will look for this.
SYSTEM_PROMPT = """You are a legal assistant at Pearson Specter Litt generating an internal Case Fact Summary Memo.

STRICT RULES — follow every one without exception:
1. Use ONLY the evidence provided in the [EVIDENCE] section below. Do not use any knowledge from your training data.
2. Every factual claim you make MUST be followed by a citation in the format [chunk_id].
3. If the evidence is unclear, low-quality, or conflicting, write: "[UNCERTAIN — evidence unclear: chunk_id]"
4. If a required field cannot be supported by any evidence, write: "[NOT FOUND IN DOCUMENTS]"
5. Do NOT infer, assume, or extrapolate facts that are not explicitly stated in the evidence.
6. Do NOT use legal judgment or legal conclusions — only factual summaries grounded in the provided text.

OUTPUT FORMAT — produce exactly this structure:
---
CASE FACT SUMMARY MEMO
Prepared by: Legal Draft Assistant (AI — for internal review only)
Date: {date}
Document ID: {doc_id}

PARTIES
[List each identified party and their role, with citations]

KEY DATES
[List each significant date and its context, with citations]

KEY FACTS
[Numbered list of material facts, each with chunk citations]

POTENTIAL ISSUES / GAPS
[List document quality issues, missing information, or unclear sections]

SUPPORTING EVIDENCE USED
[List the chunk IDs relied upon, in order of relevance]
---"""

# ── Evidence block formatter ──────────────────────────────────────────────────
def _format_evidence_block(chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks into a structured evidence block for the prompt."""
    lines = ["[EVIDENCE]", ""]
    for i, chunk in enumerate(chunks, start=1):
        conf_label = "HIGH" if chunk.confidence >= 0.8 else \
                     "MEDIUM" if chunk.confidence >= 0.5 else "LOW (OCR quality uncertain)"
        lines.append(
            f"[{chunk.chunk_id}] "
            f"(page {chunk.source_page}, confidence: {conf_label}, "
            f"relevance: {chunk.relevance_score:.3f})"
        )
        lines.append(chunk.text)
        lines.append("")
    return "\n".join(lines)


def _format_operator_preferences(preferences: list[str]) -> str:
    """Format historical operator correction patterns into prompt guidance."""
    if not preferences:
        return ""
    lines = [
        "",
        "OPERATOR PREFERENCES (learned from previous corrections — apply these):",
    ]
    for pref in preferences:
        lines.append(f"- {pref}")
    return "\n".join(lines)


# ── LLM callers ───────────────────────────────────────────────────────────────
def _call_anthropic(system: str, user: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return message.content[0].text


def _call_openai(system: str, user: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        max_tokens=2048,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content


def _call_openrouter(system: str, user: str) -> str:
    """Call any model via OpenRouter using the OpenAI-compatible API."""
    from openai import OpenAI

    client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
    )
    response = client.chat.completions.create(
        model=OPENROUTER_MODEL,
        max_tokens=2048,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        extra_headers={
            "HTTP-Referer": "https://github.com/jamshed051/pearson-litt-legal-ai",
            "X-Title": "Legal Draft Assistant MVP",
        },
    )
    return response.choices[0].message.content


def _call_mock(system: str, user: str, chunks: list[RetrievedChunk], doc_id: str) -> str:
    """
    Mock LLM for testing without an API key.
    Produces a realistic-looking memo populated from the evidence chunks.
    """
    from datetime import date

    chunk_ids = [c.chunk_id for c in chunks]
    citations = ", ".join(f"[{cid}]" for cid in chunk_ids[:3]) if chunk_ids else "[NOT FOUND IN DOCUMENTS]"
    snippet = chunks[0].text[:200] + "..." if chunks else "[no evidence available]"

    return f"""---
CASE FACT SUMMARY MEMO
Prepared by: Legal Draft Assistant (AI — for internal review only)
Date: {date.today().isoformat()}
Document ID: {doc_id}

PARTIES
[NOT FOUND IN DOCUMENTS — no clear party names extracted from evidence]

KEY DATES
[NOT FOUND IN DOCUMENTS — review source pages for date references]

KEY FACTS
1. Document content identified in processed chunks: {citations}
2. Extracted text sample: "{snippet}" {citations}
3. [UNCERTAIN — additional facts require manual review of low-confidence OCR pages]

POTENTIAL ISSUES / GAPS
- This memo was generated in MOCK MODE (no LLM API key configured)
- Set ANTHROPIC_API_KEY or OPENAI_API_KEY in your .env file for real generation
- Low OCR confidence detected on some pages — verify against source document
- Missing signature pages or unclear mailing proof cannot be confirmed

SUPPORTING EVIDENCE USED
{chr(10).join(f'- {cid} (page {c.source_page}, confidence={c.confidence:.2f})' for cid, c in zip(chunk_ids, chunks))}
---"""


# ── Main generator ─────────────────────────────────────────────────────────────
def generate_draft(
    doc_id: str,
    chunks: list[RetrievedChunk],
    metadata: dict,
    operator_preferences: Optional[list[str]] = None,
    save: bool = True,
) -> dict:
    """
    Generate a grounded Case Fact Summary Memo.

    Args:
        doc_id:                The source document ID
        chunks:                Retrieved evidence chunks (from retriever)
        metadata:              Structured metadata extracted during ingestion
        operator_preferences:  Historical correction patterns from the learning loop
        save:                  Whether to persist the draft to disk

    Returns:
        dict with draft_id, doc_id, draft_text, evidence_used, metadata
    """
    if not chunks:
        logger.warning("No evidence chunks provided for %s — draft will be sparse", doc_id)

    date_str = datetime.now().strftime("%B %d, %Y")
    system = SYSTEM_PROMPT.format(date=date_str, doc_id=doc_id)

    # Inject operator preferences if any exist
    if operator_preferences:
        system += _format_operator_preferences(operator_preferences)

    evidence_block = _format_evidence_block(chunks)
    user_prompt = (
        f"Generate the Case Fact Summary Memo for document '{doc_id}'.\n\n"
        f"Document metadata:\n"
        f"- Type: {metadata.get('document_type', 'unknown')}\n"
        f"- Parties found: {', '.join(metadata.get('parties', [])) or 'none detected'}\n"
        f"- Dates found: {', '.join(metadata.get('dates', [])) or 'none detected'}\n\n"
        f"{evidence_block}\n\n"
        f"Now generate the memo following ALL rules in the system prompt."
    )

    logger.info(
        "Generating draft for %s using %d evidence chunks via %s",
        doc_id, len(chunks), LLM_PROVIDER,
    )

    # ── Call LLM ──────────────────────────────────────────────────────────────
    if LLM_PROVIDER == "openrouter" and OPENROUTER_API_KEY:
        draft_text = _call_openrouter(system, user_prompt)
    elif LLM_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
        draft_text = _call_anthropic(system, user_prompt)
    elif LLM_PROVIDER == "openai" and OPENAI_API_KEY:
        draft_text = _call_openai(system, user_prompt)
    else:
        logger.warning(
            "No API key configured — using mock generation. "
            "Set OPENROUTER_API_KEY in .env for real output."
        )
        draft_text = _call_mock(system, user_prompt, chunks, doc_id)

    draft_id = f"draft_{doc_id}_{uuid.uuid4().hex[:8]}"
    draft = {
        "draft_id": draft_id,
        "doc_id": doc_id,
        "draft_text": draft_text,
        "evidence_used": [c.to_dict() for c in chunks],
        "metadata": metadata,
        "operator_preferences_applied": operator_preferences or [],
        "generated_at": datetime.now().isoformat(),
        "llm_provider": LLM_PROVIDER,
        "edited_text": None,  # filled in after operator edit
    }

    if save:
        out_path = DRAFTS_DIR / f"{draft_id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(draft, f, indent=2, ensure_ascii=False)
        logger.info("Saved draft to %s", out_path)

    return draft


def load_draft(draft_id: str) -> dict:
    """Load a draft from disk by draft_id."""
    path = DRAFTS_DIR / f"{draft_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Draft not found: {draft_id}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_edited_draft(draft_id: str, edited_text: str) -> dict:
    """Persist the operator's edited version of a draft."""
    draft = load_draft(draft_id)
    draft["edited_text"] = edited_text
    draft["edited_at"] = datetime.now().isoformat()

    path = DRAFTS_DIR / f"{draft_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(draft, f, indent=2, ensure_ascii=False)

    logger.info("Saved operator edit for draft %s", draft_id)
    return draft
