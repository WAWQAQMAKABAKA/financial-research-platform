"""M119A offline checks: mock provider only; no paid calls or PDFs."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.main import app
from app.modules.financial_report_analyst import live_question_intent as intent

PATH = "/api/v1/research/local-question-intent"
QUESTION = "恒瑞医药2026年上半年合并营业收入是多少？"
TOKEN = "synthetic-frp-m119-" + "x" * 40


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "_M119A_INTENT_COUNT", 0)
    return TestClient(app)


def enabled(monkeypatch):
    monkeypatch.setenv("FRP_LOCAL_QUESTION_INTENT_UI", "1")
    monkeypatch.setenv("FRP_LOCAL_LLM_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-not-a-real-key")


def post(client, question=QUESTION, token=TOKEN):
    return client.post(
        PATH,
        json={"report_key": "600276-2026H1", "question": question},
        headers={"x-frp-local-token": token},
    )


def test_disabled(client, monkeypatch):
    monkeypatch.delenv("FRP_LOCAL_QUESTION_INTENT_UI", raising=False)
    assert post(client).status_code == 404


def test_invalid_token(client, monkeypatch):
    enabled(monkeypatch)
    assert post(client, token="incorrect").status_code == 404


def test_source_scope_gate_blocks_provider_call(client, monkeypatch):
    enabled(monkeypatch)
    def no_paid_call(*args, **kwargs):
        raise AssertionError("MUST_NOT_INVOKE_PROVIDER")
    monkeypatch.setattr(intent, "propose", no_paid_call)
    r = post(client, question="我今天应该买入多少股票？")
    assert r.status_code == 200
    assert r.json()["status"] == "WITHHELD"
    assert r.json()["research_publication"] == "BLOCKED"
    assert main._M119A_INTENT_COUNT == 0


def test_authenticated_route_uses_exact_question(client, monkeypatch):
    enabled(monkeypatch)
    def fake_propose(question, *, api_key):
        assert question == QUESTION
        assert api_key == "synthetic-not-a-real-key"
        return {
            "status": "INTENT_PROPOSAL_READY",
            "report_key": "600276-2026H1",
            "research_publication": "BLOCKED",
            "financial_semantic_review": "NOT_PERFORMED",
        }
    monkeypatch.setattr(intent, "propose", fake_propose)
    response = post(client)
    assert response.status_code == 200
    assert response.json()["research_publication"] == "BLOCKED"
    assert main._M119A_INTENT_COUNT == 1


def test_budget_enforced(client, monkeypatch):
    enabled(monkeypatch)
    monkeypatch.setattr(main, "_M119A_INTENT_COUNT", 4)
    assert post(client).status_code == 429


@pytest.mark.parametrize("question,allowed", [
    (QUESTION, True),
    ("What is Hengrui consolidated revenue for the first half of 2026?", True),
    ("恒瑞医药2026H1母公司营业收入是多少？", False),
    ("恒瑞创新药2026H1同比增长多少？", False),
    ("买入600276多少仓位？", False),
])
def test_narrow_source_scope(question, allowed):
    assert intent.in_current_source_scope(question) is allowed


def mock_provider(operation="LOOKUP", *, unresolved=None):
    content = {
        "operation": operation,
        "metric": "合并营业收入",
        "numerator": None,
        "denominator": None,
        "reporting_scope": "2026H1合并报表",
        "unresolved": [] if unresolved is None else unresolved,
    }
    def handler(request):
        body = json.loads(request.content)
        assert body["messages"][-1]["content"] == QUESTION
        assert body["model"] == "deepseek-flash"
        return httpx.Response(200, json={
            "model": "deepseek-flash",
            "choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps(content, ensure_ascii=False),
            }}],
        })
    return httpx.MockTransport(handler)


def test_valid_proposal_remains_unverified():
    with httpx.Client(transport=mock_provider(), trust_env=False) as client:
        result = intent.propose(QUESTION, api_key="synthetic", client=client)
    assert result["status"] == "INTENT_PROPOSAL_READY"
    assert result["report_key"] == "600276-2026H1"
    assert result["proposal"]["question"] == QUESTION
    assert result["proposal"]["operation_candidate"] == "LOOKUP"
    assert result["proposal"]["research_publication"] == "BLOCKED"
    assert result["financial_semantic_review"] == "NOT_PERFORMED"


def test_unsupported_model_operation_withheld():
    with httpx.Client(transport=mock_provider("FORECAST"), trust_env=False) as client:
        result = intent.propose(QUESTION, api_key="synthetic", client=client)
    assert result["status"] == "WITHHELD"
    assert result["research_publication"] == "BLOCKED"


def test_temporal_claim_is_never_approved():
    with httpx.Client(transport=mock_provider(
        unresolved=["2026 H1 may be in the future"],
    ), trust_env=False) as client:
        result = intent.propose(QUESTION, api_key="synthetic", client=client)
    assert result["status"] == "INTENT_PROPOSAL_READY"
    assert result["proposal"]["unresolved"]
    assert result["interpretation_status"] == "UNVERIFIED_PROPOSAL"
    assert result["research_publication"] == "BLOCKED"


def test_provider_error_sanitized():
    def handler(_request):
        return httpx.Response(503, text="SECRET_TOKEN_SHOULD_NOT_LEAK")
    with httpx.Client(
        transport=httpx.MockTransport(handler), trust_env=False,
    ) as client:
        result = intent.propose(QUESTION, api_key="synthetic", client=client)
    assert result["status"] == "WITHHELD"
    assert "SECRET_TOKEN" not in str(result)


def test_malformed_json_withheld():
    def handler(_request):
        return httpx.Response(200, json={
            "model": "deepseek-flash",
            "choices": [{"finish_reason": "stop", "message": {
                "content": '{"operation":"LOOKUP"}',
            }}],
        })
    with httpx.Client(
        transport=httpx.MockTransport(handler), trust_env=False,
    ) as client:
        result = intent.propose(QUESTION, api_key="synthetic", client=client)
    assert result["status"] == "WITHHELD"
    assert result["research_publication"] == "BLOCKED"
