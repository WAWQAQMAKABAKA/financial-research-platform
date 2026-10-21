"""Network-free M1.6B defensive screening; synthetic cases, not benchmark GT."""
from datetime import date
import pytest
from pydantic import ValidationError

from app.modules.financial_report_analyst.semantic_gate import (
    AssertionStructure as T, CandidateMetricIdentity as Identity,
    ScreenVerdict as V, SemanticClaimProposal as Proposal,
    SourceValueCandidate as Source, screen_financial_association as screen,
)


def identity(year=2026, **updates):
    values = dict(issuer_id="SYNTHETIC", metric_code="revenue_share",
                  reporting_scope="consolidated", category="innovative_products",
                  accounting_basis="management_discussion", period_basis="H1",
                  period_start=date(year, 1, 1), period_end=date(year, 6, 30), unit="percent")
    values.update(updates)
    return Identity(**values)


def source(i, *, year=2026, labels=True, **updates):
    values = dict(evidence_id=f"E{i}", document_id="SYNTHETIC-REPORT",
                  canonical_sha256="a" * 64,
                  statement_kind_candidate="consolidated_income_statement",
                  row_label_verbatim="一、营业收入",
                  column_header_verbatim=f"{year}年半年度",
                  value_verbatim=f"{i},234.56",
                  metric_identity_candidate=identity(year) if labels else None)
    values.update(updates)
    return Source(**values)


def proposal(*values, structure=T.PERIOD_COMPARISON, kind="OBSERVED_FACT", text=None):
    return Proposal(claim_id="CL1", claim_kind=kind, structure=structure,
                    values=tuple(values), unreviewed_text=text)


def test_plain_correct_observation_is_still_not_financially_admitted():
    a = source(1)
    r = screen(proposal(a, structure=T.SOURCE_OBSERVATION), (a,))
    assert r.verdict == V.UNCERTAIN
    assert r.financial_semantic_review == "NOT_QUALIFIED"
    assert r.research_publication == "BLOCKED"
    assert r.compared_evidence_ids == ("E1",)


@pytest.mark.parametrize("changed", [
    {"value_verbatim": "9,999.99"},
    {"row_label_verbatim": "二、净利润"},
    {"column_header_verbatim": "2025年半年度"},
    {"statement_kind_candidate": "parent_income_statement"},
    {"document_id": "OTHER-SOURCE"},
    {"canonical_sha256": "b"*64},
])
def test_source_association_substitution_is_rejected(changed):
    a = source(1)
    claimed = a.model_copy(update=changed)
    out = screen(proposal(claimed, structure=T.SOURCE_OBSERVATION), (a,))
    assert out.verdict == V.REJECT
    assert out.research_publication == "BLOCKED"


def test_model_relabels_correct_number_as_other_category_is_rejected():
    a = source(1)
    wrong = a.model_copy(update={"metric_identity_candidate": identity(category="generic_products")})
    result = screen(proposal(wrong, structure=T.SOURCE_OBSERVATION), (a,))
    assert result.verdict == V.REJECT
    assert result.reason == "SOURCE_METRIC_IDENTITY_ASSOCIATION_MISMATCH"


def test_model_cannot_invent_metric_identity_from_unqualified_anchor():
    a = source(1, labels=False)
    claim = a.model_copy(update={"metric_identity_candidate": identity()})
    out = screen(proposal(claim, structure=T.SOURCE_OBSERVATION), (a,))
    assert out.verdict == V.REJECT
    assert out.reason == "UNSUPPORTED_METRIC_IDENTITY_ASSERTION"


def test_model_claim_kind_observed_fact_does_not_bypass_invalid_comparison():
    a = source(1, year=2025, metric_identity_candidate=identity(year=2025, category="generic_products"))
    b = source(2, year=2026, metric_identity_candidate=identity(year=2026, category="innovative_products"))
    out = screen(proposal(a, b, kind="OBSERVED_FACT", text="The share increased year-over-year."), (a,b))
    assert out.verdict == V.REJECT
    assert out.reason == "COMPARISON_IDENTITY_MISMATCH:category"


@pytest.mark.parametrize("field,changed", [
    ("issuer_id", "OTHER"), ("metric_code", "gross_margin"),
    ("reporting_scope", "parent"), ("accounting_basis", "IFRS"),
    ("period_basis", "FY"), ("unit", "CNY"),
])
def test_incompatible_metric_dimensions_reject(field, changed):
    a = source(1, year=2025, metric_identity_candidate=identity(year=2025))
    b = source(2, year=2026, metric_identity_candidate=identity(year=2026, **{field: changed}))
    result = screen(proposal(a,b),(a,b))
    assert result.verdict == V.REJECT
    assert result.reason == f"COMPARISON_IDENTITY_MISMATCH:{field}"


