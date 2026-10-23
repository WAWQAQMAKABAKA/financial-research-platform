"""Local-only M1.9C route boundary tests; no PDF or model network call."""
import pytest
from fastapi.testclient import TestClient

from app import main as api
from app.modules.financial_report_analyst import claim_review_preview

TOKEN = "synthetic-local-token-" + "x" * 40
PATH = "/api/v1/research/local-claim-review"
REQUEST = {
    "report_key": "600276-2026H1",
    "claim_code": "share_company_revenue",
}


@pytest.fixture
def client():
    return TestClient(api.app)


def enabled(monkeypatch):
    monkeypatch.setenv("FRP_LOCAL_CLAIM_REVIEW_UI", "1")
    monkeypatch.setenv("FRP_LOCAL_LLM_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv(
        "FRP_LOCAL_REVENUE_PDF",
        "/tmp/synthetic-review-source.pdf",
    )


def post(client, payload=REQUEST, token=TOKEN):
    return client.post(
        PATH,
        json=payload,
        headers={"x-frp-local-token": token},
    )


def test_disabled_by_default(client, monkeypatch):
    monkeypatch.delenv("FRP_LOCAL_CLAIM_REVIEW_UI", raising=False)
    assert post(client).status_code == 404


def test_missing_access_token(client, monkeypatch):
    enabled(monkeypatch)
    assert post(client, token="").status_code == 404
    assert post(client, token="incorrect").status_code == 404


def test_missing_pdf_configuration(client, monkeypatch):
    enabled(monkeypatch)
    monkeypatch.delenv("FRP_LOCAL_REVENUE_PDF")
    assert post(client).status_code == 503


@pytest.mark.parametrize("payload", [
    {"report_key": "600760-2026H1", "claim_code": "share_company_revenue"},
    {"report_key": "600276-2026H1", "claim_code": "unsupported"},
    {
        "report_key": "600276-2026H1",
        "claim_code": "share_company_revenue",
        "extra": "not-allowed",
    },
])
def test_unsupported_input_rejected(client, monkeypatch, payload):
    enabled(monkeypatch)
    assert post(client, payload).status_code == 422


def test_local_source_review_response(client, monkeypatch):
    enabled(monkeypatch)

    def fake_preview(path, claim_code, *, as_of):
        assert str(path) == "/tmp/synthetic-review-source.pdf"
        assert claim_code == "share_company_revenue"
        assert as_of.utcoffset() is not None
        return {
            "status": "LOCAL_CLAIM_REVIEW_READY",
            "research_publication": "BLOCKED",
        }

    monkeypatch.setattr(claim_review_preview, "build_preview", fake_preview)

    response = post(client)
    assert response.status_code == 200
    assert response.json()["research_publication"] == "BLOCKED"


def test_source_failure_not_exposed(client, monkeypatch):
    enabled(monkeypatch)

    def unavailable(*args, **kwargs):
        raise ValueError("PRIVATE_SOURCE_DETAIL_MUST_NOT_LEAK")

    monkeypatch.setattr(claim_review_preview, "build_preview", unavailable)

    response = post(client)
    assert response.status_code == 503
    assert "PRIVATE_SOURCE_DETAIL" not in response.text
    assert response.json()["detail"] == "SOURCE_UNAVAILABLE"
