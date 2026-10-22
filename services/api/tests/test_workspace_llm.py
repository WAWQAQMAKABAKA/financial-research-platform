"""Offline synthetic tests. Never store original document reference answers."""
import json
from hashlib import sha256

import httpx
import pytest

from app.modules.financial_report_analyst import source_workspace as sw, workspace_llm as wl


def source(key="600276-2026H1"):
    e=sw.REPORTS[key]
    s=e.source
    rid=sha256((s.document_id+"|"+s.canonical_sha256+"|consolidated-source-workspace-v1").encode()).hexdigest()
    return {
        "status":"SOURCE_DRAFT_READY", "report_key":key, "report_id":rid,
        "document_id":s.document_id, "ticker":s.ticker, "report_period":s.report_period,
        "issuer_name":e.issuer_name, "source_url":s.source_url,
        "source_sha256":s.source_sha256,"canonical_sha256":s.canonical_sha256,
        "research_publication":"BLOCKED", "financial_semantic_review":"NOT_PERFORMED",
        "observations":[{
            "claim_id":"SRC1", "evidence_id":"synthetic-e1",
            "statement_type_candidate":"consolidated_income_statement",
            "statement_title":"合并利润表 ", "row_label":e.row_label,
            "column_header":e.column_header,"value_verbatim":"1,234.56",
            "page_number":11,"cell_bbox_pt":[10.0,11.0,20.0,21.0],
            "source_text_span_status":"NOT_PROVEN_FROM_TABLE_GEOMETRY",
            "review_scope":"LITERAL_CELL_LOCATION_ONLY",
        }],
        "claims":[{"claim_id":"SRC1","kind":"OBSERVED_FACT","evidence_ids":["synthetic-e1"]}],
        "reviews":[{"claim_id":"SRC1","verdict":"ADMIT",
                    "rationale":"LITERAL_CELL_AND_HEADING_SOURCE_CHECK_ONLY"}],
    }


def provider_result(source_draft, mutation=None):
    x=source_draft["observations"][0]
    proposed={
        "claim_id":"DS1", "evidence_id":x["evidence_id"],
        "statement_kind":x["statement_type_candidate"],
        "statement_title":x["statement_title"], "row_label":x["row_label"],
        "column_header":x["column_header"], "value":x["value_verbatim"],
    }
    if mutation:mutation(proposed)
    return {"model":"deepseek-flash",
            "choices":[{"finish_reason":"stop","message":{"content":json.dumps({"claim":proposed},ensure_ascii=False)}}],
            "usage":{"prompt_tokens":130,"completion_tokens":92,"total_tokens":222,
                     "prompt_cache_hit_tokens":0,"prompt_cache_miss_tokens":130}}


def client_for(result, calls):
    def handler(req):
        calls.append(req)
        assert req.url == "https://api.deepseek.com/chat/completions"
        assert req.headers["authorization"] == "Bearer synthetic-key"
        body=json.loads(req.content)
        assert body["stream"] is False and body["max_tokens"] == wl.MAX_OUTPUT_TOKENS
        assert body["thinking"] == {"type":"disabled"}
        assert "synthetic-key" not in req.content.decode()
        return httpx.Response(200,json=result)
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("report_key",sorted(sw.REPORTS))
def test_exact_source_one_claim_for_two_issuers(report_key):
    s=source(report_key); calls=[]
    with client_for(provider_result(s),calls) as client:
        out=wl.draft_one_source_answer(report_key,s,api_key="synthetic-key",client=client)
    assert len(calls)==1
    assert out["status"]=="LLM_PROPOSAL_PACKET_MATCHED"
    assert out["report_key"]==report_key
    assert out["claims"][0]["value_verbatim"]=="1,234.56"
    assert out["claims"][0]["source_page"]==11
    assert out["usage"]["total_tokens"]==222
    assert out["research_publication"]=="BLOCKED"
    assert out["financial_semantic_review"]=="NOT_PERFORMED"


@pytest.mark.parametrize("change",[
    lambda s:s.update(report_id="0"*64),
    lambda s:s.update(canonical_sha256="0"*64),
    lambda s:s.update(source_sha256="0"*64),
    lambda s:s.update(source_url="https://example.test/not-source.pdf"),
    lambda s:s.update(research_publication="ALLOWED"),
    lambda s:s.update(financial_semantic_review="ADMIT"),
    lambda s:s["observations"][0].update(evidence_id="relabelled"),
    lambda s:s["observations"][0].update(statement_type_candidate="parent_income_statement"),
    lambda s:s["observations"][0].update(row_label="another metric"),
    lambda s:s["observations"][0].update(value_verbatim="not-a-number"),
    lambda s:s["observations"][0].update(page_number=0),
    lambda s:s["reviews"][0].update(verdict="UNCERTAIN"),
])
def test_unqualified_source_causes_no_network(change):
    s=source();change(s);calls=[]
    with client_for(provider_result(source()),calls) as client:
        out=wl.draft_one_source_answer("600276-2026H1",s,api_key="synthetic-key",client=client)
    assert out["status"]=="WITHHELD" and out["claims"]==[]
    assert calls==[]


def test_unknown_report_never_calls_provider():
    s=source();calls=[]
    with client_for(provider_result(s),calls) as client:
        out=wl.draft_one_source_answer("600000-2026H1",s,api_key="synthetic-key",client=client)
    assert out["status"]=="WITHHELD" and calls==[]


@pytest.mark.parametrize("field,bad",[
    ("evidence_id","invented"),("statement_kind","parent_income_statement"),
    ("row_label","另一指标"),("column_header","2025 年半年度"),
    ("value","1,234.57"),("claim_id","OTHER"),
    ("statement_title","母公司利润表"),
])
def test_bad_model_proposal_fails_closed(field,bad):
    s=source();calls=[]
    with client_for(provider_result(s,lambda p:p.update({field:bad})),calls) as client:
        out=wl.draft_one_source_answer("600276-2026H1",s,api_key="synthetic-key",client=client)
    assert out["status"]=="WITHHELD" and out["reason"]=="LLM_SOURCE_BINDING_MISMATCH"
    assert out["research_publication"]=="BLOCKED" and len(calls)==1


def test_truncated_response_withheld():
    s=source();r=provider_result(s);r["choices"][0]["finish_reason"]="length"
    with client_for(r,[]) as client:
        out=wl.draft_one_source_answer("600276-2026H1",s,api_key="synthetic-key",client=client)
    assert out["status"]=="WITHHELD"


def test_unexpected_model_and_bad_usage_withheld():
    s=source()
    for change in (lambda r:r.update(model="unexpected"),lambda r:r["usage"].update(total_tokens=1)):
        r=provider_result(s);change(r)
        with client_for(r,[]) as client:
            out=wl.draft_one_source_answer("600276-2026H1",s,api_key="synthetic-key",client=client)
        assert out["status"]=="WITHHELD"


def test_provider_failure_sanitized():
    s=source()
    with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(401,text="secret data"))) as client:
        out=wl.draft_one_source_answer("600276-2026H1",s,api_key="synthetic-key",client=client)
    assert out["status"]=="WITHHELD" and out["reason"]=="PROVIDER_HTTP_ERROR"
    assert "secret" not in repr(out)


def test_bad_response_shape_fail_closed():
    s=source();r=provider_result(s);r["choices"][0]["message"]["content"]='{"claim":{"unexpected":true}}'
    with client_for(r,[]) as client:
        out=wl.draft_one_source_answer("600276-2026H1",s,api_key="synthetic-key",client=client)
    assert out["status"]=="WITHHELD" and out["claims"]==[]
