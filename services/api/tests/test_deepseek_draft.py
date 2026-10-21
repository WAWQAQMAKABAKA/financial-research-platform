"""Network-free DeepSeek packet-binding tests. Values are synthetic, never source GT."""
import json
from hashlib import sha256

import httpx
import pytest

from app.modules.financial_report_analyst import deepseek_draft as ds
from app.modules.financial_report_analyst import revenue_scope as rv


def packet():
    observations = []
    claims = []
    reviews = []
    for i, selection in enumerate(rv.SELECTIONS):
        evidence_id = f"fake-evidence-{i+1}"
        claim_id = f"REV{i+1}"
        observations.append({
            "claim_id": claim_id, "evidence_id": evidence_id,
            "statement_type_candidate": selection["section_kind"],
            "statement_title": rv._STATEMENT_LABELS[selection["section_kind"]],
            "row_label": selection["row_label"],
            "column_header": selection["column_header"],
            "value_verbatim": f"{i+1},234.56",
            "page_number": 11 + i,
            "source_text_span_status": "NOT_PROVEN_FROM_TABLE_GEOMETRY",
            "review_scope": "LITERAL_CELL_LOCATION_ONLY",
        })
        claims.append({"claim_id": claim_id, "evidence_ids": [evidence_id],
                       "kind": "OBSERVED_FACT"})
        reviews.append({"claim_id": claim_id, "verdict": "ADMIT",
                        "rationale": "LITERAL_CELL_AND_HEADING_SOURCE_CHECK_ONLY"})
    report_id = sha256((rv.SOURCE.document_id + "|" + rv.SOURCE.canonical_sha256
                        + "|revenue-scope-preview-v1").encode()).hexdigest()
    return {
        "status": "SOURCE_DRAFT_READY", "question": rv.QUESTION,
        "report_id": report_id,
        "document_id": rv.SOURCE.document_id,
        "source_url": rv.SOURCE.source_url,
        "source_sha256": rv.SOURCE.source_sha256,
        "canonical_sha256": rv.SOURCE.canonical_sha256,
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED", "observations": observations,
        "claims": claims, "reviews": reviews,
    }


def response_for(source, *, mutation=None, usage=None, finish="stop", model=ds.MODEL):
    candidates = []
    for i, x in enumerate(source["observations"]):
        candidates.append({
            "claim_id": f"DS{i+1}", "evidence_id": x["evidence_id"],
            "statement_kind": x["statement_type_candidate"],
            "statement_title": x["statement_title"], "row_label": x["row_label"],
            "column_header": x["column_header"], "value": x["value_verbatim"],
        })
    if mutation:
        mutation(candidates)
    return {
        "model": model, "choices": [{"finish_reason": finish,
                                     "message": {"content": json.dumps({"claims": candidates}, ensure_ascii=False)}}],
        "usage": usage or {"prompt_tokens": 180, "completion_tokens": 160,
                           "total_tokens": 340, "prompt_cache_hit_tokens": 30,
                           "prompt_cache_miss_tokens": 150},
    }


def mock_client(result, *, calls=None):
    def handler(request):
        if calls is not None:
            calls.append(request)
        assert request.url == ds.ENDPOINT
        assert request.headers["authorization"] == "Bearer test-key"
        sent = json.loads(request.content)
        assert sent["model"] == ds.MODEL
        assert sent["thinking"] == {"type": "disabled"}
        assert sent["response_format"] == {"type": "json_object"}
        assert sent["max_tokens"] == ds.MAX_OUTPUT_TOKENS
        assert sent["stream"] is False
        assert len(sent["messages"]) == 2
        assert "test-key" not in request.content.decode()
        return httpx.Response(200, json=result)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_matching_proposals_are_exactly_bound_and_still_blocked():
    source = packet()
    calls = []
    with mock_client(response_for(source), calls=calls) as client:
        out = ds.draft_verified_cells(source, api_key="test-key", client=client)
    assert len(calls) == 1
    assert out["status"] == "LLM_PROPOSAL_PACKET_MATCHED"
    assert len(out["claims"]) == 2
    assert out["claims"][0]["evidence_id"] == "fake-evidence-1"
    assert out["claims"][1]["statement_kind"] == "parent_income_statement"
    assert out["financial_semantic_review"] == "NOT_PERFORMED"
    assert out["research_publication"] == "BLOCKED"
    assert out["usage"]["total_tokens"] == 340
    assert out["usage"]["estimated_cost_usd_high"] != "0"
    assert "test-key" not in repr(out)


