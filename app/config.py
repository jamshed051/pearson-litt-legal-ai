"""
Central configuration for Legal Draft Assistant MVP.
All settings can be overridden via environment variables or a .env file.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DOCUMENTS_DIR = DATA_DIR / "documents"
INDEXES_DIR = DATA_DIR / "indexes"
DRAFTS_DIR = DATA_DIR / "drafts"
EDITS_DIR = DATA_DIR / "edits"
OUTPUTS_DIR = BASE_DIR / "outputs"
SAMPLE_DOCS_DIR = BASE_DIR / "sample_docs"
CORRECTION_MEMORY_PATH = DATA_DIR / "correction_memory.json"

# Create dirs on import
for d in [DOCUMENTS_DIR, INDEXES_DIR, DRAFTS_DIR, EDITS_DIR, OUTPUTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── LLM ───────────────────────────────────────────────────────────────────────
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")  # "anthropic" | "openai"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# ── Embedding ──────────────────────────────────────────────────────────────────
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "all-MiniLM-L6-v2"
)  # fast, good quality

# ── Chunking ───────────────────────────────────────────────────────────────────
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "600"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))

# ── Retrieval ──────────────────────────────────────────────────────────────────
TOP_K_CHUNKS = int(os.getenv("TOP_K_CHUNKS", "5"))
MIN_CONFIDENCE_THRESHOLD = float(os.getenv("MIN_CONFIDENCE_THRESHOLD", "0.3"))

# ── OCR ────────────────────────────────────────────────────────────────────────
OCR_DPI = int(os.getenv("OCR_DPI", "300"))
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "tesseract")
TEXT_EXTRACTION_MIN_CHARS = int(
    os.getenv("TEXT_EXTRACTION_MIN_CHARS", "50")
)  # below this → fallback to OCR
