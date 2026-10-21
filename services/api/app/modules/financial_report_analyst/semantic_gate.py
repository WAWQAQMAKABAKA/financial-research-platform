"""M1.6B-1 defensive structural financial-association screen.

Rejects demonstrable mismatches to *separately supplied* source-bound candidates.
Neither candidate metadata nor a matching string is proof of financial meaning.
This module CANNOT return ADMIT or authorize publication. No model, network,
real-document benchmark reference answers, or trading dependencies.
"""
from __future__ import annotations

from datetime import date
from enum import StrEnum
import re
import unicodedata

from pydantic import Field, model_validator

from app.evidence.contracts import StrictRecord


class AssertionStructure(StrEnum):
    SOURCE_OBSERVATION = "SOURCE_OBSERVATION"
    PERIOD_COMPARISON = "PERIOD_COMPARISON"
    UNSPECIFIED = "UNSPECIFIED"


class ScreenVerdict(StrEnum):
    REJECT = "REJECT"
    UNCERTAIN = "UNCERTAIN"


class CandidateMetricIdentity(StrictRecord):
    """Unqualified candidate labels, NOT independent accounting certification."""
    issuer_id: str = Field(min_length=1)
    metric_code: str = Field(min_length=1)
    reporting_scope: str = Field(min_length=1)
    category: str = Field(min_length=1)
    accounting_basis: str = Field(min_length=1)
    period_basis: str = Field(min_length=1)
    period_start: date
    period_end: date
    unit: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_period(self):
        if self.period_start > self.period_end:
            raise ValueError("INVALID_CANDIDATE_PERIOD")
        return self


class SourceValueCandidate(StrictRecord):
    """Association from an independently built source packet; source trust is external.

    Supplying a serialized object alone DOES NOT prove a PDF or its meaning.
    """
    evidence_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    canonical_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    statement_kind_candidate: str = Field(min_length=1)
    row_label_verbatim: str = Field(min_length=1)
    column_header_verbatim: str = Field(min_length=1)
    value_verbatim: str = Field(min_length=1)
    metric_identity_candidate: CandidateMetricIdentity | None = None


class SemanticClaimProposal(StrictRecord):
    """A typed claim proposal. A text paragraph alone never counts as reviewed."""
    claim_id: str = Field(min_length=1)
    claim_kind: str = Field(min_length=1)  # never trusted as a screen bypass
    structure: AssertionStructure
    values: tuple[SourceValueCandidate, ...] = ()
    unreviewed_text: str | None = None


class SemanticScreenResult(StrictRecord):
    claim_id: str
    verdict: ScreenVerdict
    reason: str
    compared_evidence_ids: tuple[str, ...]
    financial_semantic_review: str = "NOT_QUALIFIED"
    research_publication: str = "BLOCKED"


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def _result(proposal: SemanticClaimProposal, verdict: ScreenVerdict, reason: str) -> SemanticScreenResult:
    return SemanticScreenResult(
        claim_id=proposal.claim_id, verdict=verdict, reason=reason,
        compared_evidence_ids=tuple(v.evidence_id for v in proposal.values),
    )


