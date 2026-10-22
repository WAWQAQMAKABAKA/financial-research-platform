"""Offline M1.8A route enforcement; no original PDF and no network calls."""
from fastapi.testclient import TestClient

from app import main
from app.modules.financial_report_analyst import multi_evidence, revenue_scope

PATH = "/api/v1/research/local-source-answer"
HEADERS = {"x-frp-local-token": "synthetic-session-token-never-a-real-credential"}
PAYLOAD = {"report_key": "600276-2026H1",
           "question_code": "revenue_rows_two_scopes_2026H1"}


def env(monkeypatch):
    monkeypatch.setenv("FRP_LOCAL_LLM_UI", "1")
    monkeypatch.setenv("FRP_LOCAL_SOURCE_WORKSPACE", "1")
    monkeypatch.setenv("FRP_LOCAL_LLM_ACCESS_TOKEN", HEADERS["x-frp-local-token"])
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-api-key")
    monkeypatch.setenv("FRP_LOCAL_SOURCE_PDF_600276", "/synthetic.pdf")
    monkeypatch.setattr(main, "_LOCAL_LLM_COUNT", 0)


def test_two_scope_question_off_by_default(monkeypatch):
    monkeypatch.delenv("FRP_LOCAL_LLM_UI", raising=False)
    assert TestClient(main.app).post(PATH, json=PAYLOAD, headers=HEADERS).status_code == 404


def test_two_scope_question_only_allowed_for_hengrui(monkeypatch):
    env(monkeypatch)
    p = {**PAYLOAD, "report_key": "600760-2026H1"}
    assert TestClient(main.app).post(PATH, json=p, headers=HEADERS).status_code == 422
    assert main._LOCAL_LLM_COUNT == 0


def test_wrong_token_never_spends(monkeypatch):
    env(monkeypatch)
    assert TestClient(main.app).post(PATH, json=PAYLOAD).status_code == 404
    assert main._LOCAL_LLM_COUNT == 0


def test_model_runs_only_after_two_cell_pdf_review_without_pdf_lock(monkeypatch):
    env(monkeypatch)
    states = []
    def source(*args, **kwargs):
        states.append(("source", main._PDF_REQUEST_LOCK.locked()))
        return {"status": "SOURCE_DRAFT_READY"}
    def model(*args, **kwargs):
        states.append(("model", main._PDF_REQUEST_LOCK.locked()))
        assert kwargs["api_key"] == "synthetic-api-key"
        return {"status": "WITHHELD", "claims": [], "research_publication": "BLOCKED"}
    monkeypatch.setattr(revenue_scope, "build_source_draft", source)
    monkeypatch.setattr(multi_evidence, "draft_two_source_brief", model)
    response = TestClient(main.app).post(PATH, json=PAYLOAD, headers=HEADERS)
    assert response.status_code == 200
    assert states == [("source", True), ("model", False)]
    assert main._LOCAL_LLM_COUNT == 1


def test_unqualified_two_cell_source_never_spends(monkeypatch):
    env(monkeypatch)
    monkeypatch.setattr(revenue_scope, "build_source_draft",
                        lambda *args, **kwargs: {"status": "WITHHELD"})
    def no_model(*args, **kwargs):
        raise AssertionError("MODEL_CALLED_WITH_UNQUALIFIED_SOURCE")
    monkeypatch.setattr(multi_evidence, "draft_two_source_brief", no_model)
    response = TestClient(main.app).post(PATH, json=PAYLOAD, headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["claims"] == []
    assert main._LOCAL_LLM_COUNT == 0
