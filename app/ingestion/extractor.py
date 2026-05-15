"""
Document extractor: tiered text extraction for messy legal documents.

Tier 1 — Digital PDFs:   pymupdf direct extraction
Tier 2 — Scanned PDFs:   Tesseract OCR via page-image rendering
Tier 3 — Images:         Tesseract OCR directly on the image

Each extracted chunk carries an OCR confidence score (0.0–1.0).
Low-confidence chunks are flagged so the retrieval layer can deprioritize them.
"""

from __future__ import annotations

import io
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RawPage:
    """Text extracted from a single page with metadata."""

    page_num: int
    text: str
    confidence: float  # 0.0 = pure OCR noise, 1.0 = clean digital text
    extraction_method: str  # "direct" | "ocr" | "ocr_image"
    char_count: int = field(init=False)

    def __post_init__(self) -> None:
        self.char_count = len(self.text.strip())


@dataclass
class ExtractedDocument:
    """Full extraction result for a single document."""

    doc_id: str
    source_path: str
    file_type: str  # "pdf" | "image"
    pages: list[RawPage]
    full_text: str = field(init=False)
    avg_confidence: float = field(init=False)

    def __post_init__(self) -> None:
        texts = [p.text for p in self.pages if p.text.strip()]
        self.full_text = "\n\n".join(texts)
        if self.pages:
            self.avg_confidence = sum(p.confidence for p in self.pages) / len(
                self.pages
            )
        else:
            self.avg_confidence = 0.0


def _clean_text(raw: str) -> str:
    """Normalize whitespace, fix common OCR artefacts, join broken lines."""
    # Unicode normalize
    text = unicodedata.normalize("NFKC", raw)
    # Replace form-feeds and null bytes
    text = text.replace("\x0c", "\n").replace("\x00", "")
    # Collapse multiple spaces (but preserve newlines)
    text = re.sub(r"[ \t]{2,}", " ", text)
    # Join lines that were broken mid-word (common in OCR)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    # Collapse 3+ blank lines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _ocr_confidence(ocr_data: dict) -> float:
    """Compute mean word-level OCR confidence from pytesseract data dict."""
    try:
        confidences = [
            int(c)
            for c in ocr_data.get("conf", [])
            if str(c).strip() not in ("-1", "")
        ]
        if not confidences:
            return 0.5
        return round(sum(confidences) / len(confidences) / 100.0, 3)
    except Exception:
        return 0.5


def extract_pdf(
    path: Path, min_chars: int = 50
) -> ExtractedDocument:
    """
    Extract text from a PDF using a tiered strategy:
    1. Direct pymupdf extraction (fast, high quality for digital PDFs)
    2. OCR fallback for pages with insufficient text (scanned / image-heavy)
    """
    import fitz  # pymupdf

    doc_id = path.stem
    pages: list[RawPage] = []

    try:
        pdf = fitz.open(str(path))
    except Exception as exc:
        logger.error("Failed to open PDF %s: %s", path, exc)
        raise

    for page_num, page in enumerate(pdf, start=1):
        # ── Tier 1: direct text extraction ────────────────────────────────────
        raw_text = page.get_text("text")
        cleaned = _clean_text(raw_text)

        if len(cleaned) >= min_chars:
            pages.append(
                RawPage(
                    page_num=page_num,
                    text=cleaned,
                    confidence=1.0,
                    extraction_method="direct",
                )
            )
            continue

        # ── Tier 2: OCR fallback ───────────────────────────────────────────────
        logger.info(
            "Page %d of %s has only %d chars — falling back to OCR",
            page_num,
            path.name,
            len(cleaned),
        )
        ocr_page = _ocr_pdf_page(page, page_num)
        pages.append(ocr_page)

    pdf.close()
    return ExtractedDocument(
        doc_id=doc_id,
        source_path=str(path),
        file_type="pdf",
        pages=pages,
    )


