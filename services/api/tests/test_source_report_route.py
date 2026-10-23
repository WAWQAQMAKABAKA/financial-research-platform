"""M112 offline FastAPI report-route tests; synthetic inputs only."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.financial_report_analyst import source_report_preview

PATH = "/api/v1/research/local-source-report"
TOKEN = "synthetic-m112-token-" + "x" * 40
REQUEST = {"report_key": "600276-2026H1"}


@pytest.fixture
def client():
    return TestClient(app)


def enabled(monkeypatch):
    monkeypatch.setenv("FRP_LOCAL_REPORT_PREVIEW_UI", "1")
    monkeypatch.setenv("FRP_LOCAL_LLM_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv(
        "FRP_LOCAL_REVENUE_PDF", "/offline-synthetic-report.pdf",
    )


def post(client, payload=None, token=TOKEN):
    return client.post(
        PATH,
        json=REQUEST if payload is None else payload,
        headers={"x-frp-local-token": token},
    )


def test_disabled_by_default(client, monkeypatch):
    monkeypatch.delenv("FRP_LOCAL_REPORT_PREVIEW_UI", raising=False)
    assert post(client).status_code == 404


@pytest.mark.parametrize("token", ["", "incorrect"])
def test_missing_or_invalid_token(client, monkeypatch, token):
    enabled(monkeypatch)
    assert post(client, token=token).status_code == 404


@pytest.mark.parametrize("payload", [
    {"report_key": "600760-2026H1"},
    {"report_key": "600276-2026H1", "pdf_path": "/tmp/forged.pdf"},
    {"report_key": "600276-2026H1", "publish": True},
])
def test_unsupported_inputs(client, monkeypatch, payload):
    enabled(monkeypatch)
    assert post(client, payload).status_code == 422


def test_missing_source_configuration(client, monkeypatch):
    enabled(monkeypatch)
    monkeypatch.delenv("FRP_LOCAL_REVENUE_PDF")
    response = post(client)
    assert response.status_code == 503
    assert response.json() == {"detail": "SOURCE_UNAVAILABLE"}


def test_backend_owns_source_and_as_of(client, monkeypatch):
    enabled(monkeypatch)

    def fake_report(pdf_path, *, as_of):
        assert str(pdf_path) == "/offline-synthetic-report.pdf"
        assert as_of.utcoffset() is not None
        return {
            "status": "LOCAL_SOURCE_REPORT_READY",
            "research_publication": "BLOCKED",
            "financial_semantic_review": "NOT_PERFORMED",
            "report_storage": "NOT_PERSISTED",
        }

    monkeypatch.setattr(
        source_report_preview, "build_source_report", fake_report,
    )
    response = post(client)
    assert response.status_code == 200
    assert response.json()["research_publication"] == "BLOCKED"


@pytest.mark.parametrize("field,value", [
    ("status", "UNQUALIFIED"),
    ("research_publication", "PUBLISHED"),
    ("financial_semantic_review", "APPROVED"),
    ("report_storage", "PERSISTED"),
])
def test_invalid_report_gates_blocked(
    client, monkeypatch, field, value,
):
    enabled(monkeypatch)
    packet = {
        "status": "LOCAL_SOURCE_REPORT_READY",
        "research_publication": "BLOCKED",
        "financial_semantic_review": "NOT_PERFORMED",
        "report_storage": "NOT_PERSISTED",
    }
    packet[field] = value

    monkeypatch.setattr(
        source_report_preview,
        "build_source_report",
        lambda *args, **kwargs: packet,
    )
    response = post(client)
    assert response.status_code == 503
    assert response.json() == {"detail": "SOURCE_UNAVAILABLE"}


def test_source_failure_does_not_expose_details(client, monkeypatch):
    enabled(monkeypatch)

    def fail(*args, **kwargs):
        raise ValueError("PRIVATE_SOURCE_PATH_OR_TEXT")

    monkeypatch.setattr(
        source_report_preview, "build_source_report", fail,
    )
    response = post(client)
    assert response.status_code == 503
    assert response.json() == {"detail": "SOURCE_UNAVAILABLE"}
    assert "PRIVATE_SOURCE_PATH_OR_TEXT" not in response.text
