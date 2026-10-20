from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import Field, model_validator

from app.evidence.contracts import StrictRecord


class FinancialObservation(StrictRecord):
    source_document_id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    metric_code: str = Field(min_length=1)
    reporting_entity: str = Field(min_length=1)
    category: str = Field(min_length=1)
    accounting_basis: str = Field(min_length=1)
    period_basis: str = Field(min_length=1)
    period_start: date
    period_end: date
    unit: str = Field(min_length=1)
    value: Decimal

    @model_validator(mode="after")
    def validate_period(self):
        if self.period_end < self.period_start:
            raise ValueError("INVALID_REPORTING_PERIOD")
        return self


COMPARABILITY_FIELDS = (
    "entity_id",
    "metric_code",
    "reporting_entity",
    "category",
    "accounting_basis",
    "period_basis",
    "unit",
)


def require_comparable(
    left: FinancialObservation,
    right: FinancialObservation,
) -> None:
    mismatches = [
        field
        for field in COMPARABILITY_FIELDS
        if getattr(left, field) != getattr(right, field)
    ]

    if mismatches:
        raise ValueError(
            "FINANCIAL_COMPARABILITY_MISMATCH: "
            + ", ".join(mismatches)
        )


class ClaimKind(StrEnum):
    OBSERVED_FACT = "OBSERVED_FACT"
    MANAGEMENT_EXPLANATION = "MANAGEMENT_EXPLANATION"
    ANALYST_INFERENCE = "ANALYST_INFERENCE"
    FORWARD_VIEW = "FORWARD_VIEW"


class ResearchClaim(StrictRecord):
    claim_id: str = Field(min_length=1)
    kind: ClaimKind
    text: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = ()
    supporting_claim_ids: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_trace(self):
        if self.kind in (
            ClaimKind.OBSERVED_FACT,
            ClaimKind.MANAGEMENT_EXPLANATION,
        ):
            if not self.evidence_ids:
                raise ValueError("FACT_REQUIRES_EVIDENCE")

        if self.kind in (
            ClaimKind.ANALYST_INFERENCE,
            ClaimKind.FORWARD_VIEW,
        ):
            if not self.supporting_claim_ids or not self.assumptions:
                raise ValueError("INFERENCE_REQUIRES_SUPPORT")

        return self


class ReviewVerdict(StrEnum):
    ADMIT = "ADMIT"
    REJECT = "REJECT"
    UNCERTAIN = "UNCERTAIN"


class ClaimReview(StrictRecord):
    claim_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)
    verdict: ReviewVerdict
    rationale: str = Field(min_length=1)
