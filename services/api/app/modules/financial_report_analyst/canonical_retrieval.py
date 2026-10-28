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
from app.modules.financial_report_analyst import terminology_candidates

RETRIEVER_VERSION = "frp-canonical-lexical-v1"
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


# M127: bounded, non-semantic ranking hints for terminology-expanded previews.
# These hints identify text proximity only, not units, dates, statement scope,
# accounting equivalence or financial correctness.
RANKING_VERSION = "frp-m127-quantity-proximity-page-diversity-v1"
# M129: filing-wording cues from already verified text, not financial definitions.
LICENSING_WORDING_VERSION = "frp-m129-licensing-wording-v1"
LICENSING_RANKING_VERSION = "frp-m129-licensing-cue-priority-v1"
LICENSING_REVIEW = "LITERAL_DISCLOSURE_WORDING_ONLY_NOT_FINANCIAL_SEMANTICS"
_LICENSING_CONCEPTS = frozenset((
    "licensing_recognized_revenue", "licensing_potential_deal_value",
))
_AMOUNT_QUERY_CUES = ("多少", "金额", "规模", "占比", "比重", "同比", "增速", "增幅")
_AMOUNT_TOKEN = re.compile(
    r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|"
    r"\d+(?:\.\d+)?(?:亿元|万元|亿美元|万美元|元|美元|%))"
)


def _amount_proximity_bonus(question: str, excerpt: str, probe: dict) -> float:
    """Rank, never interpret, an amount near the prefix of an audited concept.

    Only active for amount-style questions with an expanded terminology cue.
    The monetary token is NOT assigned to the concept; it is just nearby text.
    """
    if (probe["status"] != "ACTIVATED"
            or not any(cue in question for cue in _AMOUNT_QUERY_CUES)):
        return 0.0
    compact = re.sub(r"\s+", "", unicodedata.normalize("NFKC", excerpt)).casefold()
    amounts = tuple(match.start() for match in _AMOUNT_TOKEN.finditer(compact))
    if not amounts:
        return 0.0
    for candidate in probe["candidates"]:
        label = re.sub(r"\s+", "", unicodedata.normalize(
            "NFKC", candidate["preferred_zh"])).casefold()
        anchor = label[:min(4, len(label))]
        if len(anchor) < 2:
            continue
        for match in re.finditer(re.escape(anchor), compact):
            # A bounded text window does not prove the nearby amount's meaning.
            if any(abs(position - match.end()) <= 85 for position in amounts):
                return 15.0
    return 0.0


def _licensing_target(probe: dict) -> str | None:
    """Only act on one unambiguous registry concept (M126 provenance)."""
    candidates = probe["candidates"]
    if probe["status"] != "ACTIVATED" or len(candidates) != 1:
        return None
    concept = candidates[0]["concept_id"]
    return concept if concept in _LICENSING_CONCEPTS else None


def _licensing_wording_cues(excerpt: str) -> list[str]:
    """Exact wording in a bounded excerpt, never an amount-to-metric assignment.

    Different disclosures (including different periods or transactions) may
    appear within the SAME excerpt. Multiple cues indicate mixed wording and
    must never be simplified into an accounting verdict.
    """
    normalized = re.sub(r"\s+", "", unicodedata.normalize("NFKC", excerpt))
    cues: list[str] = []
    if ("报告期内确认收入" in normalized or "报告期内确认的" in normalized):
        cues.append("RECOGNITION_WORDING")
    if ("潜在总交易价值" in normalized or "潜在总交易额" in normalized):
        cues.append("POTENTIAL_VALUE_WORDING")
    if "尚未确认收入" in normalized:
        cues.append("NOT_YET_RECOGNIZED_WORDING")
    return cues


def _licensing_priority(target: str | None, excerpt: str) -> int:
    """Put an unambiguous target phrase first; no numerical or scope claims."""
    if target is None:
        return 0
    cues = set(_licensing_wording_cues(excerpt))
    if target == "licensing_recognized_revenue":
        # An excerpt mentioning both potential/absent and recognized wording
        # is NOT a clean source of one particular financial amount.
        return int(cues == {"RECOGNITION_WORDING"} and
                   "对外许可" in re.sub(r"\s+", "", excerpt))
    if target == "licensing_potential_deal_value":
        return int("POTENTIAL_VALUE_WORDING" in cues)
    return 0


