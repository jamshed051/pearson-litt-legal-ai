"""
Structured metadata extraction from legal document text.

Extracts:
- document_type  (lease, notice, contract, memo, etc.)
- parties        (names of individuals/organizations)
- dates          (all date mentions with context)
- addresses      (mailing addresses)
- case/reference numbers

Uses a regex-first approach with spaCy NER as enhancement.
Gracefully degrades if spaCy is unavailable.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── Document type detection ────────────────────────────────────────────────────
DOCUMENT_TYPE_PATTERNS: dict[str, list[str]] = {
    "eviction_notice": [
        r"\bnotice\s+to\s+(pay|quit|vacate|cure)\b",
        r"\beviction\s+notice\b",
        r"\bunlawful\s+detainer\b",
        r"\bpay\s+or\s+quit\b",
        r"\bnotice\s+to\s+pay\s+rent\b",
        r"\bin\s+default\s+under\s+the\s+terms\b",
    ],
    "lease_agreement": [
        r"\blease\s+agreement\b",
        r"\brental\s+agreement\b",
        r"\btenancy\s+agreement\b",
        r"\blessor\b",
        r"\blessee\b",
        r"\bmonthly\s+rent\b",
    ],
    "demand_letter": [
        r"\bdemand\s+letter\b",
        r"\bhereby\s+demand\b",
        r"\bimmediate\s+payment\b",
        r"\bfinal\s+notice\b",
    ],
    "court_filing": [
        r"\bplaintiff\b",
        r"\bdefendant\b",
        r"\bpetitioner\b",
        r"\brespondent\b",
        r"\bcourt\s+of\b",
        r"\bcase\s+no\b",
        r"\bdocket\b",
    ],
    "contract": [
        r"\bagreement\s+(is\s+)?entered\b",
        r"\bwhereas\b",
        r"\bin\s+consideration\s+of\b",
        r"\bhereinafter\b",
    ],
    "memo": [
        r"\bmemorandu(m|mm)\b",
        r"\bto:\s+",
        r"\bfrom:\s+",
        r"\bre:\s+",
    ],
}

# ── Date patterns ─────────────────────────────────────────────────────────────
DATE_PATTERNS = [
    # Jan 1, 2024 / January 1, 2024
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{1,2},?\s+\d{4}\b",
    # 1/15/2024 or 01-15-2024
    r"\b\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}\b",
    # 2024-01-15 (ISO)
    r"\b\d{4}-\d{2}-\d{2}\b",
    # "the 15th of January, 2024"
    r"\bthe\s+\d{1,2}(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?(?:January|February|March|April|May|June|"
    r"July|August|September|October|November|December)\b[,\s]+\d{4}\b",
]

# ── Party name patterns ───────────────────────────────────────────────────────
# Matches names like "John Doe" or "ABC Holdings LLC" near role keywords
PARTY_PATTERNS = [
    # "LANDLORD: Margaret A. Pearson" / "TO: Daniel J. Ross"
    r"(?:LANDLORD|TENANT|LESSOR|LESSEE|TO|FROM)\s*:\s*([A-Z][a-z]+(?:\s+[A-Z]\.?\s+[A-Z][a-z]+|\s+[A-Z][a-z]+){1,3})\b",
    # "John Doe, Plaintiff" / "ABC Corp, Defendant" (name before role)
    r"([A-Z][a-z]+\s+[A-Z]\.?\s*[A-Z][a-z]+)\s*[,;]?\s*"
    r"(?:Plaintiff|Defendant|Petitioner|Respondent|Lessor|Lessee|Landlord|Tenant|Buyer|Seller|Borrower|Lender)\b",
]

# Words that look like names but are actually clauses — filter these out
_PARTY_STOPWORDS = {
    "tenant", "landlord", "lessor", "lessee", "plaintiff", "defendant",
    "this agreement", "said deposit", "execution", "performance", "condition",
    "ross landlord", "default if", "property condition",
}

# ── Address patterns ──────────────────────────────────────────────────────────
ADDRESS_PATTERN = re.compile(
    r"\d{1,5}\s+[A-Za-z0-9\s]+(?:Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|"
    r"Drive|Dr|Lane|Ln|Court|Ct|Place|Pl|Way|Circle|Cir)[,\s]+[A-Za-z\s]+[,\s]+"
    r"(?:[A-Z]{2})\s+\d{5}(?:-\d{4})?",
    re.IGNORECASE,
)

# ── Case number patterns ──────────────────────────────────────────────────────
CASE_NUMBER_PATTERN = re.compile(
    r"(?:Case\s+No\.?|Docket\s+No\.?|File\s+No\.?|Ref\.?\s+No\.?)\s*:?\s*"
    r"([A-Z0-9\-\/]{4,20})",
    re.IGNORECASE,
)


def _detect_document_type(text: str) -> str:
    text_lower = text.lower()
    scores: dict[str, int] = {}
    for doc_type, patterns in DOCUMENT_TYPE_PATTERNS.items():
        score = sum(
            1 for p in patterns if re.search(p, text_lower, re.IGNORECASE)
        )
        if score:
            scores[doc_type] = score
    if scores:
        return max(scores, key=scores.get)
    return "unknown_document"


def _extract_dates(text: str) -> list[str]:
    dates: list[str] = []
    for pattern in DATE_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        dates.extend(m.strip() if isinstance(m, str) else " ".join(m).strip()
                     for m in matches)
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique = []
    for d in dates:
        norm = re.sub(r"\s+", " ", d).strip()
        if norm and norm not in seen:
            seen.add(norm)
            unique.append(norm)
    return unique


def _extract_parties(text: str) -> list[str]:
    parties: list[str] = []
    for pattern in PARTY_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                parties.extend(m.strip() for m in match if m.strip())
            elif isinstance(match, str):
                parties.append(match.strip())

    # Also try spaCy PERSON / ORG entities if available
    try:
        import spacy
        try:
            nlp = spacy.load("en_core_web_sm")
        except OSError:
            nlp = None
        if nlp:
            # Process only first 10k chars to keep it fast
            doc = nlp(text[:10000])
            for ent in doc.ents:
                if ent.label_ in ("PERSON", "ORG"):
                    parties.append(ent.text.strip())
    except ImportError:
        pass

    # Deduplicate and filter out stopwords / clause fragments
    seen: set[str] = set()
    unique = []
    for p in parties:
        clean = re.sub(r"\s+", " ", p).strip()
        # Strip trailing noise words like "Address"
        clean = re.sub(r"\s+(Address|Inc|LLC|Corp|Ltd|Esq)\.?$", "", clean).strip()
        if (
            clean
            and len(clean) > 4
            and clean.lower() not in _PARTY_STOPWORDS
            and not re.match(r"^(this|said|such|the|of|in|on|at|to|from|deposit|notice|upon)\b", clean, re.I)
            and clean not in seen
            # Must look like a real name: at least one space and mostly letters
            and " " in clean
            and re.match(r"^[A-Z][a-zA-Z\.\s]+$", clean)
        ):
            seen.add(clean)
            unique.append(clean)
    return unique[:10]  # cap at 10


def _extract_addresses(text: str) -> list[str]:
    matches = ADDRESS_PATTERN.findall(text)
    return list(dict.fromkeys(m.strip() for m in matches))


def _extract_case_numbers(text: str) -> list[str]:
    matches = CASE_NUMBER_PATTERN.findall(text)
    return list(dict.fromkeys(matches))


def extract_metadata(text: str, doc_id: str) -> dict:
    """
    Extract structured metadata from legal document text.
    Returns a dict ready to be stored alongside the document.
    """
    return {
        "doc_id": doc_id,
        "document_type": _detect_document_type(text),
        "parties": _extract_parties(text),
        "dates": _extract_dates(text),
        "addresses": _extract_addresses(text),
        "case_numbers": _extract_case_numbers(text),
    }
