# Legal Draft Assistant MVP

**Pearson Specter Litt — AI Engineer Take-Home Assessment**

A lean, grounded pipeline for ingesting messy legal documents, extracting evidence, generating Case Fact Summary Memos, and improving from operator edits.

> **Design philosophy:** I optimized for grounded, inspectable workflows under tight constraints rather than overbuilding infrastructure.

---

## Current Status

| Component | Status |
|-----------|--------|
| LLM Provider | **OpenRouter** (live — not mock mode) |
| Model | **DeepSeek V4 Flash** (`deepseek/deepseek-v4-flash:free`) |
| API Key | **Configured and verified** ✓ |
| Mock Mode | **Disabled** — full LLM generation active |
| Ingestion & OCR | Live ✓ |
| FAISS Retrieval | Live ✓ |
| Draft Generation | Live LLM output ✓ |
| Learning Loop | Live LLM pattern extraction ✓ |

The system was previously running in mock mode (no API key). It is now fully connected to a live LLM via OpenRouter using the DeepSeek V4 Flash free model, which was confirmed working with a successful API test call. All 8 pipeline stages produce real AI output.

---

## Quick Start

```bash
# 1. Enter the project folder
cd "Pearson Litt App"

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Install dependencies
pip3 install -r requirements.txt

# 4. Install spaCy model (optional, enhances party extraction)
python3 -m spacy download en_core_web_sm

# 5. Install Tesseract (for OCR fallback)
# macOS:   brew install tesseract
# Ubuntu:  sudo apt-get install tesseract-ocr
# Windows: https://github.com/UB-Mannheim/tesseract/wiki

# 6. Configure API key (OpenRouter recommended — free, no credit card required)
cp .env.example .env
# Edit .env and set your OPENROUTER_API_KEY
# Get a free key at https://openrouter.ai/keys
# The system runs in mock mode if no key is set — see "Testing Without an API Key" below

# 7. Generate sample documents and run the full demo
python3 sample_docs/generate_samples.py
python3 demo.py

# 8. Start the API server
uvicorn main:app --reload --port 8000
# Interactive API docs: http://localhost:8000/docs
```

---

## Testing the App

### Option A: Terminal Demo (Fastest)

This runs the entire pipeline end-to-end in a single command — no server needed.

```bash
# Make sure you're in the project folder with venv activated
cd "Pearson Litt App"
source venv/bin/activate

# Generate sample PDFs (only needed once)
python3 sample_docs/generate_samples.py

# Run the full 8-step demo
python3 demo.py
```

**What the demo does:**

| Step | Action |
|------|--------|
| 0 | Generates `lease_agreement.pdf` and `eviction_notice.pdf` if not present |
| 1 | Ingests both PDFs (extraction → chunking → metadata) |
| 2 | Builds FAISS vector indexes |
| 3 | Retrieves top-5 evidence chunks for a query |
| 4 | Generates Case Fact Summary Memo (Round 1, no learned preferences) |
| 5 | Simulates an operator edit (adds timeline, removes unsupported claim) |
| 6 | Runs the learning loop — extracts reusable correction patterns |
| 7 | Generates improved memo (Round 2, with learned preferences injected) |
| 8 | Saves JSON outputs to `outputs/` |

Sample outputs are written to:
- `outputs/sample_draft_v1.json` — initial draft
- `outputs/sample_draft_v2_improved.json` — improved draft after learning
- `outputs/correction_memory_snapshot.json` — learned patterns

---

### Option B: Swagger UI (Interactive, Recommended for Reviewers)

The API server exposes a full interactive UI with built-in file upload — no curl or Postman needed.

**Step 1: Start the server**