def test_matching_period_comparison_still_requires_finance_review():
    a = source(1, year=2025, metric_identity_candidate=identity(year=2025))
    b = source(2, year=2026, metric_identity_candidate=identity(year=2026))
    out = screen(proposal(a, b), (a, b))
    assert out.verdict == V.UNCERTAIN
    assert out.reason == "COMPARISON_REQUIRES_INDEPENDENT_FINANCIAL_REVIEW"


def test_same_period_is_not_a_period_change():
    a = source(1)
    b = source(2)
    assert screen(proposal(a,b),(a,b)).reason == "COMPARISON_SAME_REPORTING_PERIOD"


def test_cross_statement_kind_is_rejected_as_period_change():
    a = source(1, year=2025)
    b = source(2, year=2026, statement_kind_candidate="parent_income_statement")
    out = screen(proposal(a,b),(a,b))
    assert out.verdict == V.REJECT
    assert out.reason == "COMPARISON_SOURCE_ASSOCIATION_MISMATCH:statement_kind_candidate"


def test_cross_document_is_uncertain_not_automatically_rejected():
    a, b = source(1,year=2025), source(2,year=2026,document_id="OTHER-REPORT")
    out = screen(proposal(a,b),(a,b))
    assert out.verdict == V.UNCERTAIN
    assert out.reason == "CROSS_DOCUMENT_COMPARISON_REQUIRES_REVIEW"


def test_unqualified_metric_fields_cannot_gain_semantic_approval():
    a = source(1,year=2025,labels=False)
    b = source(2,year=2026,labels=False)
    out = screen(proposal(a,b),(a,b))
    assert out.verdict == V.UNCERTAIN
    assert out.reason == "COMPARABILITY_IDENTITY_NOT_INDEPENDENTLY_QUALIFIED"


def test_row_label_change_is_uncertain_not_hardcoded_as_noncomparable():
    a = source(1,year=2025)
    b = source(2,year=2026,row_label_verbatim="其中：营业收入")
    out = screen(proposal(a,b),(a,b))
    assert out.verdict == V.UNCERTAIN
    assert out.reason == "COMPARISON_DIFFERENT_SOURCE_LABELS_REQUIRES_REVIEW"


def test_untyped_narrative_is_never_passed_through():
    a,b = source(1),source(2)
    for text in ("2026 increased over 2025", "revenue fell", "no changes were reported"):
        out = screen(proposal(a,b,structure=T.UNSPECIFIED,text=text),(a,b))
        assert out.verdict == V.UNCERTAIN
        assert out.reason == "UNSTRUCTURED_ASSERTION_NOT_REVIEWED"


def test_duplicate_source_packet_or_claim_fails_closed():
    a = source(1)
    assert screen(proposal(a,structure=T.SOURCE_OBSERVATION),(a,a)).verdict == V.UNCERTAIN
    out = screen(proposal(a,a),(a,))
    assert out.verdict == V.REJECT and out.reason == "DUPLICATE_ASSERTED_EVIDENCE"


def test_missing_source_reference_rejected():
    a = source(1)
    b = source(2)
    assert screen(proposal(b,structure=T.SOURCE_OBSERVATION),(a,)).reason == "UNKNOWN_SOURCE_EVIDENCE"


def test_wrong_value_count_is_rejected():
    a = source(1)
    assert screen(proposal(a,structure=T.PERIOD_COMPARISON),(a,)).reason == "ASSERTION_CARDINALITY_MISMATCH"


def test_invalid_dates_and_extra_untrusted_fields_not_accepted():
    with pytest.raises(ValidationError):
        identity(period_start=date(2026,7,1),period_end=date(2026,6,30))
    with pytest.raises(ValidationError):
        Source.model_validate({**source(1).model_dump(), "certified_semantics": True})
    with pytest.raises(ValidationError):
        Proposal.model_validate({**proposal(source(1),structure=T.SOURCE_OBSERVATION).model_dump(),
                                "publish": True})


def test_mutating_both_self_reported_labels_cannot_create_admission():
    # This gate cannot independently prove source metadata is true; equal
    # forged labels never generate ADMIT. Separate source reviewer still needed.
    fake = source(1, metric_identity_candidate=identity(category="fictional"))
    result = screen(proposal(fake,structure=T.SOURCE_OBSERVATION),(fake,))
    assert result.verdict == V.UNCERTAIN
    assert result.financial_semantic_review == "NOT_QUALIFIED"
