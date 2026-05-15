# CLAUDE.md — Legal Draft Assistant MVP
# Pearson Specter Litt — AI Engineer Take-Home Assessment

## Purpose of This File
This file preserves full project context across sessions. Read it at the start of every session before making any changes. It prevents context loss when the conversation window resets.

---

## Project Summary

A Python pipeline that:
1. Ingests legal PDFs/images with tiered OCR (pymupdf → Tesseract fallback)
2. Chunks and embeds documents into a FAISS vector index
3. Retrieves grounded evidence chunks (top-k with confidence weighting)
4. Generates Case Fact Summary Memos using evidence-only prompting
5. Captures operator edits to extract reusable correction patterns
6. Injects those patterns into future drafts via prompt injection

**Root folder:** `Pearson Litt App/`
**Entry points:** `demo.py` (terminal) · `main.py` (FastAPI server)
**API docs:** http://localhost:8000/docs when server is running

---

## Environment Setup

```bash
# Always activate venv before running anything
cd "Pearson Litt App"
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate         # Windows

# macOS note: use python3/pip3, not python/pip
python3 demo.py
uvicorn main:app --reload --port 8000
```

**API key:** Set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in `.env`.
If no key is set, the system runs in **mock mode** — ingestion, chunking, and FAISS retrieval work fully; generation and pattern extraction use heuristics.

---

## File Map

```
app/
  config.py                   # All settings via env vars; auto-creates data/ dirs on import
  ingestion/
    extractor.py              # extract_document(path) → list[RawPage]
    chunker.py                # chunk_document(doc) → list[Chunk], 600-char / 100-overlap
    metadata_extractor.py     # extract_metadata(text, doc_id) → {type, parties, dates, ...}
    pipeline.py               # ingest_document(path) → ProcessedDocument (orchestrator)
  retrieval/
    embedder.py               # Singleton SentenceTransformer, embed_texts() → np.ndarray
    index.py                  # DocumentIndex: FAISS IndexFlatIP, confidence-weighted search
    retriever.py              # index_document(doc) · retrieve(doc_id, query, top_k)
  drafting/
    generator.py              # generate_draft() → dict; save_edited_draft(); load_draft()
  learning/
    correction_memory.py      # process_edit() · get_active_preferences() · get_full_memory()
  api/
    routes.py                 # All FastAPI endpoints (see API section below)

main.py                       # FastAPI app, CORS middleware, mounts router at /api/v1
demo.py                       # 8-step end-to-end demo (no server needed)
eval/evaluate.py              # 4 metrics: retrieval precision, grounding rate, hallucination, memory
sample_docs/generate_samples.py  # Creates lease_agreement.pdf, eviction_notice.pdf, inspection_note.png

data/documents/               # ProcessedDocument JSON (gitignored, generated at runtime)
data/indexes/                 # FAISS index + chunk pickle per doc (gitignored)
data/drafts/                  # Generated + edited drafts (gitignored)
data/correction_memory.json   # Learned operator preferences (gitignored)
outputs/                      # Sample artifacts committed for reviewers
```

---

## Key Data Models

### `Chunk` (ingestion output, stored in FAISS)
```python
chunk_id: str          # e.g. "eviction_notice_chunk_0003"
text: str
source_page: int
confidence: float      # 0.0–1.0 OCR confidence
extraction_method: str # "pymupdf" | "tesseract" | "image_ocr"
char_start: int
char_end: int
```

### `RetrievedChunk` (retrieval output — NOT the same as Chunk)
```python
chunk_id: str
text: str
source_page: int
confidence: float
similarity_score: float   # raw cosine similarity
relevance_score: float    # similarity × confidence_weight
# NOTE: NO extraction_method field — this caused a bug (see Bugs section)
```

### `ProcessedDocument`
```python
doc_id: str
file_type: str
page_count: int
total_chars: int
avg_confidence: float
chunks: list[Chunk]
metadata: dict  # {document_type, parties, dates, addresses, case_numbers}
```

### `CorrectionPattern` (stored in correction_memory.json)
```python
{
  "type": "structure" | "accuracy" | "completeness" | "style",
  "pattern": str,       # injected into future system prompts
  "trigger": str,
  "reason": str,
  "source_draft_id": str,
  "created_at": str
}
```

---

## API Endpoints

| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| GET | `/api/v1/health` | `health_check()` | Static status check |
| POST | `/api/v1/ingest` | `ingest()` | Upload PDF/image → extract, chunk, index |
| GET | `/api/v1/documents` | `list_documents()` | List processed docs |
| GET | `/api/v1/documents/{doc_id}` | `get_document()` | Full metadata + chunks |
| POST | `/api/v1/draft` | `generate()` | Generate grounded memo |
| GET | `/api/v1/draft/{draft_id}` | `get_draft()` | Retrieve a draft |
| POST | `/api/v1/edit` | `submit_edit()` | Operator edit → learning loop |
| GET | `/api/v1/memory` | `get_memory()` | Inspect learned patterns |

