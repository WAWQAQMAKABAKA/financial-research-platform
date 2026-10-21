"""Synthetic guardrail tests. No real-document benchmark answers here."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.modules.financial_report_analyst import revenue_scope as rv

AS_OF = datetime(2026, 10, 21, tzinfo=ZoneInfo("Asia/Shanghai"))


def candidate(i):
    kind = rv.SELECTIONS[i]["section_kind"]
    return {
        "candidate_id": f"id-{i}",
        "document_id": rv.SOURCE.document_id,
        "source_sha256": rv.SOURCE.source_sha256,
        "canonical_sha256": rv.SOURCE.canonical_sha256,
        "section_kind_candidate": kind,
        "row_label_verbatim": rv.SELECTIONS[i]["row_label"],
        "column_header_verbatim": rv.SELECTIONS[i]["column_header"],
        "cell_text_verbatim": "123,456.78" if i == 0 else "321,098.76",
        "accounting_scope_status": "HEADING_CANDIDATE_ONLY",
        "column_meaning_status": "HEADER_TEXT_ONLY",
        "source_text_span_status": "NOT_PROVEN_FROM_TABLE_GEOMETRY",
        "review_status": "REVIEW_REQUIRED",
        "statement_context_status": "VERBATIM_SOURCE_CONTEXT",
        "statement_heading_verbatim": rv._STATEMENT_LABELS[kind],
        "statement_context_verbatim": "2026 年 1—6 月\n单位：元 币种：人民币",
        "page_number": 10 + i,
        "section_root_page": 10 + i,
        "table_index": 0,
        "row_index": 2,
        "column_index": 2,
        "cell_bbox_pt": [200.0, 130.0, 300.0, 155.0],
        "row_label_bbox_pt": [80.0, 130.0, 190.0, 155.0],
    }


class Page:
    def __init__(self, value, label):
        self.value, self.label = value, label

    def get_text(self, kind, clip, sort=True):
        assert kind == "words"
        if clip.x0 > 195:
            return [(201, 132, 300, 153, self.value, 0, 0, 0)]
        return [(85, 132, 188, 153, self.label, 0, 0, 0)]


class FakePDF:
    def __init__(self, a, b):
        self.pages = [Page("", "")] * 9 + [
            Page(a["cell_text_verbatim"], a["row_label_verbatim"]),
            Page(b["cell_text_verbatim"], b["row_label_verbatim"]),
        ]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def __len__(self):
        return len(self.pages)

    def __getitem__(self, i):
        return self.pages[i]


def patched(monkeypatch, candidates):
    monkeypatch.setattr(rv, "locate_cells_in_verified_pdf", lambda *args, **kwargs: [
        {"status": "ONE_CELL_CANDIDATE", "candidates": [x]} for x in candidates
    ])
    monkeypatch.setattr(rv.pymupdf, "open", lambda p: FakePDF(*candidates))


def test_literal_reviewer_accepts_source_cell_location(monkeypatch):
    items = [candidate(0), candidate(1)]
    patched(monkeypatch, items)
    report = rv.build_source_draft(rv.SOURCE, Path("synthetic.pdf"), as_of=AS_OF)
    assert report["status"] == "SOURCE_DRAFT_READY"
    assert report["research_publication"] == "BLOCKED"
    assert report["financial_semantic_review"] == "NOT_PERFORMED"
    assert len(report["claims"]) == 2
    assert all(r["verdict"] == "ADMIT" for r in report["reviews"])
    assert report["observations"][0]["statement_title"] == "合并利润表"
    assert report["observations"][1]["statement_title"] == "母公司利润表"


def test_scope_misassociation_fail_closed(monkeypatch):
    items = [candidate(0), candidate(1)]
    items[1]["section_kind_candidate"] = "consolidated_income_statement"
    patched(monkeypatch, items)
    result = rv.build_source_draft(rv.SOURCE, Path("ignored"), as_of=AS_OF)
    assert result["status"] == "WITHHELD" and result["observations"] == []


def test_source_identity_mismatch_fail_closed(monkeypatch):
    items = [candidate(0), candidate(1)]
    items[0]["canonical_sha256"] = "0" * 64
    patched(monkeypatch, items)
    result = rv.build_source_draft(rv.SOURCE, Path("ignored"), as_of=AS_OF)
    assert result["status"] == "WITHHELD"


def test_semantic_unit_context_missing_reviewer_withholds(monkeypatch):
    items = [candidate(0), candidate(1)]
    items[0]["statement_context_verbatim"] = "2026年1—6月"
    patched(monkeypatch, items)
    result = rv.build_source_draft(rv.SOURCE, Path("ignored"), as_of=AS_OF)
    assert result["status"] == "WITHHELD"
    assert result["claims"] == [] and result["observations"] == []


def test_dash_and_blank_are_not_numbers(monkeypatch):
    for missing in ("—", "", "0", "1.2"):
        items = [candidate(0), candidate(1)]
        items[0]["cell_text_verbatim"] = missing
        patched(monkeypatch, items)
        result = rv.build_source_draft(rv.SOURCE, Path("ignored"), as_of=AS_OF)
        assert result["status"] == "WITHHELD"


def test_source_location_check_rejects_different_pdf_text():
    item = candidate(0)
    other = candidate(1)
    pdf = FakePDF({**item, "cell_text_verbatim": "wrong"}, other)
    assert rv.review_literal(item, pdf)[0] is False


def test_pit_unavailable_before_next_day(monkeypatch):
    items = [candidate(0), candidate(1)]
    patched(monkeypatch, items)
    with pytest.raises(ValueError, match="PIT_UNAVAILABLE"):
        rv.build_source_draft(rv.SOURCE, Path("ignored"), as_of=datetime(2026, 8, 20, 23, 59, tzinfo=ZoneInfo("Asia/Shanghai")))


def test_new_api_route_disabled_by_default(monkeypatch):
    monkeypatch.delenv("FRP_LOCAL_REVENUE_PREVIEW", raising=False)
    response = TestClient(app).get("/api/v1/research/revenue-scope-preview")
    assert response.status_code == 404


def test_new_api_route_fails_closed_without_path(monkeypatch):
    monkeypatch.setenv("FRP_LOCAL_REVENUE_PREVIEW", "1")
    monkeypatch.delenv("FRP_LOCAL_REVENUE_PDF", raising=False)
    response = TestClient(app).get("/api/v1/research/revenue-scope-preview")
    assert response.status_code == 503
    assert response.json() == {"detail": "SOURCE_UNAVAILABLE"}
