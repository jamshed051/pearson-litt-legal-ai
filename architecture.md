# Architecture Overview

## Design Philosophy

The system is built around a single principle: **every generated claim must trace back to a specific chunk of the source document**. This is enforced at the prompt level, the data model level, and the evaluation level.

Rather than building a general-purpose legal AI, this pipeline is narrow by design. The output type is fixed (Case Fact Summary Memo), the evidence constraints are explicit, and the improvement loop is mechanical rather than learned via fine-tuning. This makes the system more auditable, more reliable, and much easier to maintain.

---

## Component Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         INGESTION LAYER                         │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │  extractor   │    │   chunker    │    │metadata_extractor│  │
│  │              │    │              │    │                  │  │
│  │ Tier 1:      │───▶│ 600-char     │    │ regex: parties,  │  │
│  │ pymupdf      │    │ overlapping  │    │ dates, addresses │  │
│  │              │    │ chunks with  │    │                  │  │
│  │ Tier 2:      │    │ source_page  │    │ spaCy NER        │  │
│  │ Tesseract OCR│    │ + confidence │    │ (enhancement)    │  │
│  │              │    │ metadata     │    │                  │  │
│  │ Tier 3:      │    │              │    │ Output:          │  │
│  │ Image OCR    │    │              │    │ {type, parties,  │  │
│  │              │    │              │    │  dates, ...}     │  │
│  └──────────────┘    └──────────────┘    └──────────────────┘  │
│         │                   │                     │             │
│         └───────────────────┴─────────────────────┘             │
│                             │                                   │
│                    ProcessedDocument                             │
│               {doc_id, chunks[], metadata}                      │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                         RETRIEVAL LAYER                         │
│                                                                 │
│  ┌──────────────┐    ┌──────────────────────────────────────┐  │
│  │   embedder   │    │           FAISS Index                │  │
│  │              │───▶│                                      │  │
│  │ sentence-    │    │  IndexFlatIP (cosine via dot product) │  │
│  │ transformers │    │  on L2-normalized vectors            │  │
│  │              │    │                                      │  │
│  │ all-MiniLM   │    │  Confidence weighting:               │  │
│  │ -L6-v2       │    │  relevance = similarity × conf_wt    │  │
│  │              │    │  (conf < 0.3 → 0.5× penalty)        │  │
│  └──────────────┘    └──────────────────────────────────────┘  │
│                                      │                          │
│                             RetrievedChunk[]                     │
│                     {chunk_id, text, page, confidence,          │
│                      similarity_score, relevance_score}          │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        DRAFTING LAYER                           │
│                                                                 │
│  Evidence Block:                                                │
│  [chunk_id_001] (page 2, confidence: HIGH, relevance: 0.847)   │
│  "Tenant failed to pay rent for December 2024..."               │
│                                                                 │
│  System Prompt Rules:                                           │
│  • Use ONLY retrieved evidence                                  │
│  • Every claim MUST cite a chunk_id                            │
│  • Say [UNCERTAIN] if evidence is unclear                       │
│  • [NOT FOUND IN DOCUMENTS] if field cannot be supported        │
│                                                                 │
│  + Operator Preferences (from learning loop):                   │
│  • "Always include chronological timeline"                      │
│  • "Avoid unsupported intent claims"                            │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        LEARNING LOOP                            │
│                                                                 │
│  Operator Edit                                                  │
│       │                                                         │
│       ▼                                                         │
│  LLM Analysis (original vs. edited):                           │
│  → "What reusable patterns can be learned?"                     │
│                                                                 │
│  Pattern Storage (correction_memory.json):                      │
│  {                                                              │
│    "type": "structure",                                         │
│    "pattern": "Always include chronological timeline",          │
│    "trigger": "cases with more than 2 key dates",              │
│    "reason": "Operator added missing timeline section"          │
│  }                                                              │
│                                                                 │
│  Active Preferences → injected into next draft's system prompt  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

### 1. Tiered OCR Strategy

