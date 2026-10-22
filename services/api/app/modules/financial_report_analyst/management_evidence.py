"""M1.8B: original-PDF management-discussion *source passage* candidate.

Fixed topical selection, not a stored benchmark answer. Never infer whether a
management-labelled figure is accounting-comparable to an income-statement row.
The full source SHA and PIT are checked here; canonical SHA and both income-
statement cells must additionally have been verified by revenue_scope upstream.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path
import re
import unicodedata

import pymupdf

from app.modules.financial_report_analyst import revenue_scope

_TOPIC = "2026年上半年公司创新药销售收入"
_SECTION = "二、经营情况的讨论与分析"
_SUBSECTION = "创新成果持续兑现，创新药销售收入持续增长"
# Values come ONLY from the PDF. Neither model runtime nor tests store a real
# document reference answer. The regex constrains syntax, not expected values.
_SENTENCE = re.compile(
    r"2026年上半年公司创新药销售收入"
    r"[0-9]+(?:\.[0-9]+)?亿元，同比(?:增长|下降)"
    r"[0-9]+(?:\.[0-9]+)?%，占药品销售收入的"
    r"比重达[0-9]+(?:\.[0-9]+)?%[。]"
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", s))


def locate_management_excerpt(pdf_path: Path, *, as_of: datetime) -> dict:
    """Return an observed management passage only if two native text paths agree.

    A section cue, same-page subsection cue, exact literal sentence and full
    source SHA are required. Any ambiguity fails closed. No model or network.
    """
    source = revenue_scope.SOURCE
    source.require_available(as_of)
    if sha256(pdf_path.read_bytes()).hexdigest() != source.source_sha256:
        raise ValueError("SOURCE_SHA_MISMATCH")
    found: list[tuple[int, str]] = []
    with pymupdf.open(pdf_path) as pdf:
        for idx, page in enumerate(pdf):
            # Extract candidate from text; this is untrusted document content.
            txt = _norm(page.get_text("text", sort=True))
            if _TOPIC not in txt:
                continue
            if _SECTION not in txt or _SUBSECTION not in txt:
                continue
            matches = list(_SENTENCE.finditer(txt))
            if len(matches) != 1:
                raise ValueError("MANAGEMENT_SENTENCE_MISSING_OR_AMBIGUOUS")
            passage = matches[0].group(0)
            # Independent native-PDF word location check on the same page.
            # This establishes literal co-location, NOT management veracity.
            words = page.get_text("words", sort=True)
            word_text = _norm("".join(w[4] for w in words))
            if word_text.count(passage) != 1:
                raise ValueError("MANAGEMENT_NATIVE_TEXT_LOCATION_MISMATCH")
            found.append((idx + 1, passage))
    if len(found) != 1:
        raise ValueError("MANAGEMENT_SOURCE_NOT_UNIQUE")
    page_number, passage = found[0]
    identity = "|".join((source.document_id, source.canonical_sha256,
                         str(page_number), "management-innovation-sales-v1", passage))
    return {
        "status": "SOURCE_PASSAGE_REVIEWED",
        "document_id": source.document_id,
        "source_sha256": source.source_sha256,
        "canonical_sha256": source.canonical_sha256,
        "source_url": source.source_url,
        "evidence_id": sha256(identity.encode()).hexdigest(),
        "source_page": page_number,
        "source_section": "管理层讨论与分析 / 经营情况的讨论与分析",
        "source_kind": "MANAGEMENT_DISCUSSION_PASSAGE",
        "passage_whitespace_normalized": passage,
        "review_scope": "NATIVE_PDF_TEXT_AND_WORD_LOCATION_ONLY",
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
    }
