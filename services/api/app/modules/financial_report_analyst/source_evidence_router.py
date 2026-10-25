"""M121: server-owned routing from a verified source report to cited evidence.

Consumes ONLY a report returned by source_report_preview.build_source_report;
never uses model-authored source IDs, performs arithmetic, or approves claims.
This first catalog is intentionally limited to one verified disclosure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.financial_report_analyst import revenue_scope

REPORT_KEY = "600276-2026H1"
SHA = re.compile(r"[a-f0-9]{64}\Z")
AMOUNT = re.compile(r"[0-9][0-9,]*\.[0-9]{2}\Z")
MANAGEMENT = re.compile(
    r"2026年上半年公司创新药销售收入[0-9]+(?:\.[0-9]+)?亿元，"
    r"同比(?:增长|下降)[0-9]+(?:\.[0-9]+)?%，"
    r"占药品销售收入的比重达(?P<share>[0-9]+(?:\.[0-9]+)?)%[。]\Z"
)


@dataclass(frozen=True)
class RouteSpec:
    answer_kind: str
    evidence_kind: str
    claim_id: str


# Extending this catalog requires a separately qualified source builder.
# No fallback to arbitrary rows, nearest text, or model-supplied evidence IDs.
CATALOG = {
    "CONSOLIDATED_REVENUE": RouteSpec(
        "CONSOLIDATED_REVENUE", "FINANCIAL_STATEMENT_CELL", "REV1",
    ),
    "INNOVATIVE_SHARE_OF_DRUG_SALES": RouteSpec(
        "INNOVATIVE_SHARE_OF_DRUG_SALES", "ATTRIBUTED_MANAGEMENT_SHARE", "M1",
    ),
}


def _norm(value: str) -> str:
    return "".join(value.split())


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("SOURCE_EVIDENCE_ROUTE_NOT_QUALIFIED")


def route_evidence(report: dict, answer_kind: str) -> dict:
    """Bind a prequalified source report to one supported evidence selector.

    This is source routing, not independent financial-semantic review. Caller
    must independently reconstruct the verified source packet from the PDF.
    """
    spec = CATALOG.get(answer_kind)
    _require(spec is not None and isinstance(report, dict))
    source = revenue_scope.SOURCE
    _require(all((
        report.get("status") == "LOCAL_SOURCE_REPORT_READY",
        report.get("report_type") == "UNPUBLISHED_SOURCE_REPORT_PREVIEW",
        report.get("report_key") == REPORT_KEY,
        report.get("report_storage") == "NOT_PERSISTED",
        report.get("document_id") == source.document_id,
        report.get("source_url") == source.source_url,
        report.get("source_sha256") == source.source_sha256,
        report.get("canonical_sha256") == source.canonical_sha256,
        report.get("report_period") == source.report_period,
        report.get("financial_semantic_review") == "NOT_PERFORMED",
        report.get("research_publication") == "BLOCKED",
        isinstance(report.get("report_identity"), str),
    )))
    _require(bool(SHA.fullmatch(report["report_identity"])))

    if spec.evidence_kind == "FINANCIAL_STATEMENT_CELL":
        observations = report.get("observations")
        _require(isinstance(observations, list))
        matches = [
            o for o in observations
            if isinstance(o, dict) and o.get("claim_id") == spec.claim_id
        ]
        _require(len(matches) == 1)
        evidence = matches[0]
        value = evidence.get("value_verbatim")
        _require(all((
            evidence.get("kind") == "SOURCE_LITERAL_OBSERVATION",
            evidence.get("review_result") == "SOURCE_LOCATION_VERIFIED_ONLY",
            evidence.get("review_scope") == "LITERAL_CELL_LOCATION_ONLY",
            _norm(str(evidence.get("statement_title", ""))) == "合并利润表",
            _norm(str(evidence.get("row_label", ""))) == "其中:营业收入"
                or _norm(str(evidence.get("row_label", ""))) == "其中：营业收入",
            _norm(str(evidence.get("column_header", ""))) == "2026年半年度",
            isinstance(value, str),
        )))
        _require(bool(AMOUNT.fullmatch(value)))
        excerpt = value
        denominator = None
    else:
        evidence = report.get("management_statement")
        _require(isinstance(evidence, dict))
        excerpt = evidence.get("text")
        _require(all((
            evidence.get("claim_id") == spec.claim_id,
            evidence.get("kind") == "ATTRIBUTED_MANAGEMENT_STATEMENT",
            evidence.get("review_result") == "SOURCE_PASSAGE_LOCATED_ONLY",
            evidence.get("review_scope") == "NATIVE_PDF_TEXT_AND_WORD_LOCATION_ONLY",
            isinstance(excerpt, str),
        )))
        match = MANAGEMENT.fullmatch(excerpt)
        _require(match is not None)
        value = f"{match['share']}%"
        denominator = "药品销售收入"

    page = evidence.get("page")
    evidence_id = evidence.get("evidence_id")
    _require(all((
        isinstance(page, int) and not isinstance(page, bool) and page > 0,
        isinstance(evidence_id, str),
    )))
    _require(bool(SHA.fullmatch(evidence_id)))
    _require(evidence.get("claim_id") == spec.claim_id)

    return {
        "status": "ROUTED_SOURCE_EVIDENCE_READY",
        "answer_kind": spec.answer_kind,
        "evidence_kind": spec.evidence_kind,
        "claim_id": spec.claim_id,
        "evidence_id": evidence_id,
        "source_page": page,
        "source_excerpt": excerpt,
        "value_verbatim": value,
        "denominator_label": denominator,
        "review_scope": evidence["review_scope"],
        "report_key": REPORT_KEY,
        "source_report_identity": report["report_identity"],
        "document_id": source.document_id,
        "source_url": source.source_url,
        "source_sha256": source.source_sha256,
        "canonical_sha256": source.canonical_sha256,
        "routing_review_scope": "SOURCE_BINDING_ONLY",
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
    }