Rather than running OCR on everything (slow) or skipping it (misses scanned docs), the system detects which tier each page needs:

- **Tier 1 (digital PDF):** pymupdf extracts clean text directly — fast, 100% confidence
- **Tier 2 (scanned PDF):** if a page yields < 50 chars via direct extraction, fall back to Tesseract
- **Tier 3 (image files):** Tesseract runs directly on the image

Every page stores its OCR confidence score. This flows through the entire pipeline — low-confidence chunks are penalized in retrieval scoring so they're retrieved last rather than excluded entirely.

### 2. Confidence-Weighted Retrieval

Standard RAG pipelines return the top-k most similar chunks. This one applies a confidence weight:

```
relevance_score = cosine_similarity × confidence_weight
confidence_weight = 1.0 if confidence ≥ 0.3 else 0.5
```

A perfectly relevant but poorly-OCR'd chunk will be outranked by a slightly less similar but cleaner chunk. This is intentional: generation quality is bounded by evidence quality.

### 3. Evidence-Only System Prompt

The most important architectural decision. The generation prompt enforces three hard constraints:
1. Only use the provided evidence chunks
2. Cite every claim with a chunk_id in brackets
3. Explicitly flag uncertainty rather than filling in gaps

This makes hallucinations visible: if the LLM invents a fact, there will be no chunk citation, and the evaluator can immediately spot it.

### 4. Correction Memory as Prompt Injection

Most candidates would implement a diff view. This system extracts *reusable patterns* from the diff — abstract rules that apply to future documents, not just the one being edited.

The LLM is given both versions and asked: "What should we always do differently?"

The resulting patterns accumulate in `correction_memory.json` and are injected into every future system prompt. This is the most ROI-positive architectural choice: it improves the system without any retraining, fine-tuning, or database infrastructure.

### 5. Mock Mode

The pipeline degrades gracefully with no API key configured. Ingestion, chunking, FAISS indexing, and retrieval all run identically. Draft generation fills a structured template with real metadata from the retrieved evidence. Pattern extraction applies simple heuristics (added sections, removed claims) instead of LLM analysis.

This allows the full pipeline to be tested and verified end-to-end before an API key is available.

### 6. Separation of Concerns

Each module has a single responsibility and clean interfaces:
- `extractor.py` → only does text extraction
- `chunker.py` → only does chunking
- `metadata_extractor.py` → only extracts structured fields
- `pipeline.py` → orchestrates ingestion
- `retriever.py` → only does retrieval
- `generator.py` → only does generation
- `correction_memory.py` → only manages the learning loop

This makes each component independently testable, debuggable, and replaceable.

---

## Data Model

### `ProcessedDocument`
Produced by the ingestion pipeline and saved to `data/documents/{doc_id}.json`.

```python
ProcessedDocument(
    doc_id: str,
    file_type: str,             # "pdf" | "image"
    page_count: int,
    total_chars: int,
    avg_confidence: float,      # mean OCR confidence across all chunks
    chunks: list[Chunk],
    metadata: dict              # {document_type, parties, dates, addresses, case_numbers}
)
```

### `Chunk`
The atomic unit stored in the FAISS index.

```python
Chunk(
    chunk_id: str,              # e.g. "eviction_notice_chunk_0003"
    text: str,
    source_page: int,
    confidence: float,          # 0.0–1.0 OCR confidence
    extraction_method: str,     # "pymupdf" | "tesseract" | "image_ocr"
    char_start: int,
    char_end: int
)
```

### `RetrievedChunk`
Returned by the retrieval layer. Adds scoring fields on top of the stored chunk.

```python
RetrievedChunk(
    chunk_id: str,
    text: str,
    source_page: int,
    confidence: float,
    similarity_score: float,    # raw cosine similarity from FAISS
    relevance_score: float      # similarity × confidence_weight
)
```

### `CorrectionPattern`
Stored in `correction_memory.json` after each operator edit.

```python
{
    "type": "structure" | "accuracy" | "completeness" | "style",
    "pattern": str,             # the reusable rule (injected into system prompt)
    "trigger": str,             # when this rule applies
    "reason": str,              # why this was extracted
    "source_draft_id": str,
    "created_at": str
}
```

