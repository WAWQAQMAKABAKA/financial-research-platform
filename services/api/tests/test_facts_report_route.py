"""M1 facts-only report route: dev-only access control and fail-closed shape."""
from pathlib import Path
import shutil

import pytest
from fastapi.testclient import TestClient

from app.main import app

TOKEN = "m1-local-dev-token-0123456789abcdef"
PDF = Path(__file__).resolve().parents[3] / "data/raw/600760/2026H1/source.pdf"
URL = "/api/v1/research/reports/600760-2026H1"


def authorize(monkeypatch, pdf: str | None = "auto") -> None:
    monkeypatch.setenv("FRP_LOCAL_FACTS_REPORT", "1")
    monkeypatch.setenv("FRP_LOCAL_LLM_ACCESS_TOKEN", TOKEN)
    monkeypatch.delenv("FRP_ENV", raising=False)
    monkeypatch.setenv(
        "FRP_LOCAL_SOURCE_PDF_600760",
        str(PDF) if pdf == "auto" else (pdf or ""),
    )


def get(url: str = URL, token: str | None = TOKEN):
    headers = {} if token is None else {"x-frp-local-token": token}
    return TestClient(app).get(url, headers=headers)


def test_route_is_off_by_default(monkeypatch):
    monkeypatch.delenv("FRP_LOCAL_FACTS_REPORT", raising=False)
    assert get().status_code == 404


def test_missing_token_is_refused(monkeypatch):
    authorize(monkeypatch)
    assert get(token=None).status_code == 404


def test_wrong_token_is_refused(monkeypatch):
    authorize(monkeypatch)
    assert get(token="wrong-token-but-long-enough-000000").status_code == 404


def test_short_server_secret_is_refused(monkeypatch):
    authorize(monkeypatch)
    monkeypatch.setenv("FRP_LOCAL_LLM_ACCESS_TOKEN", "short")
    assert get(token="short").status_code == 404


@pytest.mark.parametrize("env", ["production", "PROD", "staging"])
def test_production_like_environment_is_refused(monkeypatch, env):
    authorize(monkeypatch)
    monkeypatch.setenv("FRP_ENV", env)
    assert get().status_code == 404


def test_unknown_and_legacy_reports_are_refused(monkeypatch):
    authorize(monkeypatch)
    assert get("/api/v1/research/reports/999999-2026H1").status_code == 404
    assert get("/api/v1/research/reports/600276-2026H1").status_code == 404


def test_missing_pdf_path_is_unavailable(monkeypatch):
    authorize(monkeypatch, pdf="")
    response = get()
    assert response.status_code == 503
    assert response.json() == {"detail": "SOURCE_UNAVAILABLE"}


def test_altered_pdf_is_unavailable_without_leaking_details(monkeypatch, tmp_path):
    authorize(monkeypatch)
    altered = tmp_path / "altered.pdf"
    shutil.copyfile(PDF, altered)
    body = bytearray(altered.read_bytes())
    body[1024] ^= 0xFF
    altered.write_bytes(body)
    monkeypatch.setenv("FRP_LOCAL_SOURCE_PDF_600760", str(altered))

    response = get()
    assert response.status_code == 503
    assert response.json() == {"detail": "SOURCE_UNAVAILABLE"}
    assert "altered" not in response.text
    assert "sha256" not in response.text.lower()


def test_authorized_request_returns_a_facts_only_report(monkeypatch):
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    authorize(monkeypatch)

    response = get()
    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "REPORT_READY"
    assert report["publication"]["research_publication"] == "FACTS_ONLY"
    assert report["facts"][0]["value_verbatim"] == "6,191,107,217.36"
    assert report["facts"][0]["citation"]["page_number"] == 46
