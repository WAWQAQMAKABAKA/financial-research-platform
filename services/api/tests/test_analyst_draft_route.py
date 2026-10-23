"""M1.10B offline route-boundary tests. No PDF or model requests."""
import pytest
from fastapi.testclient import TestClient

from app import main as api
from app.modules.financial_report_analyst import analyst_claim_review

TOKEN = "synthetic-review-token-" + "x" * 40
PATH = "/api/v1/research/local-analyst-draft-review"
REQUEST = {
    "report_key": "600276-2026H1",
    "candidate_text": "Management expects innovative-drug sales to accelerate.",
}


@pytest.fixture
def client():
    return TestClient(api.app)


def enable(monkeypatch):
    monkeypatch.setenv("FRP_LOCAL_ANALYST_REVIEW_UI", "1")
    monkeypatch.setenv("FRP_LOCAL_LLM_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv(
        "FRP_LOCAL_REVENUE_PDF",
        "/tmp/synthetic-analyst-source.pdf",
    )


def post(client, payload=None, token=TOKEN):
    return client.post(
        PATH,
        json=REQUEST if payload is None else payload,
        headers={"x-frp-local-token": token},
    )


def test_disabled_by_default(client, monkeypatch):
    monkeypatch.delenv("FRP_LOCAL_ANALYST_REVIEW_UI", raising=False)
    assert post(client).status_code == 404


@pytest.mark.parametrize("token", ["", "incorrect"])
def test_invalid_token(client, monkeypatch, token):
    enable(monkeypatch)
    assert post(client, token=token).status_code == 404


@pytest.mark.parametrize("payload", [
    {
        "report_key": "600760-2026H1",
        "candidate_text": "Example",
    },
    {
        "report_key": "600276-2026H1",
        "candidate_text": "x" * 401,
    },
    {
        "report_key": "600276-2026H1",
        "candidate_text": "Example",
        "evidence_id": "FORGED",
    },
])
def test_unsupported_request(client, monkeypatch, payload):
    enable(monkeypatch)
    assert post(client, payload).status_code == 422


def test_missing_pdf_configuration(client, monkeypatch):
    enable(monkeypatch)
    monkeypatch.delenv("FRP_LOCAL_REVENUE_PDF")
    assert post(client).status_code == 503


def test_candidate_bound_on_server(client, monkeypatch):
    enable(monkeypatch)

    def fake_review(path, candidate_text, *, as_of):
        assert str(path) == "/tmp/synthetic-analyst-source.pdf"
        assert candidate_text == REQUEST["candidate_text"]
        assert as_of.utcoffset() is not None
        return {
            "status": "UNPUBLISHED_ANALYST_CANDIDATE_REVIEWED",
            "research_publication": "BLOCKED",
        }

    monkeypatch.setattr(
        analyst_claim_review, "review_analyst_draft", fake_review
    )

    result = post(client)
    assert result.status_code == 200
    assert result.json()["research_publication"] == "BLOCKED"


def test_source_error_sanitized(client, monkeypatch):
    enable(monkeypatch)

    def unavailable(*args, **kwargs):
        raise ValueError("PRIVATE_PDF_OR_SOURCE_DETAIL")

    monkeypatch.setattr(
        analyst_claim_review, "review_analyst_draft", unavailable
    )

    result = post(client)
    assert result.status_code == 503
    assert result.json()["detail"] == "SOURCE_UNAVAILABLE"
    assert "PRIVATE_PDF_OR_SOURCE_DETAIL" not in result.text
