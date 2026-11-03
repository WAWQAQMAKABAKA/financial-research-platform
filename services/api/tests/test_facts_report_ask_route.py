"""M2a question route: dev-only access control and response shape."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

TOKEN = "m1-local-dev-token-0123456789abcdef"
PDF = Path(__file__).resolve().parents[3] / "data/raw/600760/2026H1/source.pdf"
URL = "/api/v1/research/reports/600760-2026H1/ask"
QUESTION = "中航沈飞2026年半年度合并利润表中营业收入是多少？"


def authorize(monkeypatch, pdf: str | None = "auto") -> None:
    monkeypatch.setenv("FRP_LOCAL_FACTS_REPORT", "1")
    monkeypatch.setenv("FRP_LOCAL_LLM_ACCESS_TOKEN", TOKEN)
    monkeypatch.delenv("FRP_ENV", raising=False)
    monkeypatch.setenv(
        "FRP_LOCAL_SOURCE_PDF_600760",
        str(PDF) if pdf == "auto" else (pdf or ""),
    )


def ask(url: str = URL, token: str | None = TOKEN, question: str = QUESTION, **extra):
    headers = {} if token is None else {"x-frp-local-token": token}
    body = {"question": question, **extra}
    return TestClient(app).post(url, json=body, headers=headers)


def test_route_is_off_by_default(monkeypatch):
    monkeypatch.delenv("FRP_LOCAL_FACTS_REPORT", raising=False)
    assert ask().status_code == 404


def test_missing_or_wrong_token_is_refused(monkeypatch):
    authorize(monkeypatch)
    assert ask(token=None).status_code == 404
    assert ask(token="wrong-token-but-long-enough-000000").status_code == 404


def test_production_environment_is_refused(monkeypatch):
    authorize(monkeypatch)
    monkeypatch.setenv("FRP_ENV", "production")
    assert ask().status_code == 404


def test_unknown_and_legacy_reports_are_refused(monkeypatch):
    authorize(monkeypatch)
    assert ask("/api/v1/research/reports/999999-2026H1/ask").status_code == 404
    assert ask("/api/v1/research/reports/600276-2026H1/ask").status_code == 404


def test_missing_pdf_path_is_unavailable(monkeypatch):
    authorize(monkeypatch, pdf="")
    response = ask()
    assert response.status_code == 503
    assert response.json() == {"detail": "SOURCE_UNAVAILABLE"}


@pytest.mark.parametrize("question", ["", "x", "x" * 241])
def test_invalid_question_length_is_rejected(monkeypatch, question):
    authorize(monkeypatch)
    assert ask(question=question).status_code == 422


def test_extra_fields_are_rejected(monkeypatch):
    authorize(monkeypatch)
    assert ask(unexpected="value").status_code == 422


def test_authorized_question_returns_verified_facts(monkeypatch):
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    authorize(monkeypatch)

    response = ask()
    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "REPORT_READY"
    assert report["report_type"] == "FACTS_ONLY_QUESTION_REPORT"
    assert report["facts"][0]["value_verbatim"] == "6,191,107,217.36"
    assert report["publication"]["research_publication"] == "FACTS_ONLY"
