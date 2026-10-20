"""Synthetic structural tests. No protected labels or real-document answers."""
from datetime import date, datetime
from hashlib import sha256
from zoneinfo import ZoneInfo

import pymupdf
import pytest

from app.evidence.contracts import SourceDocument
from app.evidence.document_index import (
    assign_sections, classify_heading, index_document,
)
from app.evidence.pdf_canonicalizer import canonicalize_pdf


def test_heading_must_be_isolated_title():
    assert classify_heading("合并利润表") == "consolidated_income_statement"
    assert classify_heading("母公司利润表") == "parent_income_statement"
    assert classify_heading("（2） 报告分部的财务信息") == "segment_financial_information"
    assert classify_heading("本期发生额已经包括在合并利润表和其他报表中") is None
    assert classify_heading("本期公司业务合并利润表体现了") is None


def table(y0, y1, *, x0=84, x1=537, columns=4):
    width = (x1 - x0) / columns
    return {
        "table_index": 0,
        "bbox_pt": [x0, y0, x1, y1],
        "row_count": 3,
        "column_count": columns,
        "rows": [[{
            "row_index": i, "column_index": j,
            "text": "", "bbox_pt": [x0 + j * width, y0,
                                       x0 + (j + 1) * width, y1],
            "extraction_status": "BLANK_OR_UNEXTRACTED",
        } for j in range(columns)] for i in range(3)],
        "section_kind": None,
        "relationship": "UNASSIGNED",
        "review_status": "REVIEW_REQUIRED",
    }


def heading(kind, y):
    return {"kind": kind, "text": kind, "bbox_pt": [240, y, 390, y + 15]}


def page(n, headings, tables):
    return {"page_number": n, "height_pt": 842.0, "width_pt": 595.0,
            "headings": headings, "tables": tables}


def test_two_statement_types_on_same_page_no_cross_contamination():
    # Simulates page N: an unrelated upper table and lower statement start;
    # N+1: continuation; N+2: conclusion followed by a new statement.
    pages = [
        page(1, [heading("consolidated_income_statement", 490)],
             [table(80, 460), table(530, 800)]),
        page(2, [], [table(80, 805)]),
        page(3, [heading("parent_income_statement", 475)],
             [table(80, 420), table(510, 805)]),
    ]
    assign_sections(pages)
    assert pages[0]["tables"][0]["section_kind"] is None
    assert pages[0]["tables"][1]["relationship"] == "SECTION_ROOT_CANDIDATE"
    assert pages[1]["tables"][0]["section_kind"] == "consolidated_income_statement"
    assert pages[1]["tables"][0]["relationship"] == "GEOMETRIC_CONTINUATION_CANDIDATE"
    assert pages[2]["tables"][0]["section_kind"] == "consolidated_income_statement"
    assert pages[2]["tables"][1]["section_kind"] == "parent_income_statement"
    assert pages[2]["tables"][1]["relationship"] == "SECTION_ROOT_CANDIDATE"


def test_mismatched_grid_and_page_gap_do_not_continue():
    pages = [
        page(1, [heading("consolidated_income_statement", 100)], [table(150, 820)]),
        page(2, [], [table(70, 800, columns=6)]),
        page(3, [], [table(70, 820)]),
    ]
    assign_sections(pages)
    assert pages[0]["tables"][0]["section_kind"] == "consolidated_income_statement"
    assert pages[1]["tables"][0]["section_kind"] is None
    assert pages[2]["tables"][0]["section_kind"] is None


def test_heading_mention_below_table_does_not_relabel_prior_cells():
    pages = [page(1, [heading("parent_income_statement", 480)],
                  [table(60, 390)])]
    assign_sections(pages)
    assert pages[0]["tables"][0]["section_kind"] is None


def synthetic_pdf(tmp_path):
    path = tmp_path / "synthetic.pdf"
    with pymupdf.open() as doc:
        pg = doc.new_page()
        pg.draw_rect(pymupdf.Rect(72, 100, 512, 230), color=(0, 0, 0))
        for x in (180, 290, 401):
            pg.draw_line((x, 100), (x, 230))
        for y in (140, 180):
            pg.draw_line((72, y), (512, y))
        pg.insert_text((80, 126), "Metric")
        pg.insert_text((195, 126), "2026")
        pg.insert_text((305, 126), "2025")
        pg.insert_text((80, 165), "Revenue")
        pg.insert_text((195, 165), "100")
        doc.save(path)
    digest = sha256(path.read_bytes()).hexdigest()
    canonical = canonicalize_pdf(
        document_id="SYNTHETIC", pdf_path=path,
        expected_source_sha256=digest,
    )
    source = SourceDocument(
        document_id="SYNTHETIC", ticker="TEST", report_period="2026H1",
        source_url="https://example.org/synthetic.pdf",
        published_on=date(2026, 8, 28), source_sha256=digest,
        canonical_sha256=canonical.canonical_sha256,
    )
    return path, source


def test_full_index_preserves_source_and_cell_geometry(tmp_path):
    path, source = synthetic_pdf(tmp_path)
    result = index_document(source, path,
        as_of=datetime(2026, 10, 20, tzinfo=ZoneInfo("Asia/Shanghai")))
    assert result["page_count"] == 1
    assert result["source_sha256"] == source.source_sha256
    assert result["canonical_sha256"] == source.canonical_sha256
    assert result["research_publication"] == "BLOCKED"
    assert result["financial_semantic_review"] == "NOT_PERFORMED"
    assert result["qualification_status"] == "REVIEW_REQUIRED"
    assert result["pages"][0]["tables"]
    assert all(t["section_kind"] is None for t in result["pages"][0]["tables"])
    assert result["pages"][0]["tables"][0]["rows"][0][0]["bbox_pt"] is not None


def test_source_hash_mismatch_fails_closed(tmp_path):
    path, source = synthetic_pdf(tmp_path)
    wrong = source.model_copy(update={"source_sha256": "0" * 64})
    with pytest.raises(ValueError, match="SOURCE_SHA_MISMATCH"):
        index_document(wrong, path,
            as_of=datetime(2026, 10, 20, tzinfo=ZoneInfo("Asia/Shanghai")))


def test_pit_future_source_rejected(tmp_path):
    path, source = synthetic_pdf(tmp_path)
    with pytest.raises(ValueError, match="PIT_UNAVAILABLE"):
        index_document(source, path,
            as_of=datetime(2026, 8, 28, 23, 59, tzinfo=ZoneInfo("Asia/Shanghai")))
