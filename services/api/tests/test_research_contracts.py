from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.evidence.contracts import (
    EvidenceSpan,
    SourceDocument,
    require_claim_evidence,
    require_evidence_binding,
)
from app.modules.financial_report_analyst.contracts import (
    ClaimKind,
    FinancialObservation,
    ResearchClaim,
    ReviewVerdict,
    ClaimReview,
    require_comparable,
)


CN = ZoneInfo("Asia/Shanghai")


def source() -> SourceDocument:
    return SourceDocument(
        document_id="SYNTHETIC-DOC-01",
        ticker="TEST",
        report_period="2026H1",
        source_url="https://example.org/test.pdf",
        published_on=date(2026, 8, 28),
        source_sha256="a" * 64,
        canonical_sha256="b" * 64,
    )


def evidence() -> EvidenceSpan:
    return EvidenceSpan(
        evidence_id="E1",
        document_id="SYNTHETIC-DOC-01",
        canonical_sha256="b" * 64,
        page_number=3,
        canonical_start=100,
        canonical_end=150,
        excerpt="Synthetic example text.",
    )


def observation(
    category: str = "innovative_drugs",
    year: int = 2026,
) -> FinancialObservation:
    return FinancialObservation(
        source_document_id=f"SYNTHETIC-{year}",
        evidence_id="E1",
        entity_id="TEST",
        metric_code="revenue_share",
        reporting_entity="consolidated",
        category=category,
        accounting_basis="management_discussion",
        period_basis="H1",
        period_start=date(year, 1, 1),
        period_end=date(year, 6, 30),
        unit="percent",
        value=Decimal("63.16"),
    )


def test_pit_rejects_publication_day() -> None:
    with pytest.raises(ValueError, match="PIT_UNAVAILABLE"):
        source().require_available(
            datetime(2026, 8, 28, 23, 59, tzinfo=CN)
        )


def test_pit_accepts_next_calendar_day() -> None:
    source().require_available(
        datetime(2026, 8, 29, 0, 0, tzinfo=CN)
    )


def test_pit_requires_timezone() -> None:
    with pytest.raises(ValueError, match="PIT_AS_OF"):
        source().require_available(datetime(2026, 8, 29))


def test_source_hash_is_required() -> None:
    with pytest.raises(ValidationError):
        SourceDocument.model_validate({
            **source().model_dump(),
            "source_sha256": "not-a-sha256",
        })


def test_evidence_rejects_wrong_canonical_hash() -> None:
    bad = evidence().model_copy(
        update={"canonical_sha256": "c" * 64}
    )

    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        require_evidence_binding(
            source(),
            bad,
            datetime(2026, 8, 29, tzinfo=CN),
        )


def test_claim_rejects_unknown_evidence_id() -> None:
    with pytest.raises(ValueError, match="UNKNOWN_EVIDENCE_ID"):
        require_claim_evidence(
            source(),
            [evidence()],
            ["E2"],
            datetime(2026, 8, 29, tzinfo=CN),
        )


def test_comparable_periods_can_differ_by_year() -> None:
    require_comparable(
        observation(year=2025),
        observation(year=2026),
    )


def test_cross_category_comparison_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="FINANCIAL_COMPARABILITY_MISMATCH: category",
    ):
        require_comparable(
            observation(category="generic_drugs", year=2025),
            observation(category="innovative_drugs", year=2026),
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("metric_code", "operating_margin"),
        ("accounting_basis", "segment_note"),
        ("period_basis", "FY"),
        ("unit", "CNY"),
        ("reporting_entity", "parent_company"),
    ],
)
def test_other_incompatible_comparisons(
    field: str,
    value: str,
) -> None:
    other = observation().model_copy(update={field: value})

    with pytest.raises(ValueError, match=field):
        require_comparable(observation(), other)


def test_fact_requires_evidence() -> None:
    with pytest.raises(ValidationError, match="FACT_REQUIRES_EVIDENCE"):
        ResearchClaim(
            claim_id="C1",
            kind=ClaimKind.OBSERVED_FACT,
            text="Synthetic factual claim.",
        )


def test_inference_requires_support_and_assumptions() -> None:
    with pytest.raises(ValidationError, match="INFERENCE_REQUIRES_SUPPORT"):
        ResearchClaim(
            claim_id="C2",
            kind=ClaimKind.ANALYST_INFERENCE,
            text="Synthetic inference.",
        )


def test_review_can_explicitly_record_uncertainty() -> None:
    review = ClaimReview(
        claim_id="C1",
        reviewer_id="reviewer-01",
        verdict=ReviewVerdict.UNCERTAIN,
        rationale="Insufficient evidence for semantic approval.",
    )

    assert review.verdict == ReviewVerdict.UNCERTAIN
