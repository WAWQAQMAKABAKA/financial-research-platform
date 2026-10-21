"""Local-only two-scope revenue source preview; never a published report.

Uses source-verified whole-document indexing + cell attribution. Document-specific
metadata and literal question selection are local-development configuration, not
issuer-specific table-extraction logic. No benchmark truth or valuation logic.
"""
from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
import re
import unicodedata
from zoneinfo import ZoneInfo

import pymupdf

from app.evidence.cell_attribution import locate_cells_in_verified_pdf
from app.evidence.contracts import SourceDocument
from app.modules.financial_report_analyst.contracts import (
    ClaimKind, ClaimReview, ResearchClaim, ReviewVerdict,
)

QUESTION = "What were Hengrui's consolidated and parent-company revenues in 2026 H1?"
SOURCE = SourceDocument(
    document_id="600276-2026H1-cninfo-1225483600",
    ticker="600276",
    report_period="2026H1",
    source_url="https://static.cninfo.com.cn/finalpage/2026-08-20/1225483600.PDF",
    published_on=date(2026, 8, 20),
    source_sha256="ff6910663a9726acb889aa061a8bab1433f58890d81ebea013b8c637a097a7aa",
    canonical_sha256="96784f9deba244aab85bd117b9a1894bdcbd689a8368554f84014703f1e8b864",
)

# Question-specific lookup, not financial answers or company-specific geometry.
SELECTIONS = (
    {"section_kind": "consolidated_income_statement", "row_label": "其中：营业收入", "column_header": "2026 年半年度"},
    {"section_kind": "parent_income_statement", "row_label": "一、营业收入", "column_header": "2026 年半年度"},
)
_STATEMENT_LABELS = {
    "consolidated_income_statement": "合并利润表",
    "parent_income_statement": "母公司利润表",
}
_AMOUNT = re.compile(r"(?:0|[1-9]\d{0,2}(?:,\d{3})+|[1-9]\d*)\.\d{2}\Z")


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def _withheld(reason: str) -> dict:
    return {
        "status": "WITHHELD", "reason": reason, "claims": [], "reviews": [],
        "observations": [], "research_publication": "BLOCKED",
        "financial_semantic_review": "NOT_PERFORMED",
    }


def _words_in_rectangle(page: pymupdf.Page, rect: list[float]) -> str:
    # Independent native PDF-text access to validate that the indexed cell text
    # is actually present at its claimed geometry. This does not establish CAS meaning.
    clip = pymupdf.Rect(*rect) + (-1.0, -1.0, 1.0, 1.0)
    return _norm("".join(w[4] for w in page.get_text("words", clip=clip, sort=True)))


def review_literal(candidate: dict, pdf: pymupdf.Document) -> tuple[bool, str]:
    """Independent source-text / location check, not a semantic accounting review."""
    try:
        kind = candidate["section_kind_candidate"]
        if kind not in _STATEMENT_LABELS:
            return False, "UNSUPPORTED_STATEMENT"
        if candidate["accounting_scope_status"] != "HEADING_CANDIDATE_ONLY":
            return False, "SCOPE_STATUS_MISMATCH"
        if candidate["column_meaning_status"] != "HEADER_TEXT_ONLY":
            return False, "COLUMN_STATUS_MISMATCH"
        if candidate["source_text_span_status"] != "NOT_PROVEN_FROM_TABLE_GEOMETRY":
            return False, "SPAN_STATUS_MISMATCH"
        if candidate["review_status"] != "REVIEW_REQUIRED":
            return False, "REVIEW_STATUS_MISMATCH"
        if candidate["statement_context_status"] != "VERBATIM_SOURCE_CONTEXT":
            return False, "SOURCE_CONTEXT_MISSING"
        if _norm(candidate["statement_heading_verbatim"]) != _norm(_STATEMENT_LABELS[kind]):
            return False, "STATEMENT_HEADING_MISMATCH"
        ctx = _norm(candidate["statement_context_verbatim"])
        if not re.search(r"2026年1[—－-]6月", ctx):
            return False, "SOURCE_PERIOD_NOT_VERIFIED"
        if "单位:元" not in ctx or "币种:人民币" not in ctx:
            return False, "SOURCE_UNIT_NOT_VERIFIED"
        if _norm(candidate["column_header_verbatim"]) != "2026年半年度":
            return False, "COLUMN_HEADER_NOT_VERIFIED"
        raw = candidate["cell_text_verbatim"]
        if not isinstance(raw, str) or not _AMOUNT.fullmatch(raw.strip()):
            return False, "NOT_UNAMBIGUOUS_CURRENCY_AMOUNT"
        page_no = candidate["page_number"]
        if not isinstance(page_no, int) or page_no < 1 or page_no > len(pdf):
            return False, "PAGE_OUT_OF_RANGE"
        page = pdf[page_no - 1]
        actual = _words_in_rectangle(page, candidate["cell_bbox_pt"])
        if actual != _norm(raw):
            return False, "SOURCE_CELL_LOCATION_MISMATCH"
        label_actual = _words_in_rectangle(page, candidate["row_label_bbox_pt"])
        if label_actual != _norm(candidate["row_label_verbatim"]):
            return False, "SOURCE_ROW_LOCATION_MISMATCH"
        return True, "LITERAL_CELL_AND_HEADING_SOURCE_CHECK_ONLY"
    except (KeyError, TypeError, ValueError, IndexError):
        return False, "INVALID_CANDIDATE_SHAPE"


