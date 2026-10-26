"""M124 offline synthetic checks. No protected GT, original facts, or live LLM calls."""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient

from app.modules.financial_report_analyst import retrieval_analyst as analyst
from app.modules.financial_report_analyst import canonical_retrieval
from test_canonical_retrieval import synthetic_document
from app.main import app

WHEN = datetime(2026, 10, 25, 12, tzinfo=ZoneInfo("Asia/Shanghai"))
QUESTION = "创新药销售收入和研发有什么进展？"
TOKEN = "synthetic-m124-" + "x" * 48
ROUTE = "/api/v1/research/local-retrieval-analyst"


def packet():
    source, document = synthetic_document()
    result = canonical_retrieval.retrieve_from_canonical(
        source, document, QUESTION, as_of=WHEN,
    )
    assert len(result["evidence"]) >= 2
    assert len({x["source_page"] for x in result["evidence"]}) >= 2
    return source, result


def model_response(pkt, mutate=None):
    item = next(hit for hit in pkt["evidence"] if "创新药" in hit["source_excerpt"])
    claim = {
        "claim_id": "C1", "evidence_id": item["evidence_id"],
        "text": "公告披露创新药销售收入和研发进展。",
        "quote": "管理层讨论创新药销售收入和创新药研发进展。",
    }
    if mutate:
        mutate(claim)
    return {
        "model": "deepseek-flash",
        "choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps({"claims": [claim]}, ensure_ascii=False),
        }}],
        "usage": {"prompt_tokens": 200, "completion_tokens": 60, "total_tokens": 260,
                  "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 200},
    }


def mock_client(response, calls):
    def handler(req):
        calls.append(req)
        assert req.url.host == "api.deepseek.com"
        assert req.headers["authorization"] == "Bearer synthetic-key"
        request = json.loads(req.content)
        assert request["stream"] is False and request["temperature"] == 0
        assert request["thinking"] == {"type": "disabled"}
        assert len(request["messages"]) == 2
        assert "synthetic-key" not in req.content.decode()
        return httpx.Response(200, json=response)
    return httpx.Client(transport=httpx.MockTransport(handler))


def draft(source, pkt, client, key="synthetic-key"):
    return analyst.draft_from_verified_retrieval(
        source, pkt, QUESTION, as_of=WHEN, api_key=key, client=client,
    )


def test_one_model_call_builds_source_bound_unpublished_claim():
    source, pkt = packet()
    calls = []
    with mock_client(model_response(pkt), calls) as client:
        result = draft(source, pkt, client)
    assert len(calls) == 1
    assert result["status"] == "UNPUBLISHED_ANALYST_PREVIEW"
    assert result["research_publication"] == "BLOCKED"
    assert result["financial_semantic_review"] == "NOT_PERFORMED"
    assert result["claim_level_review"] == "UNCERTAIN_SEMANTICS_NOT_REVIEWED"
    assert result["claims"][0]["review"]["verdict"] == "UNCERTAIN"
    assert result["claims"][0]["evidence_id"] in {x["evidence_id"] for x in pkt["evidence"]}
    assert result["usage"]["total_tokens"] == 260


@pytest.mark.parametrize("change", [
    lambda p: p.update(source_sha256="0" * 64),
    lambda p: p.update(canonical_sha256="0" * 64),
    lambda p: p.update(document_id="forged"),
    lambda p: p.update(research_publication="PUBLISHED"),
    lambda p: p.update(statement_heading_alert="MULTIPLE_STATEMENT_HEADING_CANDIDATES"),
    lambda p: p.update(status="WITHHELD"),
    lambda p: p["evidence"][0].update(evidence_id="a" * 64),
    lambda p: p["evidence"].__setitem__(slice(1, None), []),
])
def test_invalid_or_mixed_scope_withheld_without_model_call(change):
    source, pkt = packet()
    change(pkt)
    calls = []
    with mock_client(model_response(packet()[1]), calls) as client:
        out = draft(source, pkt, client)
    assert out["status"] == "WITHHELD"
    assert out["claims"] == []
    assert calls == []


@pytest.mark.parametrize("mutation, expected", [
    (lambda c: c.update(evidence_id="f" * 64), "MODEL_CLAIMS_NOT_SOURCE_QUALIFIED"),
    (lambda c: c.update(quote="系统没有出现过的引用语句。"), "MODEL_CLAIMS_NOT_SOURCE_QUALIFIED"),
    (lambda c: c.update(text="公告披露创新药销售收入达到999亿元。"), "MODEL_CLAIMS_NOT_SOURCE_QUALIFIED"),
    (lambda c: c.update(text="合并营业收入包含创新药销售收入。"), "MODEL_CLAIMS_NOT_SOURCE_QUALIFIED"),
    (lambda c: c.update(text="建议买入该公司股票。"), "MODEL_CLAIMS_NOT_SOURCE_QUALIFIED"),
    (lambda c: c.update(claim_id="C4"), "MODEL_CLAIMS_NOT_SOURCE_QUALIFIED"),
])
def test_model_hallucinated_claims_withheld(mutation, expected):
    source, pkt = packet()
    calls = []
    with mock_client(model_response(pkt, mutation), calls) as client:
        out = draft(source, pkt, client)
    assert out["status"] == "WITHHELD" and out["reason"] == expected
    assert len(calls) == 1