def screen_financial_association(
    proposal: SemanticClaimProposal,
    source_candidates: tuple[SourceValueCandidate, ...],
) -> SemanticScreenResult:
    """Fail closed. Only contradiction detection; never a financial-meaning ADMIT.

    `source_candidates` MUST be built separately from a source-hash/PIT-verified
    extraction + independent literal check. Model output must never populate
    both `proposal` and the source of truth. Even then metric identity labels
    are candidates, NOT finance-semantic proof.
    """
    if not source_candidates or len({v.evidence_id for v in source_candidates}) != len(source_candidates):
        return _result(proposal, ScreenVerdict.UNCERTAIN, "SOURCE_PACKET_MISSING_OR_AMBIGUOUS")
    by_id = {v.evidence_id: v for v in source_candidates}
    if proposal.structure == AssertionStructure.UNSPECIFIED or not proposal.values:
        return _result(proposal, ScreenVerdict.UNCERTAIN, "UNSTRUCTURED_ASSERTION_NOT_REVIEWED")
    needed = 1 if proposal.structure == AssertionStructure.SOURCE_OBSERVATION else 2
    if len(proposal.values) != needed:
        return _result(proposal, ScreenVerdict.REJECT, "ASSERTION_CARDINALITY_MISMATCH")
    if len({v.evidence_id for v in proposal.values}) != needed:
        return _result(proposal, ScreenVerdict.REJECT, "DUPLICATE_ASSERTED_EVIDENCE")

    for claimed in proposal.values:
        anchor = by_id.get(claimed.evidence_id)
        if anchor is None:
            return _result(proposal, ScreenVerdict.REJECT, "UNKNOWN_SOURCE_EVIDENCE")
        for key in ("document_id", "canonical_sha256", "statement_kind_candidate",
                    "row_label_verbatim", "column_header_verbatim", "value_verbatim"):
            # Values and source identity require exact agreement. Source row/
            # header spacing is display-only, not an accounting interpretation.
            left, right = getattr(claimed, key), getattr(anchor, key)
            equal = (_norm(left) == _norm(right)) if key in (
                "row_label_verbatim", "column_header_verbatim"
            ) else left == right
            if not equal:
                return _result(proposal, ScreenVerdict.REJECT, f"SOURCE_BINDING_MISMATCH:{key}")
        # Model-provided semantic labels never override source-side labels.
        if anchor.metric_identity_candidate is None and claimed.metric_identity_candidate is not None:
            return _result(proposal, ScreenVerdict.REJECT, "UNSUPPORTED_METRIC_IDENTITY_ASSERTION")
        if anchor.metric_identity_candidate is not None and claimed.metric_identity_candidate != anchor.metric_identity_candidate:
            return _result(proposal, ScreenVerdict.REJECT, "SOURCE_METRIC_IDENTITY_ASSOCIATION_MISMATCH")

    if proposal.structure == AssertionStructure.SOURCE_OBSERVATION:
        return _result(proposal, ScreenVerdict.UNCERTAIN, "SOURCE_FACT_FINANCIAL_MEANING_NOT_QUALIFIED")

    a, b = (by_id[v.evidence_id] for v in proposal.values)
    # These are concrete source association differences; do not treat the
    # two values as a time-series even if a model calls them OBSERVED_FACT.
    if a.document_id != b.document_id:
        # A legitimate comparison might span two disclosures. No automatic
        # rejection solely due to different source documents.
        return _result(proposal, ScreenVerdict.UNCERTAIN, "CROSS_DOCUMENT_COMPARISON_REQUIRES_REVIEW")
    if _norm(a.statement_kind_candidate) != _norm(b.statement_kind_candidate):
        return _result(proposal, ScreenVerdict.REJECT,
                       "COMPARISON_SOURCE_ASSOCIATION_MISMATCH:statement_kind_candidate")
    if _norm(a.row_label_verbatim) != _norm(b.row_label_verbatim):
        return _result(proposal, ScreenVerdict.UNCERTAIN,
                       "COMPARISON_DIFFERENT_SOURCE_LABELS_REQUIRES_REVIEW")
    if a.metric_identity_candidate is None or b.metric_identity_candidate is None:
        return _result(proposal, ScreenVerdict.UNCERTAIN, "COMPARABILITY_IDENTITY_NOT_INDEPENDENTLY_QUALIFIED")
    ai, bi = a.metric_identity_candidate, b.metric_identity_candidate
    for key in ("issuer_id", "metric_code", "reporting_scope", "category",
                "accounting_basis", "period_basis", "unit"):
        if getattr(ai, key) != getattr(bi, key):
            return _result(proposal, ScreenVerdict.REJECT, f"COMPARISON_IDENTITY_MISMATCH:{key}")
    if ai.period_start == bi.period_start and ai.period_end == bi.period_end:
        return _result(proposal, ScreenVerdict.REJECT, "COMPARISON_SAME_REPORTING_PERIOD")
    # Equal dimensions still do not prove metric identity, period semantics,
    # numerator/denominator, causality, math, or valid narrative direction.
    return _result(proposal, ScreenVerdict.UNCERTAIN, "COMPARISON_REQUIRES_INDEPENDENT_FINANCIAL_REVIEW")
