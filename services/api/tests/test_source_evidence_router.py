"""M121 offline source-routing contract. Synthetic, no PDF/model/network."""
from copy import deepcopy

import pytest

from app.modules.financial_report_analyst import (
    revenue_scope,
    source_evidence_router as router,
)


def source_packet():
    source = revenue_scope.SOURCE
    return {
        "status": "LOCAL_SOURCE_REPORT_READY",
        "report_type": "UNPUBLISHED_SOURCE_REPORT_PREVIEW",
        "report_key": router.REPORT_KEY,
        "report_identity": "a" * 64,
        "report_storage": "NOT_PERSISTED",
        "document_id": source.document_id,
        "source_url": source.source_url,
        "source_sha256": source.source_sha256,
        "canonical_sha256": source.canonical_sha256,
        "report_period": source.report_period,
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
        "observations": [
            {
                "claim_id": "REV1", "kind": "SOURCE_LITERAL_OBSERVATION",
                "evidence_id": "1" * 64, "page": 77,
                "statement_title": "合并利润表", "row_label": "其中：营业收入",
                "column_header": "2026 年半年度", "value_verbatim": "1,234.56",
                "review_result": "SOURCE_LOCATION_VERIFIED_ONLY",
                "review_scope": "LITERAL_CELL_LOCATION_ONLY",
            },
            {
                "claim_id": "REV2", "kind": "SOURCE_LITERAL_OBSERVATION",
                "evidence_id": "2" * 64, "page": 79,
                "statement_title": "母公司利润表", "row_label": "一、营业收入",
                "column_header": "2026 年半年度", "value_verbatim": "3,456.78",
                "review_result": "SOURCE_LOCATION_VERIFIED_ONLY",
                "review_scope": "LITERAL_CELL_LOCATION_ONLY",
            },
        ],
        "management_statement": {
            "claim_id": "M1", "kind": "ATTRIBUTED_MANAGEMENT_STATEMENT",
            "evidence_id": "3" * 64, "page": 20,
            "text": (
                "2026年上半年公司创新药销售收入1.23亿元，"
                "同比增长4.56%，占药品销售收入的比重达7.89%。"
            ),
            "review_result": "SOURCE_PASSAGE_LOCATED_ONLY",
            "review_scope": "NATIVE_PDF_TEXT_AND_WORD_LOCATION_ONLY",
        },
    }


def test_revenue_route_selects_by_claim_not_array_position():
    packet = source_packet()
    packet["observations"].reverse()
    result = router.route_evidence(packet, "CONSOLIDATED_REVENUE")
    assert result["evidence_id"] == "1" * 64
    assert result["value_verbatim"] == "1,234.56"
    assert result["source_page"] == 77
    assert result["denominator_label"] is None
    assert result["source_report_identity"] == "a" * 64
    assert result["research_publication"] == "BLOCKED"


def test_attributed_share_preserves_explicit_denominator():
    result = router.route_evidence(
        source_packet(), "INNOVATIVE_SHARE_OF_DRUG_SALES",
    )
    assert result["value_verbatim"] == "7.89%"
    assert result["denominator_label"] == "药品销售收入"
    assert result["evidence_kind"] == "ATTRIBUTED_MANAGEMENT_SHARE"
    assert result["routing_review_scope"] == "SOURCE_BINDING_ONLY"
    assert result["financial_semantic_review"] == "NOT_PERFORMED"


@pytest.mark.parametrize("kind", [
    "PARENT_REVENUE", "TRADE_ACTION", "INNOVATIVE_SHARE_OF_CONSOLIDATED_REVENUE",
])
def test_no_fallback_for_unsupported_kind(kind):
    with pytest.raises(ValueError, match="SOURCE_EVIDENCE_ROUTE_NOT_QUALIFIED"):
        router.route_evidence(source_packet(), kind)


@pytest.mark.parametrize("field,value", [
    ("source_sha256", "f" * 64),
    ("canonical_sha256", "f" * 64),
    ("research_publication", "PUBLISHED"),
    ("financial_semantic_review", "ADMIT"),
    ("report_identity", "forged"),
])
def test_rejects_modified_provenance_or_status(field, value):
    packet = source_packet()
    packet[field] = value
    with pytest.raises(ValueError, match="SOURCE_EVIDENCE_ROUTE_NOT_QUALIFIED"):
        router.route_evidence(packet, "CONSOLIDATED_REVENUE")