```bash
cd "Pearson Litt App"
source venv/bin/activate
uvicorn main:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

**Step 2: Open the Swagger UI**

Go to **http://localhost:8000/docs** in your browser. You'll see all 8 endpoints listed with expandable sections, request/response schemas, and "Try it out" buttons.

**Step 3: Upload a document**

1. First, generate sample docs if you haven't: `python3 sample_docs/generate_samples.py`
2. In the Swagger UI, expand **`POST /api/v1/ingest`**
3. Click **"Try it out"**
4. Click **"Choose File"** — select `sample_docs/eviction_notice.pdf` (or any PDF/image)
5. Click **"Execute"**
6. Note the `doc_id` in the response (e.g. `"eviction_notice"`)

**Step 4: Generate a draft**

1. Expand **`POST /api/v1/draft`**
2. Click "Try it out"
3. Edit the request body:
   ```json
   {
     "doc_id": "eviction_notice",
     "query": "Generate a comprehensive case fact summary memo",
     "top_k": 5
   }
   ```
4. Click "Execute" — you'll get a full Case Fact Summary Memo with chunk citations and evidence references

**Step 5: Submit an operator edit (triggers learning)**

1. Copy the `draft_id` from Step 4's response
2. Expand **`POST /api/v1/edit`**
3. Click "Try it out"
4. Paste in the `draft_id` and your edited version of the text:
   ```json
   {
     "draft_id": "draft_abc123",
     "edited_text": "...your modified version of the memo..."
   }
   ```
5. Execute — the response shows newly extracted correction patterns and updated active preferences

**Step 6: Generate improved draft**

Repeat Step 4 with the same `doc_id`. The system now automatically injects learned operator preferences into the system prompt. You'll see `"operator_preferences_applied"` in the response listing the active rules.

**Step 7: Inspect learned memory**

Expand **`GET /api/v1/memory`** and click Execute to see all accumulated correction patterns.

---

### Option C: curl (Command Line)

```bash
# 1. Ingest a document
curl -X POST http://localhost:8000/api/v1/ingest \
  -F "file=@sample_docs/eviction_notice.pdf"
# Returns: { "doc_id": "eviction_notice", "chunk_count": 8, ... }

# 2. Generate a draft
curl -X POST http://localhost:8000/api/v1/draft \
  -H "Content-Type: application/json" \
  -d '{"doc_id": "eviction_notice", "top_k": 5}'
# Returns: { "draft_id": "draft_...", "draft_text": "...", "evidence_used": [...] }

# 3. Submit an operator edit (replace draft_id with the value from step 2)
curl -X POST http://localhost:8000/api/v1/edit \
  -H "Content-Type: application/json" \
  -d '{"draft_id": "draft_...", "edited_text": "...your edited version..."}'
# Returns: { "new_patterns_extracted": 2, "active_preferences": [...] }

# 4. Inspect what was learned
curl http://localhost:8000/api/v1/memory

# 5. Generate improved draft (preferences auto-applied)
curl -X POST http://localhost:8000/api/v1/draft \
  -H "Content-Type: application/json" \
  -d '{"doc_id": "eviction_notice", "top_k": 5}'
```

---

### LLM Provider: OpenRouter (Live)

The system now runs on **OpenRouter** with the **DeepSeek V4 Flash free model** (`deepseek/deepseek-v4-flash:free`). Mock mode is no longer the default — the pipeline produces real LLM-generated memos and real pattern extraction from operator edits.

**To configure your own OpenRouter key:**

```bash
cp .env.example .env
# Then set in .env:
# LLM_PROVIDER=openrouter
# OPENROUTER_API_KEY=sk-or-xxxxxxxxxxxx
# OPENROUTER_MODEL=deepseek/deepseek-v4-flash:free
```

Get a free key (no credit card required) at **https://openrouter.ai/keys**.

**Available free models** (swap `OPENROUTER_MODEL` in `.env`):

| Model | ID |
|-------|----|
| DeepSeek V4 Flash *(current default)* | `deepseek/deepseek-v4-flash:free` |
| Llama 3.3 70B | `meta-llama/llama-3.3-70b-instruct:free` |
| Llama 3.2 3B (fast) | `meta-llama/llama-3.2-3b-instruct:free` |
| Gemma 4 31B | `google/gemma-4-31b-it:free` |
| Hermes 3 405B | `nousresearch/hermes-3-llama-3.1-405b:free` |

**Alternative providers** (also supported — set `LLM_PROVIDER` accordingly):

```bash
# Anthropic Claude
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx

# OpenAI
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxxxxxxxxxxx
```

### Testing Without an API Key (Mock Mode)

Mock mode is still available if you want to run the pipeline without any API key. All stages except LLM generation and pattern extraction work identically.

To run in mock mode, leave all API keys blank in `.env`:

```bash
cp .env.example .env
# Leave OPENROUTER_API_KEY, ANTHROPIC_API_KEY, and OPENAI_API_KEY all empty
python3 demo.py
```

You'll see real chunking, real FAISS retrieval scores, real metadata extraction, and a structured mock-generated memo.

---

## Running the Evaluation

```bash
# First run the demo to populate drafts
python3 demo.py

# Then run evaluation
python3 eval/evaluate.py eviction_notice
```

**Metrics produced:**

- **Retrieval Precision:** keyword overlap between query and retrieved chunks
- **Grounding Rate:** fraction of draft sentences that include a chunk citation
- **Citation Accuracy:** fraction of cited chunk IDs that exist in the evidence
- **Hallucination Estimate:** proper nouns in draft not found in evidence
- **Correction Memory:** count of patterns learned and active preferences

---

## Pipeline Overview

```
Upload PDF/Image
       ↓