**Error codes:** 400 (bad file type) · 401 (bad API key) · 404 (missing doc/draft) · 422 (empty evidence) · 500 (pipeline failure)

---

## Bugs Fixed (Do Not Reintroduce)

### Bug 1 — Temp filename as doc_id (`app/api/routes.py`)
**Symptom:** Uploaded files got doc_ids like `tmp18_cglzu` instead of `eviction_notice`.
**Root cause:** Used `tempfile.NamedTemporaryFile` path as doc_id.
**Fix:** Derive `clean_doc_id` from `file.filename` stem before saving:
```python
original_stem = Path(file.filename or "upload").stem
clean_doc_id = re.sub(r"[^a-zA-Z0-9_-]", "_", original_stem).strip("_") or "document"
tmp_path = Path(tempfile.gettempdir()) / f"{clean_doc_id}{suffix}"
```

### Bug 2 — Unhandled 401 crash (`app/api/routes.py`)
**Symptom:** Invalid API key caused opaque 500 instead of clean error.
**Fix:** Wrap `generate_draft()` in try/except, detect "401"/"authentication" in error string, return HTTP 401 with actionable message.

### Bug 3 — Eviction notice classified as "memo" (`app/ingestion/metadata_extractor.py`)
**Symptom:** `document_type` returned `"memo"` for eviction notices.
**Root cause:** `"memo"` pattern (`FROM:`) evaluated before `"eviction_notice"`.
**Fix:** `"eviction_notice"` must appear first in `DOCUMENT_TYPE_PATTERNS`; added stronger patterns (`"notice to pay rent"`, `"in default under the terms"`).

### Bug 4 — Party extraction returned clause fragments (`app/ingestion/metadata_extractor.py`)
**Symptom:** Phrases like `"Tenant agrees to pay"` appeared as party names.
**Fix:** Tightened regex to proper-name structure, added `_PARTY_STOPWORDS`, require `" " in clean` and `re.match(r"^[A-Z][a-zA-Z\.\s]+$", clean)`.

### Bug 5 — `AttributeError` in demo.py
**Symptom:** `AttributeError: 'RetrievedChunk' object has no attribute 'extraction_method'`
**Root cause:** `demo.py` printed `chunk.extraction_method` — valid on `Chunk` but not `RetrievedChunk`.
**Fix:** Removed `extraction_method` from the retrieval print block. Only print `source_page`, `confidence`, `relevance_score`.

---

## Architecture Decisions (Don't Change Without Good Reason)

- **OCR tiers:** Tier 1 = pymupdf direct; Tier 2 = Tesseract fallback if page < 50 chars; Tier 3 = image OCR
- **Confidence weighting:** `relevance = similarity × (1.0 if confidence ≥ 0.3 else 0.5)` — low-quality OCR penalised, not excluded
- **Evidence-only prompt:** Every claim must cite `[chunk_id]`. Say `[UNCERTAIN]` if unclear. `[NOT FOUND IN DOCUMENTS]` if missing. Never fabricate.
- **Correction memory:** Patterns stored as abstract reusable rules, injected into system prompt — NOT per-document overrides
- **Storage:** Local JSON files only — no database, no external services required
- **Mock mode:** Full pipeline minus LLM. Don't add hard requirements on API key presence.

---

## Testing Workflows

### Terminal (no server)
```bash
python3 sample_docs/generate_samples.py  # once only
python3 demo.py                          # 8-step end-to-end
python3 eval/evaluate.py eviction_notice # metrics
```

### Swagger UI
```bash
uvicorn main:app --reload --port 8000
# Open http://localhost:8000/docs
# POST /ingest → upload sample_docs/eviction_notice.pdf
# POST /draft  → {"doc_id": "eviction_notice", "top_k": 5}
# POST /edit   → {"draft_id": "...", "edited_text": "..."}
# GET  /memory → inspect learned patterns
```

### Mock mode (no API key)
```bash
cp .env.example .env   # leave keys blank
python3 demo.py        # runs fully, generation uses heuristics
```

---

## What Has Been Built and Verified

- [x] Full ingestion pipeline (extractor → chunker → metadata → pipeline)
- [x] FAISS retrieval with confidence weighting
- [x] Evidence-only draft generation (Anthropic / OpenAI / mock)
- [x] Correction memory learning loop
- [x] All 8 FastAPI endpoints
- [x] 14-point test suite (all passing)
- [x] End-to-end demo script
- [x] Evaluation script (4 metrics)
- [x] Sample doc generator
- [x] Mock mode (no API key required)
- [x] README with setup, testing, and bug documentation
- [x] architecture.md with data models, decisions, and tradeoffs
- [x] All 5 bugs fixed and documented

---

## Session Continuity Notes

When resuming work in a new session:
1. Read this file first
2. Check `git status` or file mtimes to see what changed since last session
3. Do NOT reintroduce the 5 fixed bugs listed above
4. The `data/` directory is gitignored — regenerate with `python3 demo.py` if needed
5. `outputs/` is committed and contains sample draft JSON for reference
6. The `venv/` folder is local — activate it before running any Python commands
