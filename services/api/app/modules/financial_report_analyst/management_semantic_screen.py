"""M1.9B: bounded source-bound management contradiction screening.

Only rejects explicit substitutions in recognized narrative structures.
Input management evidence must come from original-PDF verification.
Never certifies accounting meaning, admits claims, or permits publication.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import re
import unicodedata

from app.evidence.contracts import SourceDocument
from app.modules.financial_report_analyst.semantic_gate import (
    ScreenVerdict,
    SemanticScreenResult,
)

# The passage's figures are parsed from source text, not hardcoded.
_PASSAGE = re.compile(
    r"2026年上半年公司创新药销售收入[0-9]+(?:\.[0-9]+)?亿元，"
    r"同比(?P<direction>增长|下降)(?P<growth>[0-9]+(?:\.[0-9]+)?)%，"
    r"占药品销售收入的比重达(?P<share>[0-9]+(?:\.[0-9]+)?)%[。]"
)

_NUM = r"(?P<pct>[0-9]+(?:\.[0-9]+)?)"

_SHARE = re.compile(
    r"^innovative[- ]drug sales (?:were|represented|accounted for) "
    + _NUM
    + r"% of (?P<denom>drug sales revenue|total drug sales|"
    r"total consolidated company revenue|total company revenue|"
    r"consolidated revenue|company-wide revenue|overall company revenue)\.$"
)

_GROWTH = re.compile(
    r"^(?P<subject>innovative[- ]drug sales|total consolidated company revenue|"
    r"total company revenue|company-wide revenue|overall company revenue) "
    r"(?P<verb>grew|increased|declined|fell) "
    + _NUM
    + r"% (?:year over year|year-on-year)\.$"
)


def _result(claim_id, evidence_id, reason, reject=False):
    return SemanticScreenResult(
        claim_id=claim_id or "UNSPECIFIED_CLAIM",
        verdict=ScreenVerdict.REJECT if reject else ScreenVerdict.UNCERTAIN,
        reason=reason,
        compared_evidence_ids=(evidence_id,) if evidence_id else (),
        financial_semantic_review="NOT_QUALIFIED",
        research_publication="BLOCKED",
    )


def screen_management_narrative(
    *,
    claim_id: str,
    narrative: str,
    evidence_id: str,
    management: dict,
    document: SourceDocument,
    as_of: datetime,
) -> SemanticScreenResult:
    """Reject recognized source-claim substitutions; otherwise abstain.

    The caller must obtain management through locate_management_excerpt,
    not directly from Analyst output. Metadata equality is not itself
    independent source verification or financial certification.
    """
    if not isinstance(claim_id, str) or not isinstance(evidence_id, str):
        return _result("", "", "INVALID_CLAIM_BINDING")

    if not isinstance(document, SourceDocument) or not isinstance(as_of, datetime):
        return _result(claim_id, evidence_id, "SOURCE_OR_PIT_UNAVAILABLE")

    try:
        document.require_available(as_of)
    except (ValueError, TypeError):
        return _result(claim_id, evidence_id, "SOURCE_OR_PIT_UNAVAILABLE")

    if not isinstance(management, dict):
        return _result(claim_id, evidence_id, "UNQUALIFIED_SOURCE_PACKET")

    try:
        page = management["source_page"]
        passage = management["passage_whitespace_normalized"]

        valid = all((
            management["status"] == "SOURCE_PASSAGE_REVIEWED",
            management["review_scope"] == "NATIVE_PDF_TEXT_AND_WORD_LOCATION_ONLY",
            management["source_kind"] == "MANAGEMENT_DISCUSSION_PASSAGE",
            management["document_id"] == document.document_id,
            management["source_sha256"] == document.source_sha256,
            management["canonical_sha256"] == document.canonical_sha256,
            management["source_url"] == document.source_url,
            management["financial_semantic_review"] == "NOT_PERFORMED",
            management["research_publication"] == "BLOCKED",
            isinstance(page, int) and not isinstance(page, bool) and page >= 1,
            isinstance(passage, str) and len(passage) <= 250,
        ))

        if not valid:
            return _result(claim_id, evidence_id, "UNQUALIFIED_SOURCE_PACKET")

        expected_id = sha256("|".join((
            document.document_id,
            document.canonical_sha256,
            str(page),
            "management-innovation-sales-v1",
            passage,
        )).encode()).hexdigest()

        if evidence_id != management["evidence_id"] or evidence_id != expected_id:
            return _result(claim_id, evidence_id, "EVIDENCE_BINDING_NOT_VERIFIED")

    except (KeyError, TypeError, ValueError, AttributeError):
        return _result(claim_id, evidence_id, "UNQUALIFIED_SOURCE_PACKET")

    source = _PASSAGE.fullmatch(passage)
    if source is None:
        return _result(claim_id, evidence_id, "SOURCE_MEANING_NOT_PARSED")

    if not isinstance(narrative, str) or len(narrative) > 400:
        return _result(claim_id, evidence_id, "UNSTRUCTURED_NARRATIVE")

    text = unicodedata.normalize("NFKC", narrative).strip().casefold()
    text = " ".join(text.split())

    # Negations, quotations, questions, and hypotheticals are not
    # treated as unambiguous assertions.
    if any(c in text for c in ('?', '"', "'", ':', ';')) or re.search(
        r"\b(?:not|never|incorrect|wrong|might|could|if|whether|hypothetical|allegedly)\b",
        text,
    ):
        return _result(
            claim_id, evidence_id, "NARRATIVE_NOT_ASSERTED_UNAMBIGUOUSLY"
        )

    share = _SHARE.fullmatch(text)
    if share:
        same = Decimal(share["pct"]) == Decimal(source["share"])
        correct_denominator = share["denom"] in {
            "drug sales revenue", "total drug sales"
        }

        if same and not correct_denominator:
            return _result(
                claim_id, evidence_id,
                "SOURCE_SHARE_DENOMINATOR_SUBSTITUTED", True,
            )

        if not same and correct_denominator:
            return _result(
                claim_id, evidence_id,
                "SOURCE_SHARE_PERCENTAGE_MISMATCH", True,
            )

        return _result(
            claim_id, evidence_id,
            "SOURCE_SHARE_NOT_FINANCIALLY_QUALIFIED",
        )

    growth = _GROWTH.fullmatch(text)
    if growth:
        same = Decimal(growth["pct"]) == Decimal(source["growth"])

        if not same:
            return _result(
                claim_id, evidence_id,
                "GROWTH_PERCENTAGE_NOT_SOURCE_MATCHED",
            )

        claim_increases = growth["verb"] in {"grew", "increased"}
        source_increases = source["direction"] == "增长"

        if claim_increases != source_increases:
            return _result(
                claim_id, evidence_id,
                "SOURCE_GROWTH_DIRECTION_MISMATCH", True,
            )

        if growth["subject"] != "innovative-drug sales":
            return _result(
                claim_id, evidence_id,
                "SOURCE_GROWTH_METRIC_SUBSTITUTED", True,
            )

        return _result(
            claim_id, evidence_id,
            "SOURCE_GROWTH_NOT_FINANCIALLY_QUALIFIED",
        )

    return _result(
        claim_id, evidence_id,
        "NARRATIVE_NOT_WITHIN_BOUNDED_GRAMMAR",
    )