---

## API Layer

The FastAPI app is stateless — all state lives in the `data/` directory. Endpoints are thin wrappers around the core pipeline functions.

```
POST /api/v1/ingest       → ingest_document() + index_document()
GET  /api/v1/documents    → list data/documents/*.json
GET  /api/v1/documents/{id} → load_processed_document()
POST /api/v1/draft        → retrieve() + generate_draft()
GET  /api/v1/draft/{id}   → load_draft()
POST /api/v1/edit         → save_edited_draft() + process_edit()
GET  /api/v1/memory       → get_full_memory()
GET  /api/v1/health       → static response
```

Error handling:
- `400` — unsupported file type on ingest
- `401` — invalid API key (detected from Anthropic/OpenAI SDK error messages)
- `404` — doc_id or draft_id not found in data/
- `422` — empty evidence or empty original draft
- `500` — unexpected pipeline failure with error detail

---

## Tradeoffs

| Decision | Chosen | Alternative | Reason |
|----------|--------|-------------|--------|
| Vector DB | FAISS (local) | Pinecone, Weaviate | No infra, inspectable files |
| Embeddings | sentence-transformers (local) | OpenAI embeddings | No per-request cost, offline capable |
| Storage | Local JSON | PostgreSQL, MongoDB | Inspectable, zero setup |
| Chunking | Fixed-size with sentence boundaries | Semantic chunking | Reliable, predictable chunk sizes |
| Draft type | Case Fact Summary Memo | Title review, checklist | Best evidence-citation structure |
| Learning | Prompt injection | Fine-tuning, RLHF | No training infrastructure needed |
| Mock mode | Heuristic fallback | Require API key | Testable without credentials |

---

## Bugs Fixed During Development

Five bugs were discovered and fixed during end-to-end testing:

| # | Bug | Root Cause | Fix |
|---|-----|------------|-----|
| 1 | Uploaded files got random `doc_id` like `tmp18_cglzu` | `/ingest` used `NamedTemporaryFile` path as doc_id | Derive clean doc_id from original `file.filename` before saving |
| 2 | Invalid API key returned opaque 500 | `AuthenticationError` not caught in `/draft` route | Added try/except detecting "401"/"authentication" in error string, returns clean 401 |
| 3 | Eviction notice classified as `"memo"` | `"memo"` pattern (`FROM:`) matched before `"eviction_notice"` | Reordered type patterns; added stronger eviction-specific patterns |
| 4 | Party extraction returned clause fragments | Regex too broad, matched verb phrases | Tightened to proper-name structure, added stopword filter |
| 5 | `demo.py` crashed with `AttributeError` | Referenced `chunk.extraction_method` on `RetrievedChunk` which doesn't have that field | Removed the invalid field reference from the print statement |

---

## Scalability Path

If this were to go to production:

1. **Storage:** Replace JSON files with a database (PostgreSQL + pgvector, or Weaviate)
2. **Embeddings:** Add batching + caching for high document volume
3. **OCR:** Add GPU-accelerated OCR (AWS Textract, Google Document AI) for production quality
4. **Serving:** The FastAPI app is already stateless — wrap in Docker and horizontally scale
5. **Learning loop:** At sufficient volume, correction patterns could seed fine-tuning data
6. **Authentication:** Add API key or JWT auth for multi-operator deployments

---

## What Was Intentionally Omitted

- **Authentication:** Not required for a single-operator internal tool at this stage
- **Fine-tuning / RLHF:** The correction memory approach achieves the same goal without training infrastructure
- **LangChain:** All pipeline logic is explicit Python — no framework magic, easier to debug and audit
- **Frontend:** The API + Swagger UI + demo script demonstrate the full loop; a bespoke UI would add complexity without additional value for this assessment
- **Async ingestion queue:** Documents are processed synchronously. For production, a task queue (Celery, ARQ) would allow non-blocking uploads