def _ocr_pdf_page(page, page_num: int) -> RawPage:
    """Render a PDF page to an image and run Tesseract OCR on it."""
    try:
        import pytesseract
        from PIL import Image

        # Render at 300 DPI for decent OCR quality
        mat = page.get_pixmap(matrix=page.__class__.__mro__[0].__dict__.get(
            "Identity", None
        ) or __import__("fitz").Matrix(300 / 72, 300 / 72))
        img_bytes = mat.tobytes("png")
        img = Image.open(io.BytesIO(img_bytes))

        ocr_data = pytesseract.image_to_data(
            img, output_type=pytesseract.Output.DICT, lang="eng"
        )
        confidence = _ocr_confidence(ocr_data)
        raw_text = pytesseract.image_to_string(img, lang="eng")
        cleaned = _clean_text(raw_text)

        return RawPage(
            page_num=page_num,
            text=cleaned,
            confidence=confidence,
            extraction_method="ocr",
        )
    except Exception as exc:
        logger.warning("OCR failed for page %d: %s", page_num, exc)
        return RawPage(
            page_num=page_num,
            text="[OCR FAILED — page unreadable]",
            confidence=0.0,
            extraction_method="ocr_failed",
        )


def _ocr_pdf_page_fitz(page, page_num: int) -> RawPage:
    """Render a fitz page to image properly using its own matrix."""
    try:
        import fitz
        import pytesseract
        from PIL import Image

        mat = fitz.Matrix(300 / 72, 300 / 72)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_bytes))

        ocr_data = pytesseract.image_to_data(
            img, output_type=pytesseract.Output.DICT, lang="eng"
        )
        confidence = _ocr_confidence(ocr_data)
        raw_text = pytesseract.image_to_string(img, lang="eng")
        cleaned = _clean_text(raw_text)

        return RawPage(
            page_num=page_num,
            text=cleaned,
            confidence=confidence,
            extraction_method="ocr",
        )
    except Exception as exc:
        logger.warning("OCR failed for page %d: %s", page_num, exc)
        return RawPage(
            page_num=page_num,
            text="[OCR FAILED — page unreadable]",
            confidence=0.0,
            extraction_method="ocr_failed",
        )


def extract_pdf(path: Path, min_chars: int = 50) -> ExtractedDocument:
    """
    Extract text from a PDF using a tiered strategy:
    1. Direct pymupdf extraction (fast, high quality for digital PDFs)
    2. OCR fallback for pages with insufficient text (scanned / image-heavy)
    """
    import fitz

    doc_id = path.stem
    pages: list[RawPage] = []

    try:
        pdf = fitz.open(str(path))
    except Exception as exc:
        logger.error("Failed to open PDF %s: %s", path, exc)
        raise

    for page_num, page in enumerate(pdf, start=1):
        raw_text = page.get_text("text")
        cleaned = _clean_text(raw_text)

        if len(cleaned) >= min_chars:
            pages.append(
                RawPage(
                    page_num=page_num,
                    text=cleaned,
                    confidence=1.0,
                    extraction_method="direct",
                )
            )
        else:
            logger.info(
                "Page %d of %s has only %d chars — falling back to OCR",
                page_num, path.name, len(cleaned),
            )
            ocr_page = _ocr_pdf_page_fitz(page, page_num)
            pages.append(ocr_page)

    pdf.close()
    return ExtractedDocument(
        doc_id=doc_id,
        source_path=str(path),
        file_type="pdf",
        pages=pages,
    )


def extract_image(path: Path) -> ExtractedDocument:
    """
    Tier 3: direct OCR on image files (PNG, JPG, TIFF).
    Handles handwritten notes and photographed documents.
    """
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(str(path))
        # Convert to RGB if needed
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        ocr_data = pytesseract.image_to_data(
            img, output_type=pytesseract.Output.DICT, lang="eng"
        )
        confidence = _ocr_confidence(ocr_data)
        raw_text = pytesseract.image_to_string(img, lang="eng")
        cleaned = _clean_text(raw_text)

        page = RawPage(
            page_num=1,
            text=cleaned,
            confidence=confidence,
            extraction_method="ocr_image",
        )
        return ExtractedDocument(
            doc_id=path.stem,
            source_path=str(path),
            file_type="image",
            pages=[page],
        )
    except Exception as exc:
        logger.error("Image OCR failed for %s: %s", path, exc)
        raise


def extract_document(path: Path, min_chars: int = 50) -> ExtractedDocument:
    """
    Unified entry point: dispatch to the correct extractor based on file type.
    Raises ValueError for unsupported formats.
    """
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path, min_chars=min_chars)
    elif suffix in (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"):
        return extract_image(path)
    else:
        raise ValueError(
            f"Unsupported file type: {suffix}. Supported: .pdf, .png, .jpg, .jpeg, .tiff"
        )
