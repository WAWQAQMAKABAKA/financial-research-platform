"""M122: bounded lexical evidence candidates from a verified financial PDF.

Retrieval ranks literal canonical-text spans; it does not verify accounting
semantics, generate answers, or certify relevance. No labels/GT or model calls.
The selected source comes from a trusted server-side registry, not a question.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from hashlib import sha256
from math import log1p
from pathlib import Path
import re
import unicodedata

from app.evidence.contracts import EvidenceSpan, SourceDocument, require_evidence_binding
from app.evidence.pdf_canonicalizer import CanonicalDocument, canonicalize_pdf
from app.modules.financial_report_analyst.source_context import (
    CONTEXT_VERSION, attach_heading_context,
)

RETRIEVER_VERSION = "frp-canonical-lexical-v1"
_REPORT_KEY = "600276-2026H1"  # Local report selection; not a question/answer rule.
_WINDOW = 540
_OVERLAP = 105
_MAX_HITS = 5
_WORDS = re.compile(r"[\u3400-\u9fff]+|[a-z0-9]+", re.IGNORECASE)


def _terms(value: str) -> set[str]:
    """Simple lexical baseline, including CJK bigrams/trigrams, no finance synonyms."""
    compact = re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).casefold()
    terms: set[str] = set()
    for item in _WORDS.findall(compact):
        if re.fullmatch(r"[\u3400-\u9fff]+", item):
            for n in (2, 3):
                terms.update(item[i:i+n] for i in range(len(item)-n+1))
        elif len(item) >= 2:
            terms.add(item)
    return terms


def _windows(document: CanonicalDocument):
    text = document.canonical_text
    previous_end = 0
    for expected_page, page in enumerate(document.pages, start=1):
        marker = f"=== PAGE {expected_page} ===\n"
        if not (
            page.page_number == expected_page
            and previous_end <= page.marker_start
            and 0 <= page.marker_start <= page.content_start
            <= page.content_end <= len(text)
            and text[page.marker_start:page.content_start] == marker
        ):
            raise ValueError("CANONICAL_PAGE_OFFSETS_INVALID")
        previous_end = page.content_end
        position = page.content_start
        while position < page.content_end:
            stop = min(position + _WINDOW, page.content_end)
            if stop < page.content_end:
                newline = text.rfind("\n", position + 350, stop)
                if newline > position + 350:
                    stop = newline + 1
            if text[position:stop].strip():
                yield (page.page_number, position, stop, text[position:stop])
            if stop == page.content_end:
                break
            position = max(position + 1, stop - _OVERLAP)


def retrieve_from_canonical(
    source: SourceDocument,
    document: CanonicalDocument,
    question: str,
    *,
    as_of: datetime,
) -> dict:
    """Rank source-text candidates; canonical offsets are checked before exposure."""
    source.require_available(as_of)
    if (
        document.document_id != source.document_id
        or document.source_sha256 != source.source_sha256
        or document.canonical_sha256 != source.canonical_sha256
        or sha256(document.canonical_text.encode("utf-8")).hexdigest()
            != document.canonical_sha256
    ):
        raise ValueError("CANONICAL_SOURCE_BINDING_INVALID")
    if (not isinstance(question, str) or not question.strip()
            or len(question) > 240 or len(question.encode("utf-8")) > 800):
        raise ValueError("RETRIEVAL_QUESTION_INVALID")

    tokens = _terms(question)
    windows = list(_windows(document))
    if not windows:
        raise ValueError("CANONICAL_DOCUMENT_EMPTY")
    terms_by_window = [_terms(item[3]) for item in windows]
    frequency = Counter(term for terms in terms_by_window for term in terms)
    total = len(windows)
    ranked = []
    for (page, start, end, excerpt), terms in zip(windows, terms_by_window):
        matched = tokens & terms
        if not matched:
            continue
        # Local keyword recall baseline. Score is NOT a relevance probability.
        score = sum(log1p(total / (1 + frequency[term])) for term in matched)
        score *= (0.8 + 0.2 * len(matched) / max(len(tokens), 1))
        ranked.append((score, page, start, end, excerpt))
    ranked.sort(key=lambda x: (-x[0], x[1], x[2]))

    hits = []
    for _, page, start, end, excerpt in ranked[:_MAX_HITS]:
        span_id = sha256("|".join((
            RETRIEVER_VERSION, source.document_id,
            source.canonical_sha256, str(page), str(start), str(end), excerpt,
        )).encode("utf-8")).hexdigest()
        evidence = EvidenceSpan(
            evidence_id=span_id,
            document_id=source.document_id,
            canonical_sha256=source.canonical_sha256,
            page_number=page,
            canonical_start=start,
            canonical_end=end,
            excerpt=excerpt,
        )
        require_evidence_binding(source, evidence, as_of)
        if document.canonical_text[start:end] != excerpt:
            raise ValueError("CANONICAL_SPAN_CONTENT_MISMATCH")
        hits.append({
            "evidence_id": evidence.evidence_id,
            "source_page": evidence.page_number,
            "canonical_start": evidence.canonical_start,
            "canonical_end": evidence.canonical_end,
            "source_excerpt": evidence.excerpt,
            "review_scope": "VERIFIED_CANONICAL_TEXT_SPAN_ONLY",
        })

    hits, heading_alert = attach_heading_context(document, hits)

    run_id = sha256("|".join((
        RETRIEVER_VERSION, source.document_id, source.canonical_sha256,
        as_of.date().isoformat(), question,
    )).encode("utf-8")).hexdigest()
    return {
        "status": "RETRIEVAL_CANDIDATES_READY" if hits else "WITHHELD",
        "reason": None if hits else "NO_LEXICAL_MATCH_NOT_EVIDENCE_OF_ABSENCE",
        "retrieval_id": run_id,
        "retriever_version": RETRIEVER_VERSION,
        "report_key": _REPORT_KEY,
        "question": question,
        "as_of": as_of.isoformat(),
        "document_id": source.document_id,
        "report_period": source.report_period,
        "source_url": source.source_url,
        "source_sha256": source.source_sha256,
        "canonical_sha256": source.canonical_sha256,
        "evidence": hits,
        "context_probe_version": CONTEXT_VERSION,
        "statement_heading_alert": heading_alert,
        "retrieval_context_review": "HEADING_CUE_ONLY_NOT_SEMANTICALLY_REVIEWED",
        "retrieval_review": "CANDIDATES_NOT_RELEVANCE_QUALIFIED",
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
        "report_storage": "NOT_PERSISTED",
        "limitations": (
            "Lexical candidates only; not an answer or evidence-sufficiency judgment."
            " Chinese/English synonym matching and table geometry are not qualified."
        ),
    }


def retrieve_report_evidence(
    source: SourceDocument,
    pdf_path: Path,
    question: str,
    *,
    as_of: datetime,
) -> dict:
    """Verify PIT, full PDF SHA and canonical SHA before ranking any chunk."""
    source.require_available(as_of)
    document = canonicalize_pdf(
        document_id=source.document_id,
        pdf_path=pdf_path,
        expected_source_sha256=source.source_sha256,
    )
    return retrieve_from_canonical(source, document, question, as_of=as_of)