def test_empty_model_claims_abstain():
    source, pkt = packet()
    response = model_response(pkt)
    response["choices"][0]["message"]["content"] = '{"claims":[]}'
    with mock_client(response, []) as client:
        out = draft(source, pkt, client)
    assert out["status"] == "WITHHELD"



def test_trading_request_rejected_before_model():
    source, pkt = packet()
    with pytest.raises(ValueError, match="TRADING_REQUEST_NOT_SUPPORTED"):
        analyst._validated_evidence(source, pkt, "现在应该买入多少仓位？", WHEN)


def test_no_model_key_causes_no_network():
    source, pkt = packet()
    calls = []
    with mock_client(model_response(pkt), calls) as client:
        out = draft(source, pkt, client, key="")
    assert out["status"] == "WITHHELD" and calls == []


def enabled(monkeypatch):
    monkeypatch.setenv("FRP_LOCAL_ANALYST_PREVIEW_UI", "1")
    monkeypatch.setenv("FRP_LOCAL_LLM_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("FRP_LOCAL_REVENUE_PDF", "/offline-synthetic.pdf")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


def post(payload=None, token=TOKEN):
    return TestClient(app).post(ROUTE, json=payload or {
        "report_key": "600276-2026H1", "question": QUESTION,
    }, headers={"x-frp-local-token": token})


def test_api_default_disabled(monkeypatch):
    monkeypatch.delenv("FRP_LOCAL_ANALYST_PREVIEW_UI", raising=False)
    assert post().status_code == 404


def test_api_rejects_invalid_token(monkeypatch):
    enabled(monkeypatch)
    assert post(token="incorrect").status_code == 404


@pytest.mark.parametrize("payload", [
    {"report_key": "600760-2026H1", "question": QUESTION},
    {"report_key": "600276-2026H1", "question": QUESTION, "pdf_path": "/tmp/forged"},
    {"report_key": "600276-2026H1", "question": ""},
])
def test_api_forbids_untrusted_fields(monkeypatch, payload):
    enabled(monkeypatch)
    assert post(payload).status_code == 422


def test_api_scope_gate_before_paid_call(monkeypatch):
    enabled(monkeypatch)
    from app.modules.financial_report_analyst import revenue_scope
    source, pkt = packet()
    # Verify actual trusted source identity is checked inside model-bound API.
    pkt.update({
        "document_id": revenue_scope.SOURCE.document_id,
        "source_sha256": revenue_scope.SOURCE.source_sha256,
        "canonical_sha256": revenue_scope.SOURCE.canonical_sha256,
        "source_url": revenue_scope.SOURCE.source_url,
        "statement_heading_alert": "MULTIPLE_STATEMENT_HEADING_CANDIDATES",
    })
    monkeypatch.setattr(canonical_retrieval, "retrieve_report_evidence", lambda *a, **kw: pkt)
    response = post()
    assert response.status_code == 200
    assert response.json()["status"] == "WITHHELD"
    assert response.json()["research_publication"] == "BLOCKED"


def test_api_source_failure_sanitized(monkeypatch):
    enabled(monkeypatch)
    def fail(*_args, **_kwargs):
        raise ValueError("PRIVATE_PATH_OR_DOCUMENT_TEXT")
    monkeypatch.setattr(canonical_retrieval, "retrieve_report_evidence", fail)
    response = post()
    assert response.status_code == 503
    assert response.json() == {"detail": "SOURCE_UNAVAILABLE"}
    assert "PRIVATE_PATH_OR_DOCUMENT_TEXT" not in response.text


@pytest.mark.parametrize("mutation,code", [
    (lambda c: c.update(quote="完全不存在的支持性引用文本。"), "QUOTE_NOT_IN_SOURCE"),
    (lambda c: c.update(text="公司创新药销售达到999亿元。"), "NUMERIC_SUBSTITUTION"),
    (lambda c: c.update(text="合并报表披露了创新药销售。"), "ACCOUNTING_SCOPE_SUBSTITUTION"),
    (lambda c: c.update(evidence_id="f" * 64), "CLAIM_EVIDENCE_BINDING_INVALID"),
])
def test_failure_code_is_sanitized_and_source_gate_remains_closed(mutation, code):
    source, pkt = packet()
    response = model_response(pkt, mutation)
    calls = []
    with mock_client(response, calls) as client:
        result = draft(source, pkt, client)
    assert len(calls) == 1
    assert result["status"] == "WITHHELD"
    assert result["claims"] == []
    assert result["reason"] == "MODEL_CLAIMS_NOT_SOURCE_QUALIFIED"
    assert result["failure_code"] == code
    assert result["research_publication"] == "BLOCKED"
    assert result["financial_semantic_review"] == "NOT_PERFORMED"
    assert "完全不存在的支持性引用文本" not in repr(result)


def test_model_schema_failure_classified_without_leaking_model_content():
    source, pkt = packet()
    response = model_response(pkt)
    response["choices"][0]["message"]["content"] = '{"claims":[{"claim_id":"C1"}]}'
    with mock_client(response, []) as client:
        result = draft(source, pkt, client)
    assert result["status"] == "WITHHELD"
    assert result["reason"] == "MODEL_CLAIMS_NOT_SOURCE_QUALIFIED"
    assert result["failure_code"] == "MODEL_SCHEMA_INVALID"
    assert result["claims"] == []