def build_source_draft(source: SourceDocument, pdf_path: Path, *, as_of: datetime) -> dict:
    """Bounded Analyst -> independent literal Reviewer -> fail-closed draft gate."""
    source.require_available(as_of)
    selections = list(SELECTIONS)
    results = locate_cells_in_verified_pdf(source, pdf_path, as_of=as_of, selections=selections)
    if len(results) != len(selections) or any(x.get("status") != "ONE_CELL_CANDIDATE" for x in results):
        return _withheld("SOURCE_CELL_UNRESOLVED")
    candidates = [r["candidates"][0] for r in results]
    if len({c["candidate_id"] for c in candidates}) != 2:
        return _withheld("DUPLICATE_SOURCE_CELL")
    for expected, item in zip(selections, candidates):
        if (item["document_id"] != source.document_id
            or item["source_sha256"] != source.source_sha256
            or item["canonical_sha256"] != source.canonical_sha256
            or item["section_kind_candidate"] != expected["section_kind"]
            or _norm(item["row_label_verbatim"]) != _norm(expected["row_label"])
            or _norm(item["column_header_verbatim"]) != _norm(expected["column_header"])):
            return _withheld("SOURCE_CANDIDATE_BINDING_MISMATCH")

    # Drafted by a bounded, deterministic Analyst; no inference or comparison.
    claims = tuple(ResearchClaim(
        claim_id=f"REV{i+1}", kind=ClaimKind.OBSERVED_FACT,
        text=(f'In the source section "{item["statement_heading_verbatim"]}", '
              f'the row "{item["row_label_verbatim"]}" under '
              f'"{item["column_header_verbatim"]}" reads '
              f'"{item["cell_text_verbatim"]}".'),
        evidence_ids=(item["candidate_id"],),
    ) for i, item in enumerate(candidates))
    with pymupdf.open(pdf_path) as pdf:
        reviews = tuple(ClaimReview(
            claim_id=claim.claim_id,
            reviewer_id="native-pdf-cell-literal-reviewer-v1",
            verdict=(ReviewVerdict.ADMIT if result[0] else ReviewVerdict.UNCERTAIN),
            rationale=result[1],
        ) for claim, result in zip(claims, (review_literal(item, pdf) for item in candidates)))
    if (len(reviews) != 2
        or {r.claim_id for r in reviews} != {c.claim_id for c in claims}
        or any(r.verdict != ReviewVerdict.ADMIT for r in reviews)):
        return _withheld("INDEPENDENT_LITERAL_REVIEW_NOT_PASSED")

    report_id = sha256((source.document_id + "|" + source.canonical_sha256 + "|revenue-scope-preview-v1").encode()).hexdigest()
    observations = [
        {
            "claim_id": claim.claim_id,
            "evidence_id": item["candidate_id"],
            "statement_title": item["statement_heading_verbatim"],
            "statement_type_candidate": item["section_kind_candidate"],
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
        } for claim, item in zip(claims, candidates)
    ]
    return {
        "status": "SOURCE_DRAFT_READY",
        "question": QUESTION,
        "report_id": report_id,
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "document_id": source.document_id,
        "ticker": source.ticker,
        "report_period": source.report_period,
        "source_url": source.source_url,
        "source_sha256": source.source_sha256,
        "canonical_sha256": source.canonical_sha256,
        "claims": [c.model_dump(mode="json") for c in claims],
        "reviews": [r.model_dump(mode="json") for r in reviews],
        "observations": observations,
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
        "limitation": "Two literal PDF cells and statement headings were checked. Source headings, currency and period remain unqualified financial semantics. No comparison, inference, or publication is approved.",
    }
