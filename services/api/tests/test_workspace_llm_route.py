"""Offline source-ask HTTP gate tests: no paid calls or original answer labels."""
from fastapi.testclient import TestClient
from app import main
from app.modules.financial_report_analyst import source_workspace, workspace_llm

PATH="/api/v1/research/local-source-answer"
PAYLOAD={"report_key":"600276-2026H1","question_code":"consolidated_revenue_2026H1"}
HEAD={"x-frp-local-token":"synthetic-strong-session-token-not-a-key"}


def configured(monkeypatch):
    monkeypatch.setenv("FRP_LOCAL_LLM_UI","1")
    monkeypatch.setenv("FRP_LOCAL_SOURCE_WORKSPACE","1")
    monkeypatch.setenv("FRP_LOCAL_LLM_ACCESS_TOKEN",HEAD["x-frp-local-token"])
    monkeypatch.setenv("DEEPSEEK_API_KEY","synthetic-key")
    monkeypatch.setenv("FRP_LOCAL_SOURCE_PDF_600276","/synthetic.pdf")
    monkeypatch.setattr(main,"_LOCAL_LLM_COUNT",0)


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("FRP_LOCAL_LLM_UI",raising=False)
    assert TestClient(main.app).post(PATH,json=PAYLOAD,headers=HEAD).status_code==404


def test_missing_or_bad_token_disallowed(monkeypatch):
    configured(monkeypatch)
    assert TestClient(main.app).post(PATH,json=PAYLOAD).status_code==404
    assert TestClient(main.app).post(PATH,json=PAYLOAD,headers={"x-frp-local-token":"bad"}).status_code==404
    assert main._LOCAL_LLM_COUNT==0


def test_reject_unlisted_question_and_extra_fields(monkeypatch):
    configured(monkeypatch)
    for data in ({**PAYLOAD,"question_code":"investment_advice"},
                 {**PAYLOAD,"prompt":"arbitrary"},
                 {**PAYLOAD,"report_key":"000001-2026H1"}):
        assert TestClient(main.app).post(PATH,json=data,headers=HEAD).status_code==422
    assert main._LOCAL_LLM_COUNT==0


def test_missing_source_never_spends(monkeypatch):
    configured(monkeypatch)
    monkeypatch.delenv("FRP_LOCAL_SOURCE_PDF_600276",raising=False)
    assert TestClient(main.app).post(PATH,json=PAYLOAD,headers=HEAD).status_code==503
    assert main._LOCAL_LLM_COUNT==0


def test_unqualified_source_never_spends(monkeypatch):
    configured(monkeypatch)
    monkeypatch.setattr(source_workspace,"build_source_workspace",lambda *a,**kw:{"status":"WITHHELD"})
    out=TestClient(main.app).post(PATH,json=PAYLOAD,headers=HEAD)
    assert out.status_code==200 and out.json()["claims"]==[]
    assert main._LOCAL_LLM_COUNT==0


def test_source_verified_before_network_pdf_lock_not_held_for_provider(monkeypatch):
    configured(monkeypatch)
    observed=[]
    def src(*args,**kw):
        observed.append(("source",main._PDF_REQUEST_LOCK.locked()))
        return {"status":"SOURCE_DRAFT_READY"}
    def model(*args,**kw):
        observed.append(("model",main._PDF_REQUEST_LOCK.locked()))
        assert kw["api_key"]=="synthetic-key"
        return {"status":"WITHHELD","claims":[],"research_publication":"BLOCKED"}
    monkeypatch.setattr(source_workspace,"build_source_workspace",src)
    monkeypatch.setattr(workspace_llm,"draft_one_source_answer",model)
    out=TestClient(main.app).post(PATH,json=PAYLOAD,headers=HEAD)
    assert out.status_code==200 and observed==[("source",True),("model",False)]
    assert main._LOCAL_LLM_COUNT==1


def test_four_call_budget_no_more(monkeypatch):
    configured(monkeypatch)
    monkeypatch.setattr(source_workspace,"build_source_workspace",lambda *a,**kw:{"status":"SOURCE_DRAFT_READY"})
    calls=[]
    def llm(*args,**kw):
        calls.append(1)
        return {"status":"WITHHELD","claims":[],"research_publication":"BLOCKED"}
    monkeypatch.setattr(workspace_llm,"draft_one_source_answer",llm)
    client=TestClient(main.app)
    assert all(client.post(PATH,json=PAYLOAD,headers=HEAD).status_code==200 for _ in range(4))
    assert client.post(PATH,json=PAYLOAD,headers=HEAD).status_code==429
    assert len(calls)==4
