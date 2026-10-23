"""M1.10A: one free-text Analyst candidate, independently source-bound.

One pinned management passage only. The caller supplies draft text, never the
source packet or reviewer verdict. Not a general financial semantics model.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path

from app.modules.financial_report_analyst import management_evidence, revenue_scope
from app.modules.financial_report_analyst.contracts import ClaimKind, ResearchClaim
from app.modules.financial_report_analyst.management_semantic_screen import (
    _PASSAGE,
    screen_management_narrative,
)

REVIEW_VERSION = "m110a-source-bound-manual-analyst-draft-v1"


def review_analyst_draft(
    pdf_path: Path,
    candidate_text: str,
    *,
    as_of: datetime,
) -> dict:
    """Return a withheld-from-publication claim/review/evidence record.

    An incorrect draft is displayed ONLY alongside its verdict and source.
    A missing/unqualified source withholds the entire draft result.
    """
    if (
        not isinstance(candidate_text, str)
        or not candidate_text.strip()
        or len(candidate_text) > 400
        or len(candidate_text.encode("utf-8")) > 1200
    ):
        raise ValueError("INVALID_ANALYST_CANDIDATE")

    # Source of truth is built separately from candidate content. This locator
    # requires full original-PDF SHA, independent native word/text agreement,
    # a unique section-anchored passage and conservative PIT availability.
    management = management_evidence.locate_management_excerpt(
        pdf_path, as_of=as_of,
    )
    source = revenue_scope.SOURCE
    if (
        management.get("document_id") != source.document_id
        or management.get("source_sha256") != source.source_sha256
        or management.get("canonical_sha256") != source.canonical_sha256
        or management.get("source_url") != source.source_url
        or management.get("status") != "SOURCE_PASSAGE_REVIEWED"
        or management.get("review_scope") != "NATIVE_PDF_TEXT_AND_WORD_LOCATION_ONLY"
        or management.get("research_publication") != "BLOCKED"
        or management.get("financial_semantic_review") != "NOT_PERFORMED"
        or not isinstance(management.get("evidence_id"), str)
        or _PASSAGE.fullmatch(management.get("passage_whitespace_normalized", "")) is None
    ):
        raise ValueError("SOURCE_NOT_QUALIFIED")

    # The selected source is server-bound. The Analyst supplies text only;
    # it cannot manufacture evidence, declare source facts, or write a verdict.
    claim = ResearchClaim(
        claim_id="MC1",
        kind=ClaimKind.OBSERVED_FACT,
        text=candidate_text,
        evidence_ids=(management["evidence_id"],),
    )
    review = screen_management_narrative(
        claim_id=claim.claim_id,
        narrative=claim.text,
        evidence_id=claim.evidence_ids[0],
        management=management,
        document=source,
        as_of=as_of,
    )
    # A structural/provenance failure is not a normal semantic abstention.
    if (
        review.reason in {
            "SOURCE_OR_PIT_UNAVAILABLE", "UNQUALIFIED_SOURCE_PACKET",
            "EVIDENCE_BINDING_NOT_VERIFIED", "SOURCE_MEANING_NOT_PARSED",
        }
        or review.compared_evidence_ids != claim.evidence_ids
        or review.verdict.value not in {"REJECT", "UNCERTAIN"}
        or review.research_publication != "BLOCKED"
        or review.financial_semantic_review != "NOT_QUALIFIED"
    ):
        raise ValueError("REVIEW_SOURCE_BINDING_FAILED")

    review_id = sha256("|".join((
        source.document_id, source.canonical_sha256,
        management["evidence_id"], claim.claim_id, claim.text,
        as_of.isoformat(), REVIEW_VERSION,
    )).encode("utf-8")).hexdigest()

    return {
        "status": "UNPUBLISHED_ANALYST_CANDIDATE_REVIEWED",
        "report_key": "600276-2026H1",
        "review_id": review_id,
        "as_of": as_of.isoformat(),
        "draft_origin": "MANUAL_ANALYST_DRAFT",
        "claim": {
            "claim_id": claim.claim_id,
            "kind": claim.kind.value,
            "text": claim.text,
            "evidence_ids": list(claim.evidence_ids),
        },
        "review": {
            "claim_id": review.claim_id,
            "verdict": review.verdict.value,
            "reason": review.reason,
            "compared_evidence_ids": list(review.compared_evidence_ids),
            "review_scope": "BOUNDED_NARRATIVE_CONTRADICTION_ONLY",
        },
        "evidence": {
            "evidence_id": management["evidence_id"],
            "source_page": management["source_page"],
            "excerpt": management["passage_whitespace_normalized"],
            "review_scope": management["review_scope"],
        },
        "document_id": source.document_id,
        "source_url": source.source_url,
        "source_sha256": source.source_sha256,
        "canonical_sha256": source.canonical_sha256,
        "financial_semantic_review": "NOT_QUALIFIED",
        "research_publication": "BLOCKED",
        "limitation": (
            "Manual candidate only; one server-selected evidence passage. "
            "Unrecognized language stays UNCERTAIN. No financial-semantic "
            "approval or customer publication."
        ),
    }
