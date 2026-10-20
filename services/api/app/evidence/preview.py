"""Explicitly local, unreviewed, source-specific financial evidence preview.

Native code in financial-research-platform. The evidence source is a separate,
ignored, hash-qualified local PDF. No cross-repository runtime access.
"""

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.evidence.contracts import EvidenceSpan, SourceDocument, require_evidence_binding
from app.evidence.pdf_canonicalizer import CanonicalDocument, canonicalize_pdf

DOCUMENT_ID = "600760-2026H1-cninfo-1225517994"
SOURCE = SourceDocument(
    document_id=DOCUMENT_ID,
    ticker="600760",
    report_period="2026H1",
    source_url="https://static.cninfo.com.cn/finalpage/2026-08-28/1225517994.PDF",
    published_on=date(2026, 8, 28),
    source_sha256="d53ee98c091fdcbb8df3ebcc3f8d9bef87f61b374615dc3165dadb594f637d99",
    canonical_sha256="620d3a30f73423527dd662e21ebf3367b546dfa6795c6fcf618f35ebf0008aa5",
)
PDF_PATH = Path(__file__).resolve().parents[4] / "data/raw/600760/2026H1/source.pdf"
PAGE_NUMBER = 198
TABLE_START = 229004
TABLE_END = 230562
ROW_ANCHORS = (
    ("segment-revenue-row", "一、营业收入", "6,191,107,217.36", 229181),
    ("segment-cost-row", "二、营业成本", "5,535,215,299.31", 229308),
)


def require_exact_span(
    source: SourceDocument,
    canonical: CanonicalDocument,
    span: EvidenceSpan,
    as_of: datetime,
) -> None:
    require_evidence_binding(source, span, as_of)
    if (
        canonical.document_id != source.document_id
        or canonical.source_sha256 != source.source_sha256
        or canonical.canonical_sha256 != source.canonical_sha256
    ):
        raise ValueError("CANONICAL_SOURCE_IDENTITY_MISMATCH")
    if span.page_number > len(canonical.pages):
        raise ValueError("EVIDENCE_PAGE_OUT_OF_RANGE")
    page = canonical.pages[span.page_number - 1]
    if (
        page.page_number != span.page_number
        or span.canonical_start < page.content_start
        or span.canonical_end > page.content_end
    ):
        raise ValueError("EVIDENCE_PAGE_BOUNDARY_MISMATCH")
    if canonical.canonical_text[span.canonical_start:span.canonical_end] != span.excerpt:
        raise ValueError("EVIDENCE_EXCERPT_MISMATCH")


def build_source_preview(pdf_path: Path) -> dict:
    as_of = datetime.now(ZoneInfo("Asia/Shanghai"))
    SOURCE.require_available(as_of)
    canonical = canonicalize_pdf(
        document_id=DOCUMENT_ID,
        pdf_path=pdf_path,
        expected_source_sha256=SOURCE.source_sha256,
    )
    if (
        canonical.canonical_sha256 != SOURCE.canonical_sha256
        or len(canonical.canonical_text) != 237398
        or len(canonical.pages) != 207
    ):
        raise ValueError("CANONICAL_REGRESSION_MISMATCH")
    page = canonical.pages[PAGE_NUMBER - 1]
    text = canonical.canonical_text
    if not (page.content_start <= TABLE_START < TABLE_END <= page.content_end):
        raise ValueError("TABLE_PAGE_BOUNDARY_MISMATCH")
    table = text[TABLE_START:TABLE_END]
    if not all(x in table for x in ("报告分部的财务信息", "合计", "单位：元")):
        raise ValueError("TABLE_CONTEXT_MISMATCH")

    evidence = []
    for evidence_id, label, number, value_offset in ROW_ANCHORS:
        if text[value_offset:value_offset + len(number)] != number:
            raise ValueError("ROW_NUMBER_ANCHOR_MISMATCH")
        line_start = text.rfind("\n", TABLE_START, value_offset) + 1
        line_end = text.find("\n", value_offset, TABLE_END)
        if line_end < 0 or not (TABLE_START <= line_start < value_offset < line_end <= TABLE_END):
            raise ValueError("ROW_BOUNDARY_MISMATCH")
        excerpt = text[line_start:line_end]
        if label not in excerpt or excerpt.index(label) > excerpt.index(number):
            raise ValueError("ROW_LABEL_NUMBER_MISMATCH")
        span = EvidenceSpan(
            evidence_id=evidence_id,
            document_id=DOCUMENT_ID,
            canonical_sha256=SOURCE.canonical_sha256,
            page_number=PAGE_NUMBER,
            canonical_start=line_start,
            canonical_end=line_end,
            excerpt=excerpt,
        )
        require_exact_span(SOURCE, canonical, span, as_of)
        evidence.append(span.model_dump())
    return {
        "status": "SOURCE_EVIDENCE_ONLY",
        "document_id": DOCUMENT_ID,
        "ticker": SOURCE.ticker,
        "report_period": SOURCE.report_period,
        "source_url": SOURCE.source_url,
        "source_sha256": SOURCE.source_sha256,
        "canonical_sha256": SOURCE.canonical_sha256,
        "checked_as_of": as_of.isoformat(),
        "financial_semantic_review": "NOT_PERFORMED",
        "evidence": evidence,
        "limitation": (
            "The labels and numbers occur on source page 198. PDF text flattening does "
            "not establish segment-column attribution or equivalence to consolidated "
            "income statement lines. No independent financial-semantic review was performed."
        ),
    }
