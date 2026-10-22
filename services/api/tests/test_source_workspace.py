"""Offline M1.7A two-issuer controls; synthetic financial values only."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.financial_report_analyst import source_workspace as ws

AS_OF = datetime(2026, 10, 21, tzinfo=ZoneInfo("Asia/Shanghai"))


def fake_cell(entry: ws.ReportEntry) -> dict:
    return {
        "candidate_id": "synthetic-verified-cell", "document_id": entry.source.document_id,
        "source_sha256": entry.source.source_sha256,
        "canonical_sha256": entry.source.canonical_sha256,
        "source_url": entry.source.source_url,
        "section_kind_candidate": entry.section_kind,
        "statement_heading_verbatim": "合并利润表",
        "statement_context_verbatim": "2026年1—6月 单位：元 币种：人民币",
        "row_label_verbatim": entry.row_label,
        "column_header_verbatim": entry.column_header,
        "cell_text_verbatim": "12,345.67",
        "page_number": 99, "table_index": 1, "row_index": 2,
        "column_index": 2, "cell_bbox_pt": [200., 200., 300., 220.],
        "source_text_span_status": "NOT_PROVEN_FROM_TABLE_GEOMETRY",
        "accounting_scope_status": "HEADING_CANDIDATE_ONLY",
        "column_meaning_status": "HEADER_TEXT_ONLY",
        "review_status": "REVIEW_REQUIRED",
    }


class FakePDF:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


def configure(monkeypatch, report_key, *, overrides=None, passed=True, status="ONE_CELL_CANDIDATE"):
    entry = ws.REPORTS[report_key]
    cell = {**fake_cell(entry), **(overrides or {})}
    tracked = []

    def locate(source, pdf_path, *, as_of, selections):
        tracked.append((source, pdf_path, as_of, selections))
        return [{"status": status, "candidates": [cell]}]

    monkeypatch.setattr(ws, "locate_cells_in_verified_pdf", locate)
    monkeypatch.setattr(ws.pymupdf, "open", lambda path: FakePDF())
    monkeypatch.setattr(ws.revenue_scope, "review_literal", lambda item, pdf: (
        passed, "LITERAL_CELL_AND_HEADING_SOURCE_CHECK_ONLY" if passed else "WRONG_NATIVE_PDF_CELL"
    ))
    return tracked


@pytest.mark.parametrize("key", sorted(ws.REPORTS))
def test_one_shared_path_for_both_issuers(monkeypatch, key):
    tracked = configure(monkeypatch, key)
    entry = ws.REPORTS[key]
    out = ws.build_source_workspace(key, Path("unused-pinned.pdf"), as_of=AS_OF)
    assert out["status"] == "SOURCE_DRAFT_READY"
    assert out["report_key"] == key
    assert out["document_id"] == entry.source.document_id
    assert out["source_sha256"] == entry.source.source_sha256
    assert out["canonical_sha256"] == entry.source.canonical_sha256
    assert out["observations"][0]["value_verbatim"] == "12,345.67"
    assert out["research_publication"] == "BLOCKED"
    assert out["financial_semantic_review"] == "NOT_PERFORMED"
    assert out["reviews"][0]["rationale"] == "LITERAL_CELL_AND_HEADING_SOURCE_CHECK_ONLY"
    assert tracked[0][0] == entry.source
    assert tracked[0][3] == [{
        "section_kind": "consolidated_income_statement",
        "row_label": "其中：营业收入",
        "column_header": "2026 年半年度",
    }]


def test_different_issuers_do_not_share_document_identity():
    a, b = ws.REPORTS.values()
    assert a.source.document_id != b.source.document_id
    assert a.source.canonical_sha256 != b.source.canonical_sha256
    assert a.source.source_sha256 != b.source.source_sha256
    assert a.pdf_env_name != b.pdf_env_name


def test_unknown_issuer_fails_closed():
    with pytest.raises(ws.UnknownReportError, match="REPORT_NOT_ALLOWLISTED"):
        ws.build_source_workspace("999999-2026H1", Path("nothing"), as_of=AS_OF)


@pytest.mark.parametrize("changed", [
    {"document_id": "WRONG-DOCUMENT"},
    {"canonical_sha256": "0" * 64},
    {"source_sha256": "0" * 64},
    {"source_url": "https://example.test/wrong.pdf"},
    {"section_kind_candidate": "parent_income_statement"},
    {"column_header_verbatim": "2025 年半年度"},
    {"row_label_verbatim": "其中：营业成本"},
    {"review_status": "PUBLISHED"},
    {"source_text_span_status": "PROVEN"},
    {"accounting_scope_status": "QUALIFIED"},
])
def test_wrong_binding_never_shows_money(monkeypatch, changed):
    configure(monkeypatch, "600760-2026H1", overrides=changed)
    out = ws.build_source_workspace("600760-2026H1", Path("unused"), as_of=AS_OF)
    assert out["status"] == "WITHHELD"
    assert out["claims"] == out["observations"] == []
    assert out["research_publication"] == "BLOCKED"


def test_unresolved_cell_never_shows_money(monkeypatch):
    configure(monkeypatch, "600276-2026H1", status="UNRESOLVED")
    out = ws.build_source_workspace("600276-2026H1", Path("unused"), as_of=AS_OF)
    assert out["status"] == "WITHHELD"
    assert out["observations"] == []


def test_failed_literal_review_never_shows_money(monkeypatch):
    configure(monkeypatch, "600760-2026H1", passed=False)
    out = ws.build_source_workspace("600760-2026H1", Path("unused"), as_of=AS_OF)
    assert out["status"] == "WITHHELD"
    assert out["claims"] == out["observations"] == []


def test_pit_before_available_day_rejected(monkeypatch):
    configure(monkeypatch, "600760-2026H1")
    with pytest.raises(ValueError, match="PIT_UNAVAILABLE"):
        ws.build_source_workspace("600760-2026H1", Path("unused"), as_of=datetime(
            2026, 8, 28, 23, 59, tzinfo=ZoneInfo("Asia/Shanghai")
        ))


def test_report_ids_are_source_specific_and_stable(monkeypatch):
    ids = []
    for key in sorted(ws.REPORTS):
        configure(monkeypatch, key)
        first = ws.build_source_workspace(key, Path("unused"), as_of=AS_OF)
        second = ws.build_source_workspace(key, Path("unused"), as_of=AS_OF)
        assert first["report_id"] == second["report_id"]
        ids.append(first["report_id"])
    assert len(set(ids)) == 2


def test_route_off_by_default(monkeypatch):
    monkeypatch.delenv("FRP_LOCAL_SOURCE_WORKSPACE", raising=False)
    for key in ws.REPORTS:
        assert TestClient(app).get(f"/api/v1/research/source-workspace/{key}").status_code == 404


def test_unknown_route_fails_closed(monkeypatch):
    monkeypatch.setenv("FRP_LOCAL_SOURCE_WORKSPACE", "1")
    assert TestClient(app).get("/api/v1/research/source-workspace/../../etc/passwd").status_code in (404, 422)
    assert TestClient(app).get("/api/v1/research/source-workspace/999999-2026H1").status_code == 404


def test_route_requires_server_defined_pdf_path(monkeypatch):
    monkeypatch.setenv("FRP_LOCAL_SOURCE_WORKSPACE", "1")
    for entry in ws.REPORTS.values():
        monkeypatch.delenv(entry.pdf_env_name, raising=False)
        result = TestClient(app).get(f"/api/v1/research/source-workspace/{entry.key}")
        assert result.status_code == 503
        assert result.json() == {"detail": "SOURCE_UNAVAILABLE"}


def test_route_does_not_leak_source_errors(monkeypatch):
    monkeypatch.setenv("FRP_LOCAL_SOURCE_WORKSPACE", "1")
    monkeypatch.setenv(ws.REPORTS["600760-2026H1"].pdf_env_name, "/no/such/file.pdf")
    def fail(*args, **kwargs):
        raise FileNotFoundError("private filesystem diagnostic")
    monkeypatch.setattr(ws, "build_source_workspace", fail)
    resp = TestClient(app).get("/api/v1/research/source-workspace/600760-2026H1")
    assert resp.status_code == 503
    assert resp.json() == {"detail": "SOURCE_UNAVAILABLE"}
    assert "private" not in resp.text


def test_route_passes_selected_pinned_pdf_path(monkeypatch):
    monkeypatch.setenv("FRP_LOCAL_SOURCE_WORKSPACE", "1")
    target = "/tmp/local-synthetic-source.pdf"
    monkeypatch.setenv(ws.REPORTS["600276-2026H1"].pdf_env_name, target)
    seen = []
    def build(key, path, *, as_of):
        seen.append((key, path, as_of))
        return {"status": "WITHHELD", "reason": "SYNTHETIC", "claims": [],
                "observations": [], "reviews": [],
                "financial_semantic_review": "NOT_PERFORMED",
                "research_publication": "BLOCKED"}
    monkeypatch.setattr(ws, "build_source_workspace", build)
    resp = TestClient(app).get("/api/v1/research/source-workspace/600276-2026H1")
    assert resp.status_code == 200 and resp.json()["status"] == "WITHHELD"
    assert seen[0][0] == "600276-2026H1"
    assert seen[0][1] == Path(target)
    assert seen[0][2].utcoffset() is not None
