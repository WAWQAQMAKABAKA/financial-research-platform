"""M1.8B network-free API authentication, source, paid budget and PDF-lock checks."""
from fastapi.testclient import TestClient

from app import main
from app.modules.financial_report_analyst import management_brief, management_evidence, revenue_scope

PATH = "/api/v1/research/local-source-answer"
DATA = {"report_key":"600276-2026H1","question_code":management_brief.QUESTION_CODE}
TOKEN = "synthetic-local-credential-not-a-provider-key"
HEAD = {"x-frp-local-token":TOKEN}


def config(monkeypatch):
    monkeypatch.setenv("FRP_LOCAL_LLM_UI","1")
    monkeypatch.setenv("FRP_LOCAL_SOURCE_WORKSPACE","1")
    monkeypatch.setenv("FRP_LOCAL_LLM_ACCESS_TOKEN",TOKEN)
    monkeypatch.setenv("DEEPSEEK_API_KEY","synthetic-provider-key")
    monkeypatch.setenv("FRP_LOCAL_SOURCE_PDF_600276","/synthetic.pdf")
    monkeypatch.setattr(main,"_LOCAL_LLM_COUNT",0)


def test_new_code_disabled_by_default(monkeypatch):
    config(monkeypatch)
    monkeypatch.delenv("FRP_LOCAL_LLM_UI",raising=False)
    assert TestClient(main.app).post(PATH,json=DATA,headers=HEAD).status_code == 404


def test_new_code_requires_session_secret(monkeypatch):
    config(monkeypatch)
    assert TestClient(main.app).post(PATH,json=DATA).status_code == 404
    assert main._LOCAL_LLM_COUNT == 0


def test_new_code_only_supports_hengrui(monkeypatch):
    config(monkeypatch)
    result = TestClient(main.app).post(PATH,json={**DATA,"report_key":"600760-2026H1"},headers=HEAD)
    assert result.status_code == 422
    assert main._LOCAL_LLM_COUNT == 0


def test_source_before_paid_call_and_pdf_lock_released(monkeypatch):
    config(monkeypatch)
    events = []
    def two(*args,**kwargs):
        events.append(("cells",main._PDF_REQUEST_LOCK.locked()))
        return {"status":"SOURCE_DRAFT_READY"}
    def management(*args,**kwargs):
        events.append(("management",main._PDF_REQUEST_LOCK.locked()))
        return {"status":"SOURCE_PASSAGE_REVIEWED"}
    def model(*args,**kwargs):
        events.append(("model",main._PDF_REQUEST_LOCK.locked()))
        assert kwargs["api_key"] == "synthetic-provider-key"
        return {"status":"WITHHELD","claims":[],"research_publication":"BLOCKED"}
    monkeypatch.setattr(revenue_scope,"build_source_draft",two)
    monkeypatch.setattr(management_evidence,"locate_management_excerpt",management)
    monkeypatch.setattr(management_brief,"draft_management_brief",model)
    resp = TestClient(main.app).post(PATH,json=DATA,headers=HEAD)
    assert resp.status_code == 200
    assert events == [("cells",True),("management",True),("model",False)]
    assert main._LOCAL_LLM_COUNT == 1


def test_failed_passage_never_spends(monkeypatch):
    config(monkeypatch)
    monkeypatch.setattr(revenue_scope,"build_source_draft",lambda *a,**k:{"status":"SOURCE_DRAFT_READY"})
    def fail(*a,**k):
        raise ValueError("source passage cannot be verified")
    monkeypatch.setattr(management_evidence,"locate_management_excerpt",fail)
    monkeypatch.setattr(management_brief,"draft_management_brief",lambda *a,**k: (_ for _ in ()).throw(AssertionError("PAID")))
    resp=TestClient(main.app).post(PATH,json=DATA,headers=HEAD)
    assert resp.status_code in (200,503)
    assert main._LOCAL_LLM_COUNT == 0


def test_invalid_extra_question_never_spends(monkeypatch):
    config(monkeypatch)
    resp=TestClient(main.app).post(PATH,json={**DATA,"prompt":"trade please"},headers=HEAD)
    assert resp.status_code == 422
    assert main._LOCAL_LLM_COUNT == 0
