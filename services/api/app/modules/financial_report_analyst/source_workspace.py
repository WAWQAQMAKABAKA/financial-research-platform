"""M1.7A two-issuer source-only consolidated revenue workspace.

Issuer selection is an allowlisted local-development source manifest, never a
free-form filesystem path. Both reports use one index/attribution/review path.
Literal source checks are not financial-semantic qualification or publication.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path

import pymupdf

from app.evidence import preview
from app.evidence.cell_attribution import locate_cells_in_verified_pdf
from app.evidence.contracts import SourceDocument
from app.modules.financial_report_analyst import revenue_scope


@dataclass(frozen=True)
class ReportEntry:
    key: str
    issuer_name: str
    source: SourceDocument
    pdf_env_name: str
    section_kind: str
    row_label: str
    column_header: str


# Source metadata is defined once in earlier, independently hash-verified
# reports; no duplicated real-document amounts or expected page coordinates.
# Only the query selection changes, not the extraction/reviewer implementation.
REPORTS: dict[str, ReportEntry] = {
    "600276-2026H1": ReportEntry(
        key="600276-2026H1", issuer_name="恒瑞医药", source=revenue_scope.SOURCE,
        pdf_env_name="FRP_LOCAL_SOURCE_PDF_600276",
        section_kind="consolidated_income_statement",
        row_label="其中：营业收入", column_header="2026 年半年度",
    ),
    "600760-2026H1": ReportEntry(
        key="600760-2026H1", issuer_name="中航沈飞", source=preview.SOURCE,
        pdf_env_name="FRP_LOCAL_SOURCE_PDF_600760",
        section_kind="consolidated_income_statement",
        row_label="其中：营业收入", column_header="2026 年半年度",
    ),
}


class UnknownReportError(ValueError):
    """Not present in the fixed local report catalog."""


def _withheld(reason: str) -> dict:
    return {
        "status": "WITHHELD", "reason": reason, "observations": [],
        "claims": [], "reviews": [], "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
    }


def build_source_workspace(report_key: str, pdf_path: Path, *, as_of: datetime) -> dict:
    """Build one literal observed cell; no comparison, LLM, or publication.

    A trusted caller selects `report_key` from REPORTS and supplies the
    associated hash-pinned source PDF. Errors on missing/mismatched files fail
    closed at the API boundary; unresolved cells yield WITHHELD, no values.
    """
    entry = REPORTS.get(report_key)
    if entry is None:
        raise UnknownReportError("REPORT_NOT_ALLOWLISTED")
    source = entry.source
    source.require_available(as_of)
    selections = [{
        "section_kind": entry.section_kind,
        "row_label": entry.row_label,
        "column_header": entry.column_header,
    }]
    matches = locate_cells_in_verified_pdf(
        source, pdf_path, as_of=as_of, selections=selections,
    )
    if len(matches) != 1 or matches[0].get("status") != "ONE_CELL_CANDIDATE":
        return _withheld("SOURCE_CELL_UNRESOLVED")
    choices = matches[0].get("candidates")
    if not isinstance(choices, list) or len(choices) != 1:
        return _withheld("SOURCE_CELL_AMBIGUOUS")
    item = choices[0]
    if not isinstance(item, dict):
        return _withheld("SOURCE_CELL_INVALID")
    if (
        item.get("document_id") != source.document_id
        or item.get("source_sha256") != source.source_sha256
        or item.get("canonical_sha256") != source.canonical_sha256
        or item.get("source_url") != source.source_url
        or item.get("section_kind_candidate") != entry.section_kind
        or revenue_scope._norm(item.get("row_label_verbatim", "")) != revenue_scope._norm(entry.row_label)
        or revenue_scope._norm(item.get("column_header_verbatim", "")) != revenue_scope._norm(entry.column_header)
        or item.get("source_text_span_status") != "NOT_PROVEN_FROM_TABLE_GEOMETRY"
        or item.get("accounting_scope_status") != "HEADING_CANDIDATE_ONLY"
        or item.get("column_meaning_status") != "HEADER_TEXT_ONLY"
        or item.get("review_status") != "REVIEW_REQUIRED"
    ):
        return _withheld("SOURCE_CELL_IDENTITY_MISMATCH")
    # Independent native-PDF text/geometry check. The existing reviewer is
    # intentionally limited to the 2026 H1 CNY source-statement vocabulary.
    with pymupdf.open(pdf_path) as pdf:
        accepted, rationale = revenue_scope.review_literal(item, pdf)
    if not accepted:
        return _withheld("LITERAL_REVIEW_NOT_PASSED")
    source_id = sha256((
        source.document_id + "|" + source.canonical_sha256 +
        "|consolidated-source-workspace-v1"
    ).encode()).hexdigest()
    claim_id = "SRC1"
    observation = {
        "claim_id": claim_id,
        "evidence_id": item["candidate_id"],
        "statement_type_candidate": item["section_kind_candidate"],
        "statement_title": item["statement_heading_verbatim"],
        "row_label": item["row_label_verbatim"],
        "column_header": item["column_header_verbatim"],
        "value_verbatim": item["cell_text_verbatim"],
        "statement_context": item["statement_context_verbatim"],
        "page_number": item["page_number"],
        "table_index": item["table_index"],
        "row_index": item["row_index"],
        "column_index": item["column_index"],
        "cell_bbox_pt": item["cell_bbox_pt"],
        "source_text_span_status": item["source_text_span_status"],
        "review_scope": "LITERAL_CELL_LOCATION_ONLY",
    }
    return {
        "status": "SOURCE_DRAFT_READY", "report_key": entry.key,
        "report_id": source_id, "issuer_name": entry.issuer_name,
        "document_id": source.document_id, "ticker": source.ticker,
        "report_period": source.report_period,
        "source_url": source.source_url,
        "source_sha256": source.source_sha256,
        "canonical_sha256": source.canonical_sha256,
        "observations": [observation],
        "claims": [{"claim_id": claim_id, "kind": "OBSERVED_FACT",
                    "evidence_ids": [item["candidate_id"]]}],
        "reviews": [{"claim_id": claim_id, "verdict": "ADMIT",
                     "rationale": rationale, "reviewer_id": "native-pdf-cell-literal-reviewer-v1"}],
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
        "limitation": (
            "One hash-verified consolidated-income-statement cell was located and "
            "checked against the native PDF text. Scope, period and unit are "
            "source text only, not independently qualified financial semantics. "
            "No comparison, inference or research publication is approved."
        ),
    }