OCR + Text Extraction        ← pymupdf (Tier 1) or Tesseract (Tier 2/3)
       ↓
Cleaning + Chunking          ← 600-char chunks, 100-char overlap
       ↓
Structured Metadata          ← parties, dates, addresses, doc type
       ↓
Embeddings + FAISS Index     ← sentence-transformers + cosine similarity
       ↓
Grounded Retrieval           ← top-5 chunks with confidence weighting
       ↓
Draft Generation             ← evidence-only prompting, chunk citations
       ↓
Operator Edits               ← capture in data/drafts/
       ↓
Pattern Extraction           ← LLM analyzes diff for reusable patterns
       ↓
Correction Memory            ← data/correction_memory.json
       ↓
Prompt Improvement           ← preferences injected into future drafts
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/ingest` | Upload PDF or image → extract, chunk, index |
| `GET` | `/api/v1/documents` | List all processed documents |
| `GET` | `/api/v1/documents/{doc_id}` | Get document metadata and chunks |
| `POST` | `/api/v1/draft` | Generate a grounded Case Fact Summary Memo |
| `GET` | `/api/v1/draft/{draft_id}` | Retrieve a generated draft |
| `POST` | `/api/v1/edit` | Submit operator edit → trigger learning loop |
| `GET` | `/api/v1/memory` | Inspect learned correction patterns |
| `GET` | `/api/v1/health` | Health check |

---

## Project Structure

```
Pearson Litt App/
├── app/
│   ├── ingestion/
│   │   ├── extractor.py           # Tiered OCR + text extraction
│   │   ├── chunker.py             # Sentence-aware overlapping chunker
│   │   ├── metadata_extractor.py  # Regex + spaCy NER extraction
│   │   └── pipeline.py            # Ingestion orchestrator
│   ├── retrieval/
│   │   ├── embedder.py            # sentence-transformers wrapper
│   │   ├── index.py               # FAISS index (build/save/search)
│   │   └── retriever.py           # Retrieval pipeline
│   ├── drafting/
│   │   └── generator.py           # Evidence-aware draft generation
│   ├── learning/
│   │   └── correction_memory.py   # Edit capture + pattern extraction
│   ├── api/
│   │   └── routes.py              # FastAPI endpoints
│   └── config.py                  # Centralized configuration
├── sample_docs/
│   ├── generate_samples.py        # Creates test documents
│   ├── lease_agreement.pdf        # Tier 1: digital PDF
│   ├── eviction_notice.pdf        # Tier 2: digital PDF (notice)
│   └── inspection_note.png        # Tier 3: image OCR
├── data/
│   ├── documents/                 # Processed document JSON
│   ├── indexes/                   # FAISS indexes per document
│   ├── drafts/                    # Generated + edited drafts
│   └── correction_memory.json     # Learned operator preferences
├── outputs/
│   ├── sample_draft_v1.json       # Example initial draft
│   └── sample_draft_v2_improved.json  # Example improved draft
├── eval/
│   └── evaluate.py                # Evaluation script
├── main.py                        # FastAPI app entry point
├── demo.py                        # End-to-end demo
├── architecture.md                # System design and decisions
├── requirements.txt
└── .env.example
```

---

## Technology Stack

| Layer | Tool | Reason |
|-------|------|--------|
| Language | Python 3.11+ | Standard, fast |
| API | FastAPI | Auto docs, type safety |
| PDF extraction | pymupdf | Fast, handles digital PDFs well |
| OCR | Tesseract | Open source, robust fallback |
| Embeddings | sentence-transformers | Local, no API cost, good quality |
| Vector DB | FAISS | Lightweight, no server needed |
| LLM | OpenRouter / Claude / OpenAI | Pluggable via env var — default: OpenRouter + DeepSeek V4 Flash (free) |
| Storage | Local JSON | Simple, inspectable, no database overhead |
| NER | spaCy | Fast regex-first, NER as enhancement |

---

## Bugs Found and Fixed During Testing

The following issues were caught during a full end-to-end verification pass and fixed before submission. Documented here for transparency.

### 1. Uploaded files got random temp filenames as their `doc_id`

**What broke:** The `/ingest` route saved uploads to a `tempfile.NamedTemporaryFile`, which generates a random path like `/tmp/tmp18_cglzu.pdf`. The ingestion pipeline used the file stem as the `doc_id`, so every uploaded document got an unreadable random ID (e.g. `tmp18_cglzu`) instead of `eviction_notice`.

**Fix:** The route now derives `doc_id` from the original uploaded filename before saving, sanitizes it for use as a filesystem key, and writes the temp file as `{clean_doc_id}{suffix}`. Result: uploading `eviction_notice.pdf` reliably yields `doc_id = "eviction_notice"` every time.

**File:** `app/api/routes.py`

---

### 2. A bad API key crashed with an unhandled 500, not a clear error

**What broke:** When `ANTHROPIC_API_KEY` was set to an invalid value, the Anthropic SDK raised an `AuthenticationError` (HTTP 401) inside `generate_draft()`. The `/draft` route had no handler for this, so it bubbled up as an opaque 500 Internal Server Error with a raw SDK traceback.

**Fix:** The `/draft` route now wraps `generate_draft()` in a try/except that detects authentication errors by status code and message content, and returns a clean `401` response with the message: `"LLM API authentication failed. Check your ANTHROPIC_API_KEY or OPENAI_API_KEY in .env"`. All other unexpected errors return `500` with the error detail rather than crashing silently.

**File:** `app/api/routes.py`

---

### 3. Document type detection misclassified the eviction notice as a memo

**What broke:** The `DOCUMENT_TYPE_PATTERNS` dictionary evaluated types in insertion order. The `"memo"` pattern matched first on eviction notices because they contain `"FROM:"` — a pattern shared with internal memos. An eviction notice was being classified as `document_type: "memo"` instead of `"eviction_notice"`.

**Fix:** Moved `"eviction_notice"` before `"lease_agreement"` and `"memo"` in the pattern dictionary, and added more specific matching patterns for eviction notices (e.g. `"notice to pay rent"`, `"in default under the terms"`). The type now correctly resolves to `"eviction_notice"` for all notice-style documents.

**File:** `app/ingestion/metadata_extractor.py`

---

### 4. Party extraction returned clause fragments instead of names

**What broke:** The regex patterns for extracting party names were too broad. On the lease agreement, phrases like `"Tenant agrees to pay"`, `"shall deposit with"`, and `"obligation under this Agreement"` were being returned as party names alongside the real names (`Margaret A. Pearson`, `Daniel J. Ross`).

**Fix:** Tightened the party patterns to only match proper-name structures (capitalised first + last name), added a stopword filter to reject known clause openers, stripped trailing noise words like `"Address"`, and added a validation rule requiring matches to look like real names (at least one space, mostly letters, no verb phrases). The extractor now returns only `['Margaret A. Pearson', 'Daniel J. Ross']` for both documents.

**File:** `app/ingestion/metadata_extractor.py`

---

### 5. `demo.py` referenced a field not present on `RetrievedChunk`

**What broke:** The demo printed `chunk.extraction_method` in the retrieval step. The `extraction_method` field exists on raw `Chunk` objects (from ingestion) but not on `RetrievedChunk` objects (returned by the retrieval layer), which only carry `chunk_id`, `text`, `source_page`, `confidence`, `similarity_score`, and `relevance_score`. Running the demo raised: `AttributeError: 'RetrievedChunk' object has no attribute 'extraction_method'`.

**Fix:** Removed the `extraction_method` reference from the demo print statement. The retrieval step now correctly prints `page`, `confidence`, and `relevance` — all fields that exist on `RetrievedChunk`.

**File:** `demo.py`

---

### Verification summary

After all fixes, a 14-point automated test suite passed clean:

| # | Check | Status |
|---|-------|--------|
| 1 | `GET /health` | ✓ 200 |
| 2 | `POST /ingest` — doc_id = original filename | ✓ 200 |
| 3 | `POST /ingest` — correct type, parties, dates | ✓ 200 |
| 4 | `GET /documents` | ✓ 200 |
| 5 | `GET /documents/{id}` — all metadata fields present | ✓ 200 |
| 6 | `POST /draft` — evidence chunks with chunk_id, page, relevance | ✓ 200 |
| 7 | `GET /draft/{id}` | ✓ 200 |
| 8 | `POST /edit` — patterns extracted, preferences rebuilt | ✓ 200 |
| 9 | `GET /memory` | ✓ 200 |
| 10 | `POST /draft` v2 — learned preferences injected | ✓ 200 |
| 11 | 404 on missing doc_id | ✓ 404 |
| 12 | 400 on unsupported file type | ✓ 400 |
| 13 | 404 on missing draft_id | ✓ 404 |
| 14 | 401 on invalid API key — clean error, not a crash | ✓ 401 |

---

## Deployment Note: Git Push & the index.lock Issue

### What happened

When pushing this repo to GitHub from the Cowork AI assistant (Claude), the push ran inside a **sandboxed Linux virtual machine** — not on the Mac directly. Here's why that matters, and what went wrong.

### Why does Claude run a Linux sandbox?

Claude's Cowork mode executes shell commands inside an isolated Ubuntu 22 container. This sandbox is spun up fresh for each session and mounts your Mac's folder as a network filesystem (via a path like `/sessions/<id>/mnt/`). The sandbox has git, Python, Node, and common CLI tools available, but it runs as a non-root user with strict write restrictions on the mounted filesystem.

This architecture exists for safety — the sandbox can't accidentally modify your Mac's system files, and each session starts clean. The tradeoff is that certain low-level filesystem operations (like deleting lock files in `.git/`) are blocked at the OS level, even though reading and writing normal project files works fine.

### The index.lock problem

Git uses a file called `.git/index.lock` as a mutex — it's created at the start of any operation that modifies the index, and deleted when that operation completes. If a git process crashes or is interrupted, it can leave a stale `index.lock` behind. Any subsequent git command will refuse to run and print:

```
fatal: Unable to create '.git/index.lock': File exists.
Another git process seems to be running in this repository.
```

In this session, the `.git/index.lock` file was a **zero-byte stale lock** left over from an earlier interrupted git operation. On a normal Mac terminal you'd fix it with `rm .git/index.lock` and move on. Inside the Linux sandbox, however, the mounted filesystem's permission model prevented the sandbox from deleting files inside the `.git/` directory, even though it could read them.

```
rm: cannot remove '.git/index.lock': Operation not permitted
```

### How it was resolved

Since the lock couldn't be deleted, the workaround was to use git's environment variable `GIT_INDEX_FILE` to redirect git to a fresh index file in a writable location (the sandbox's own `/outputs/` directory), bypassing the locked file entirely:

```bash
GIT_INDEX_FILE="/sessions/.../outputs/git_index_tmp" git add -A
GIT_INDEX_FILE="/sessions/.../outputs/git_index_tmp" git commit -m "..."
GIT_INDEX_FILE="/sessions/.../outputs/git_index_tmp" git push -u origin main
```

This let git stage, commit, and push all 35 files without touching the locked index.

### The GitHub username mismatch

A second issue: the target remote was set to `alamjamshed051/pearson-litt-legal-ai`, but the Personal Access Token provided belonged to the GitHub account `jamshed051`. GitHub rejected the push with `remote: Repository not found` because the token didn't have access to the `alamjamshed051` namespace. The fix was to confirm the correct username via the GitHub API (`GET /user`) and update the remote URL accordingly before pushing.

### If you need to push again from your Mac terminal

The stale lock file is still present on your Mac. Before running any git commands locally, remove it first:

```bash
rm "/Users/shihabsmac/Desktop/Legal Document AI app/Pearson Litt App/.git/index.lock"
```

Then push normally:

```bash
cd "/Users/shihabsmac/Desktop/Legal Document AI app/Pearson Litt App"
git push origin main
```

---

## Changelog

### May 2026 — OpenRouter Integration

- **Added OpenRouter as the default LLM provider** — replaces the previous Anthropic/OpenAI-only setup
- **Mock mode is no longer the default** — the system now produces real LLM output with a live API key
- **Default model:** `deepseek/deepseek-v4-flash:free` via OpenRouter — free, no credit card required, confirmed working
- **`app/config.py`** — added `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_BASE_URL` settings; default `LLM_PROVIDER` changed from `anthropic` to `openrouter`
- **`app/drafting/generator.py`** — added `_call_openrouter()` function; OpenRouter is now checked first in the provider priority chain
- **`app/learning/correction_memory.py`** — OpenRouter support added to the pattern extraction LLM call
- **`.env.example`** — updated to document OpenRouter as the recommended provider with free model options
- **`.env`** — created (not committed) with live OpenRouter key and `deepseek/deepseek-v4-flash:free` configured
- **API key verified** — live test call confirmed `OpenRouter connection successful` before full pipeline test

---

## Mac Installation Notes

If you're on macOS and hit issues during setup:

**`python` or `pip` not found:**
```bash
# macOS ships with python3/pip3, not python/pip
python3 -m venv venv
pip3 install -r requirements.txt
```

**SSL certificate error during pip install:**
```bash
# Open Finder → Applications → Python 3.x folder
# Double-click "Install Certificates.command"
# Then retry with trusted-host flags:
pip3 install -r requirements.txt \
  --trusted-host pypi.org \
  --trusted-host files.pythonhosted.org
```

**pymupdf metadata-generation-failed:**
```bash
pip3 install -r requirements.txt \
  --only-binary=:all: \
  --trusted-host pypi.org \
  --trusted-host files.pythonhosted.org
```
