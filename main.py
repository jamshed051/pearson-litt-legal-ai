"""
Legal Draft Assistant MVP — Entry point.

Run with:
    uvicorn main:app --reload --port 8000

API docs available at: http://localhost:8000/docs
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(
    title="Legal Draft Assistant MVP",
    description=(
        "AI pipeline for ingesting messy legal documents, extracting grounded evidence, "
        "generating Case Fact Summary Memos, and improving from operator edits."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/")
def root():
    return {
        "service": "Legal Draft Assistant MVP",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "ingest":    "POST /api/v1/ingest",
            "documents": "GET  /api/v1/documents",
            "draft":     "POST /api/v1/draft",
            "edit":      "POST /api/v1/edit",
            "memory":    "GET  /api/v1/memory",
            "health":    "GET  /api/v1/health",
        },
    }