def _diversify_pages(ranked: list[tuple]) -> list[tuple]:
    """Take best available excerpt per page before using page duplicates.

    Not a hard exclusion: when too few unique pages exist, the remainder
    fills from the original score order. Distinct cash-flow pages are retained.
    """
    seen = set()
    unique = []
    extra = []
    for hit in ranked:
        if hit[1] in seen:
            extra.append(hit)
        else:
            seen.add(hit[1])
            unique.append(hit)
    return unique + extra


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

    # M126: terminology matches only affect retrieval candidates; not assertions.
    terminology_probe = terminology_candidates.candidate_probe(question)
    licensing_target = _licensing_target(terminology_probe)
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
        expansion_bonus = terminology_candidates.candidate_score(excerpt, terminology_probe)
        if not matched and not expansion_bonus:
            continue
        # Local keyword recall baseline. Score is NOT a relevance probability.
        score = sum(log1p(total / (1 + frequency[term])) for term in matched)
        score *= (0.8 + 0.2 * len(matched) / max(len(tokens), 1))
        score += expansion_bonus
        if terminology_probe["status"] == "ACTIVATED":
            score += _amount_proximity_bonus(question, excerpt, terminology_probe)
        ranked.append((score, page, start, end, excerpt))
    if licensing_target is not None:
        # M129: a clearly matching disclosure phrase precedes an unrelated
        # transaction-value snippet. This is a lexical candidate ordering only.
        ranked.sort(key=lambda x: (-_licensing_priority(licensing_target, x[4]),
                                   -x[0], x[1], x[2]))
    else:
        ranked.sort(key=lambda x: (-x[0], x[1], x[2]))
    if terminology_probe["status"] == "ACTIVATED":
        ranked = _diversify_pages(ranked)

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
            "licensing_wording_cues": (
                _licensing_wording_cues(excerpt)
                if licensing_target is not None else []
            ),
        })

    hits, heading_alert = attach_heading_context(document, hits)

    identity = [RETRIEVER_VERSION, source.document_id, source.canonical_sha256,
                as_of.date().isoformat(), question]
    if terminology_probe["status"] == "ACTIVATED":
        identity.extend((terminology_candidates.VERSION,
                         terminology_candidates.REGISTRY_SHA256,
                         LICENSING_RANKING_VERSION if licensing_target else RANKING_VERSION))
    if licensing_target:
        identity.extend((LICENSING_WORDING_VERSION, licensing_target))
    run_id = sha256("|".join(identity).encode("utf-8")).hexdigest()
    return {
        "status": "RETRIEVAL_CANDIDATES_READY" if hits else "WITHHELD",
        "reason": None if hits else "NO_LEXICAL_MATCH_NOT_EVIDENCE_OF_ABSENCE",
        "retrieval_id": run_id,
        "retriever_version": RETRIEVER_VERSION,
        # SourceDocument is server-selected and source/PIT verified upstream.
        # This is metadata identity, not question-driven report selection.
        "report_key": f"{source.ticker}-{source.report_period}",
        "question": question,
        "as_of": as_of.isoformat(),
        "document_id": source.document_id,
        "report_period": source.report_period,
        "source_url": source.source_url,
        "source_sha256": source.source_sha256,
        "canonical_sha256": source.canonical_sha256,
        "evidence": hits,
        "terminology_probe": terminology_probe,
        "licensing_wording_probe": {
            "version": LICENSING_WORDING_VERSION,
            "status": "ACTIVATED" if licensing_target else "NOT_APPLICABLE",
            "target_concept_id": licensing_target,
            "review": LICENSING_REVIEW,
        },
        "ranking_version": (
            LICENSING_RANKING_VERSION if licensing_target else
            RANKING_VERSION if terminology_probe["status"] == "ACTIVATED" else
            "frp-legacy-lexical-v1"
        ),
        "context_probe_version": CONTEXT_VERSION,
        "statement_heading_alert": heading_alert,
        "retrieval_context_review": "HEADING_CUE_ONLY_NOT_SEMANTICALLY_REVIEWED",
        "retrieval_review": "CANDIDATES_NOT_RELEVANCE_QUALIFIED",
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
        "report_storage": "NOT_PERSISTED",
        "limitations": (
            "Lexical candidates only; not an answer or evidence-sufficiency judgment."
            " Candidate terminology is retrieval-only, never accounting equivalence;"
            " expanded results may use amount proximity and one-page-first diversity;"
            " licensing cue priority only matches literal wording, never a financial amount;"
            " excerpts may contain mixed periods, transactions or recognition status;"
            " proximity does not prove a value belongs to a concept;"
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
