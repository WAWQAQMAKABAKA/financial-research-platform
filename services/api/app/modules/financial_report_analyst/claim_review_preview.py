"""M1.9C: local source-bound claim review, never publication.

Four bounded financial claim formulations. Values are parsed from a
hash-verified, PIT-available original-PDF management passage.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal

from app.modules.financial_report_analyst import (
    management_evidence,
    revenue_scope,
)
from app.modules.financial_report_analyst.management_semantic_screen import (
    _PASSAGE,
    screen_management_narrative,
)

ClaimCode = Literal[
    "share_drug_sales",
    "share_company_revenue",
    "growth_innovative_drugs",
    "growth_company_revenue",
]


def build_preview(
    pdf_path: Path,
    claim_code: ClaimCode,
    *,
    as_of: datetime,
) -> dict:
    """Recheck original PDF and PIT before reviewing a selected claim."""
    templates = {
        "share_drug_sales":
            "Innovative-drug sales were {share}% of drug sales revenue.",
        "share_company_revenue":
            "Innovative-drug sales were {share}% of total consolidated company revenue.",
        "growth_innovative_drugs":
            "Innovative-drug sales grew {growth}% year over year.",
        "growth_company_revenue":
            "Total consolidated company revenue grew {growth}% year over year.",
    }

    if claim_code not in templates:
        raise ValueError("UNSUPPORTED_CLAIM_CODE")

    # This locator checks original PDF SHA, native text location and PIT.
    # Analyst/model output must not populate the source packet.
    management = management_evidence.locate_management_excerpt(
        pdf_path,
        as_of=as_of,
    )
    source = revenue_scope.SOURCE

    match = _PASSAGE.fullmatch(
        management["passage_whitespace_normalized"]
    )
    if match is None or match["direction"] != "增长":
        raise ValueError("MANAGEMENT_SOURCE_NOT_WITHIN_PREVIEW_SCOPE")

    claim_text = templates[claim_code].format(
        share=match["share"],
        growth=match["growth"],
    )

    review = screen_management_narrative(
        claim_id="C1",
        narrative=claim_text,
        evidence_id=management["evidence_id"],
        management=management,
        document=source,
        as_of=as_of,
    )

    # If a later Reviewer change alters the supported behavior, withhold
    # this preview. The frozen offline evaluation remains independent.
    expected = {
        "share_drug_sales": (
            "UNCERTAIN",
            "SOURCE_SHARE_NOT_FINANCIALLY_QUALIFIED",
        ),
        "share_company_revenue": (
            "REJECT",
            "SOURCE_SHARE_DENOMINATOR_SUBSTITUTED",
        ),
        "growth_innovative_drugs": (
            "UNCERTAIN",
            "SOURCE_GROWTH_NOT_FINANCIALLY_QUALIFIED",
        ),
        "growth_company_revenue": (
            "REJECT",
            "SOURCE_GROWTH_METRIC_SUBSTITUTED",
        ),
    }

    if (
        (review.verdict.value, review.reason) != expected[claim_code]
        or review.compared_evidence_ids != (management["evidence_id"],)
        or review.financial_semantic_review != "NOT_QUALIFIED"
        or review.research_publication != "BLOCKED"
    ):
        raise ValueError("REVIEW_BOUNDARY_FAILED")

    identity = "|".join((
        source.document_id,
        source.canonical_sha256,
        management["evidence_id"],
        claim_code,
        claim_text,
        "m19c-v1",
    ))

    return {
        "status": "LOCAL_CLAIM_REVIEW_READY",
        "report_key": "600276-2026H1",
        "claim_code": claim_code,
        "claim_id": "C1",
        "claim_text": claim_text,
        "review": {
            "claim_id": review.claim_id,
            "verdict": review.verdict.value,
            "reason": review.reason,
            "compared_evidence_ids": list(review.compared_evidence_ids),
        },
        "evidence": {
            "evidence_id": management["evidence_id"],
            "page": management["source_page"],
            "excerpt": management["passage_whitespace_normalized"],
            "review_scope": management["review_scope"],
        },
        "document_id": source.document_id,
        "source_url": source.source_url,
        "source_sha256": source.source_sha256,
        "canonical_sha256": source.canonical_sha256,
        "preview_id": sha256(identity.encode()).hexdigest(),
        "financial_semantic_review": "NOT_QUALIFIED",
        "research_publication": "BLOCKED",
        "limitation": (
            "Bounded contradiction screen, not financial-semantic approval."
        ),
    }