def test_missing_or_duplicate_claim_withheld():
    packet = source_packet()
    packet["observations"].append(deepcopy(packet["observations"][0]))
    with pytest.raises(ValueError, match="SOURCE_EVIDENCE_ROUTE_NOT_QUALIFIED"):
        router.route_evidence(packet, "CONSOLIDATED_REVENUE")


def test_parent_company_row_cannot_impersonate_consolidated_revenue():
    packet = source_packet()
    packet["observations"][0]["statement_title"] = "母公司利润表"
    with pytest.raises(ValueError, match="SOURCE_EVIDENCE_ROUTE_NOT_QUALIFIED"):
        router.route_evidence(packet, "CONSOLIDATED_REVENUE")


def test_management_denominator_substitution_withheld():
    packet = source_packet()
    packet["management_statement"]["text"] = packet["management_statement"][
        "text"
    ].replace("占药品销售收入", "占合并营业收入")
    with pytest.raises(ValueError, match="SOURCE_EVIDENCE_ROUTE_NOT_QUALIFIED"):
        router.route_evidence(packet, "INNOVATIVE_SHARE_OF_DRUG_SALES")


def test_management_missing_source_evidence_withheld():
    packet = source_packet()
    packet["management_statement"]["evidence_id"] = "missing"
    with pytest.raises(ValueError, match="SOURCE_EVIDENCE_ROUTE_NOT_QUALIFIED"):
        router.route_evidence(packet, "INNOVATIVE_SHARE_OF_DRUG_SALES")


def test_local_source_report_route_integration_without_pdf(monkeypatch):
    """Authenticated API returns a source-bound route; no LLM or real PDF."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.modules.financial_report_analyst import source_report_preview

    monkeypatch.setenv("FRP_LOCAL_REPORT_PREVIEW_UI", "1")
    monkeypatch.setenv("FRP_LOCAL_LLM_ACCESS_TOKEN", "x" * 64)
    monkeypatch.setenv("FRP_LOCAL_REVENUE_PDF", "/synthetic/not-real.pdf")
    monkeypatch.setattr(
        source_report_preview, "build_source_report",
        lambda *args, **kwargs: source_packet(),
    )
    client = TestClient(app)
    headers = {"x-frp-local-token": "x" * 64}
    url = "/api/v1/research/local-source-report"

    routed = client.post(url, json={
        "report_key": router.REPORT_KEY,
        "answer_kind": "INNOVATIVE_SHARE_OF_DRUG_SALES",
    }, headers=headers)
    assert routed.status_code == 200
    assert routed.json()["routed_evidence"]["value_verbatim"] == "7.89%"
    assert routed.json()["routed_evidence"]["research_publication"] == "BLOCKED"

    original = client.post(
        url, json={"report_key": router.REPORT_KEY}, headers=headers,
    )
    assert original.status_code == 200
    assert "routed_evidence" not in original.json()

    unsupported = client.post(url, json={
        "report_key": router.REPORT_KEY,
        "answer_kind": "INNOVATIVE_SHARE_OF_CONSOLIDATED_REVENUE",
    }, headers=headers)
    assert unsupported.status_code == 422

    unauthorized = client.post(url, json={
        "report_key": router.REPORT_KEY,
        "answer_kind": "CONSOLIDATED_REVENUE",
    })
    assert unauthorized.status_code == 404


def test_local_source_report_route_fails_closed_on_mismatched_evidence(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.modules.financial_report_analyst import source_report_preview

    packet = source_packet()
    packet["management_statement"]["text"] = (
        "2026年上半年公司创新药销售收入1.23亿元，"
        "同比增长4.56%，占合并营业收入的比重达7.89%。"
    )
    monkeypatch.setenv("FRP_LOCAL_REPORT_PREVIEW_UI", "1")
    monkeypatch.setenv("FRP_LOCAL_LLM_ACCESS_TOKEN", "x" * 64)
    monkeypatch.setenv("FRP_LOCAL_REVENUE_PDF", "/synthetic/not-real.pdf")
    monkeypatch.setattr(
        source_report_preview, "build_source_report",
        lambda *args, **kwargs: packet,
    )
    response = TestClient(app).post(
        "/api/v1/research/local-source-report",
        json={
            "report_key": router.REPORT_KEY,
            "answer_kind": "INNOVATIVE_SHARE_OF_DRUG_SALES",
        },
        headers={"x-frp-local-token": "x" * 64},
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "SOURCE_UNAVAILABLE"}