@pytest.mark.parametrize("mutate", [
    lambda x: x[0].update(value="999,999.99"),
    lambda x: x[1].update(statement_kind="consolidated_income_statement"),
    lambda x: x[0].update(evidence_id="invented"),
    lambda x: x[0].update(column_header="prior year"),
    lambda x: x.reverse(),
    lambda x: x[0].update(arbitrary_explanation="Financial performance rose"),
    lambda x: x.pop(),
])
def test_hallucination_or_ambiguous_claims_are_withheld(mutate):
    source = packet()
    with mock_client(response_for(source, mutation=mutate)) as client:
        out = ds.draft_verified_cells(source, api_key="test-key", client=client)
    assert out["status"] == "WITHHELD"
    assert out["claims"] == []
    assert out["research_publication"] == "BLOCKED"
    assert out["usage"]["total_tokens"] == 340


@pytest.mark.parametrize("tamper", [
    lambda x: x.update(financial_semantic_review="APPROVED"),
    lambda x: x.update(research_publication="PUBLISHED"),
    lambda x: x.update(source_sha256="0" * 64),
    lambda x: x["reviews"][0].update(verdict="UNCERTAIN"),
    lambda x: x["claims"][0].update(evidence_ids=["other"]),
    lambda x: x["observations"][0].update(value_verbatim="—"),
    lambda x: x["observations"][0].update(statement_type_candidate="parent_income_statement"),
    lambda x: x["observations"][0].update(evidence_id="fake-evidence-2"),
])
def test_unqualified_packet_never_reaches_provider(tamper):
    source = packet()
    tamper(source)
    calls = []
    with mock_client(response_for(packet()), calls=calls) as client:
        out = ds.draft_verified_cells(source, api_key="test-key", client=client)
    assert calls == []
    assert out["status"] == "WITHHELD"
    assert out["claims"] == []


def test_key_missing_never_calls_provider():
    calls = []
    with mock_client(response_for(packet()), calls=calls) as client:
        out = ds.draft_verified_cells(packet(), api_key="", client=client)
    assert calls == [] and out["reason"] == "MISSING_API_KEY"


def test_non_stop_finish_cannot_approve_partial_response():
    src = packet()
    with mock_client(response_for(src, finish="length")) as client:
        out = ds.draft_verified_cells(src, api_key="test-key", client=client)
    assert out["status"] == "WITHHELD"
    assert out["reason"] == "GENERATION_NOT_COMPLETE"


def test_wrong_provider_model_fails_closed():
    src = packet()
    with mock_client(response_for(src, model="unexpected-model")) as client:
        out = ds.draft_verified_cells(src, api_key="test-key", client=client)
    assert out["status"] == "WITHHELD"
    assert out["reason"] == "UNEXPECTED_MODEL"


def test_invalid_usage_fails_closed():
    src = packet()
    result = response_for(src)
    result["usage"]["total_tokens"] = 333
    with mock_client(result) as client:
        out = ds.draft_verified_cells(src, api_key="test-key", client=client)
    assert out["status"] == "WITHHELD" and out["claims"] == []


def test_http_error_redacts_provider_body():
    client = httpx.Client(transport=httpx.MockTransport(
        lambda _: httpx.Response(429, text="private secret and bearer token")
    ))
    with client:
        out = ds.draft_verified_cells(packet(), api_key="test-key", client=client)
    assert out["reason"] == "PROVIDER_HTTP_ERROR"
    assert "private secret" not in repr(out)
    assert "test-key" not in repr(out)


def test_transport_timeout_is_fail_closed():
    def handler(_):
        raise httpx.ReadTimeout("Fake network timeout")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        out = ds.draft_verified_cells(packet(), api_key="test-key", client=client)
    assert out["status"] == "WITHHELD"
    assert out["reason"] == "NETWORK_OR_TIMEOUT"


def test_full_packet_too_long_is_not_sent():
    src = packet()
    src["observations"][0]["row_label"] = "X" * 10000
    calls = []
    with mock_client(response_for(packet()), calls=calls) as client:
        out = ds.draft_verified_cells(src, api_key="test-key", client=client)
    assert out["status"] == "WITHHELD" and calls == []
