"""Synthetic invariants only. Real-document reference answers stay offline."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.evidence.cell_attribution import locate_cell_candidate
from app.evidence.contracts import SourceDocument

AS_OF = datetime(2026, 10, 20, tzinfo=ZoneInfo("Asia/Shanghai"))
SOURCE = SourceDocument(
    document_id="synthetic-issuer-2026h1", ticker="TEST", report_period="2026H1",
    source_url="https://example.test/synthetic.pdf", published_on=date(2026, 8, 1),
    source_sha256="a" * 64, canonical_sha256="b" * 64,
)


def tbl(page, index, rows, kind, relation):
    result_rows = []
    for ri, values in enumerate(rows):
        result_rows.append([{
            "row_index": ri, "column_index": ci, "text": value,
            "bbox_pt": [10.0 + ci * 100, 100.0 + ri * 20,
                        110.0 + ci * 100, 120.0 + ri * 20],
            "extraction_status": "TEXT_DETECTED" if value else "BLANK_OR_UNEXTRACTED",
        } for ci, value in enumerate(values)])
    return {
        "table_index": index, "bbox_pt": [10, 100, 410, 300],
        "row_count": len(rows), "column_count": 4, "rows": result_rows,
        "section_kind": kind, "relationship": relation, "review_status": "REVIEW_REQUIRED",
    }


def fixture():
    con = "consolidated_income_statement"
    par = "parent_income_statement"
    first = tbl(1, 0, [["项目", "附注", "2026 年半年度", "2025 年半年度"],
                       ["其中：营业收入", "Note", "100.00", "80.00"]],
                con, "SECTION_ROOT_CANDIDATE")
    continued = tbl(2, 0, [["财务费用", "Note", "-3.20", "2.00"],
                           ["空列", "", "", "—"]],
                    con, "GEOMETRIC_CONTINUATION_CANDIDATE")
    parent = tbl(2, 1, [["项目", "附注", "2026年半年度", "2025年半年度"],
                        ["其中：营业收入", "Note", "70.00", "65.00"]],
                 par, "SECTION_ROOT_CANDIDATE")
    pages = [
        {"page_number": 1, "width_pt": 595, "height_pt": 842,
         "headings": [], "tables": [first]},
        {"page_number": 2, "width_pt": 595, "height_pt": 842,
         "headings": [], "tables": [continued, parent]},
    ]
    sections = []
    for page in pages:
        for table in page["tables"]:
            sections.append({
                "page_number": page["page_number"], "table_index": table["table_index"],
                "section_kind": table["section_kind"], "relationship": table["relationship"],
                "bbox_pt": table["bbox_pt"], "shape": [table["row_count"], table["column_count"]],
            })
    return {
        "index_schema": "frp-cn-document-index-candidate-v1",
        "document_id": SOURCE.document_id, "source_sha256": SOURCE.source_sha256,
        "canonical_sha256": SOURCE.canonical_sha256, "pages": pages,
        "page_count": 2, "sections": sections,
        "qualification_status": "REVIEW_REQUIRED",
        "financial_semantic_review": "NOT_PERFORMED", "research_publication": "BLOCKED",
    }


def select(m, kind, row, col="2026年半年度", **kwargs):
    return locate_cell_candidate(
        m, SOURCE, as_of=kwargs.get("as_of", AS_OF), section_kind=kind,
        row_label=row, column_header=col,
    )


def test_consolidated_and_parent_values_not_mixed():
    m = fixture()
    c = select(m, "consolidated_income_statement", "其中：营业收入")
    p = select(m, "parent_income_statement", "其中：营业收入")
    assert c["status"] == p["status"] == "ONE_CELL_CANDIDATE"
    assert c["candidates"][0]["cell_text_verbatim"] == "100.00"
    assert p["candidates"][0]["cell_text_verbatim"] == "70.00"
    assert c["candidates"][0]["candidate_id"] != p["candidates"][0]["candidate_id"]
    assert c["research_publication"] == p["research_publication"] == "BLOCKED"


def test_column_header_literal_prevents_prior_period_mix():
    m = fixture()
    result = select(m, "consolidated_income_statement", "其中：营业收入", "2025年半年度")
    assert result["candidates"][0]["cell_text_verbatim"] == "80.00"
    assert result["candidates"][0]["column_header_verbatim"] == "2025 年半年度"
    assert result["candidates"][0]["column_meaning_status"] == "HEADER_TEXT_ONLY"


def test_continuation_negatives_blanks_and_dashes_not_zero():
    m = fixture()
    negative = select(m, "consolidated_income_statement", "财务费用")
    assert negative["candidates"][0]["cell_text_verbatim"] == "-3.20"
    assert negative["candidates"][0]["page_number"] == 2
    assert negative["candidates"][0]["section_relationship"] == "GEOMETRIC_CONTINUATION_CANDIDATE"
    blank = select(m, "consolidated_income_statement", "空列")
    dash = select(m, "consolidated_income_statement", "空列", "2025年半年度")
    assert blank["candidates"][0]["cell_text_status"] == "BLANK_OR_UNEXTRACTED"
    assert dash["candidates"][0]["cell_text_status"] == "DASH_UNINTERPRETED"


def test_missing_and_duplicate_labels_fail_closed():
    m = fixture()
    assert select(m, "consolidated_income_statement", "不存在")["reason"] == "ROW_NOT_FOUND"
    m["pages"][1]["tables"][0]["rows"][0][0]["text"] = "其中：营业收入"
    result = select(m, "consolidated_income_statement", "其中：营业收入")
    assert result["status"] == "UNRESOLVED"
    assert result["reason"] == "DUPLICATE_ROW_ACROSS_SECTION"
    assert result["candidates"] == []


def test_missing_duplicate_headers_fail_closed():
    m = fixture()
    assert select(m, "consolidated_income_statement", "其中：营业收入", "2024年半年度")["status"] == "UNRESOLVED"
    m["pages"][0]["tables"][0]["rows"][0][1]["text"] = "2026年半年度"
    assert select(m, "consolidated_income_statement", "其中：营业收入")["reason"] == "COLUMN_HEADER_MISSING_OR_AMBIGUOUS"


def test_no_auto_comparison_or_canonical_span_claimed():
    v = select(fixture(), "consolidated_income_statement", "其中：营业收入")
    cell = v["candidates"][0]
    assert cell["canonical_text_span"] is None
    assert cell["source_text_span_status"] == "NOT_PROVEN_FROM_TABLE_GEOMETRY"
    assert cell["accounting_scope_status"] == "HEADING_CANDIDATE_ONLY"
    assert v["financial_semantic_review"] == "NOT_PERFORMED"


def test_wrong_source_provenance_rejected():
    m = fixture()
    m["source_sha256"] = "c" * 64
    with pytest.raises(ValueError, match="INDEX_SOURCE_IDENTITY_MISMATCH"):
        select(m, "consolidated_income_statement", "其中：营业收入")


def test_wrong_pit_rejected():
    with pytest.raises(ValueError, match="PIT_UNAVAILABLE"):
        select(fixture(), "consolidated_income_statement", "其中：营业收入",
               as_of=datetime(2026, 8, 1, 23, 59, tzinfo=ZoneInfo("Asia/Shanghai")))


def test_wrong_cell_geometry_rejected():
    m = fixture()
    m["pages"][0]["tables"][0]["rows"][1][2]["bbox_pt"] = None
    assert select(m, "consolidated_income_statement", "其中：营业收入")["reason"] == "CELL_GEOMETRY_MISSING"


def test_section_binding_mismatch_rejected():
    m = fixture()
    m["sections"][0]["shape"] = [999, 4]
    with pytest.raises(ValueError, match="SECTION_TABLE_BINDING_MISMATCH"):
        select(m, "consolidated_income_statement", "其中：营业收入")


def test_reject_unreviewed_index_marked_publishable():
    m = fixture()
    m["research_publication"] = "ALLOWED"
    with pytest.raises(ValueError, match="INDEX_PUBLICATION_BOUNDARY_VIOLATED"):
        select(m, "consolidated_income_statement", "其中：营业收入")
