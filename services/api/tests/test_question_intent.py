"""Synthetic question-contract tests, not semantic accuracy tests."""
import pytest
from pydantic import ValidationError

from app.modules.financial_report_analyst.question_intent import (
    QuestionIntentProposal,
    QuestionOperation,
)


def proposal(**overrides):
    data = {
        "question": "Synthetic company: how much revenue?",
        "operation_candidate": "LOOKUP",
        "metric_candidate": "revenue",
    }
    return QuestionIntentProposal.model_validate({
        **data,
        **overrides,
    })


def test_candidate_is_unverified_and_not_publishable():
    p = proposal()

    assert p.interpretation_status == "UNVERIFIED_PROPOSAL"
    assert p.financial_semantic_review == "NOT_PERFORMED"
    assert p.research_publication == "BLOCKED"
    assert len(p.question_sha256) == 64

    roundtrip = p.model_dump(
        exclude={"question_sha256"}
    )
    assert QuestionIntentProposal.model_validate(roundtrip) == p


def test_ratio_preserves_distinct_denominators():
    values = []

    for denominator in (
        "drug_sales",
        "consolidated_revenue",
    ):
        p = proposal(
            question="What is synthetic category sales share?",
            operation_candidate="RATIO",
            metric_candidate="category_sales_share",
            numerator_candidate="category_sales",
            denominator_candidate=denominator,
        )
        values.append(p.denominator_candidate)

    assert values[0] != values[1]


def test_missing_denominator_is_explicitly_unresolved():
    with pytest.raises(
        ValidationError,
        match="RATIO_DENOMINATOR_UNRESOLVED",
    ):
        proposal(
            operation_candidate="RATIO",
            denominator_candidate=None,
        )

    p = proposal(
        operation_candidate="RATIO",
        denominator_candidate=None,
        unresolved=("Which revenue denominator?",),
    )
    assert p.denominator_candidate is None


def test_unknown_operation_requires_reason():
    with pytest.raises(
        ValidationError,
        match="UNKNOWN_OPERATION_MUST_BE_EXPLICIT",
    ):
        proposal(operation_candidate="UNKNOWN")

    p = proposal(
        operation_candidate="UNKNOWN",
        unresolved=("Unsupported wording",),
    )

    assert p.operation_candidate is QuestionOperation.UNKNOWN


@pytest.mark.parametrize("data", [
    {"research_publication": "PUBLISHED"},
    {"financial_semantic_review": "APPROVED"},
    {"interpretation_status": "ADMIT"},
    {"external_evidence_id": "forged"},
    {"question": " \t "},
    {"operation_candidate": "RANDOM"},
    {"unresolved": ("",)},
])
def test_invalid_or_unsafe_proposals_rejected(data):
    with pytest.raises(ValidationError):
        proposal(**data)


def test_question_identity_is_bound_to_exact_text():
    first = proposal(question="Revenue for year A?")
    second = proposal(question="Revenue for year B?")

    assert first.question_sha256 != second.question_sha256

    with pytest.raises(ValidationError):
        QuestionIntentProposal.model_validate({
            **first.model_dump(),
            "question_sha256": "0" * 64,
        })
